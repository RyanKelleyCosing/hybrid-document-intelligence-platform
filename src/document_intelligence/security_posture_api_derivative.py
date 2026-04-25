"""Extraction helpers for the public security-posture API derivative package."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from textwrap import dedent

from .repo_boundary import RepoBoundaryManifest

DEFAULT_SECURITY_POSTURE_API_DERIVATIVE_OUTPUT = Path(
    "public-derivatives/security-posture-api"
)
_SECURITY_POSTURE_SUBTREE_ARTIFACT_PATH = "public-subtrees/security-posture-platform"
_SECURITY_POSTURE_PUBLIC_REPO_ARTIFACT_PATH = (
    "public-repo-staging/security-posture-platform"
)
_PUBLIC_MANIFEST_REFERENCE = "private repo boundary manifest"
_SECURITY_POSTURE_API_DERIVATIVE_ARTIFACT_PATHS = {
    DEFAULT_SECURITY_POSTURE_API_DERIVATIVE_OUTPUT.as_posix(),
    _SECURITY_POSTURE_SUBTREE_ARTIFACT_PATH,
    _SECURITY_POSTURE_PUBLIC_REPO_ARTIFACT_PATH,
}

_SECURITY_POSTURE_API_SOURCE_DESTINATIONS = {
    "scripts/verify_public_simulation_stack.py": (
        "scripts/verify_public_simulation_stack.py"
    ),
    "src/document_intelligence/public_request_context.py": (
        "src/security_posture_api/public_request_context.py"
    ),
    "src/document_intelligence/public_site_monitor.py": (
        "src/security_posture_api/public_site_monitor.py"
    ),
    "src/document_intelligence/public_traffic_metrics.py": (
        "src/security_posture_api/public_traffic_metrics.py"
    ),
    "src/document_intelligence/traffic_alerts.py": (
        "src/security_posture_api/traffic_alerts.py"
    ),
    "src/document_intelligence/utils/public_simulation_verifier.py": (
        "src/security_posture_api/utils/public_simulation_verifier.py"
    ),
    "src/document_intelligence/utils/public_traffic_client.py": (
        "src/security_posture_api/utils/public_traffic_client.py"
    ),
}

_SECURITY_POSTURE_API_VALIDATION_DESTINATIONS = {
    "tests/unit/test_public_request_context.py": (
        "tests/unit/test_public_request_context.py"
    ),
    "tests/unit/test_public_simulation_verifier.py": (
        "tests/unit/test_public_simulation_verifier.py"
    ),
    "tests/unit/test_public_site_monitor.py": (
        "tests/unit/test_public_site_monitor.py"
    ),
    "tests/unit/test_public_traffic_client.py": (
        "tests/unit/test_public_traffic_client.py"
    ),
    "tests/unit/test_public_traffic_metrics.py": (
        "tests/unit/test_public_traffic_metrics.py"
    ),
    "tests/unit/test_traffic_alerts.py": "tests/unit/test_traffic_alerts.py",
}

_FUNCTION_APP_TEMPLATE = dedent(
    '''
    """Azure Functions entrypoints for the extracted public security API."""

    from __future__ import annotations

    import json
    import logging
    import sys
    from http import HTTPStatus
    from pathlib import Path
    from typing import Any

    APP_ROOT = Path(__file__).resolve().parent
    SRC_PATH = APP_ROOT / "src"
    if str(SRC_PATH) not in sys.path:
        sys.path.insert(0, str(SRC_PATH))

    import azure.functions as func
    from pydantic import ValidationError

    from security_posture_api.settings import get_settings

    app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


    def _json_response(
        payload: dict[str, Any],
        status_code: HTTPStatus,
    ) -> func.HttpResponse:
        return func.HttpResponse(
            body=json.dumps(payload, indent=2, default=str),
            mimetype="application/json",
            status_code=int(status_code),
        )


    def _validation_error_response(
        error: ValidationError | ValueError,
    ) -> func.HttpResponse:
        details: Any
        if isinstance(error, ValidationError):
            details = error.errors(include_url=False)
        else:
            details = str(error)

        return _json_response(
            {"status": "invalid_request", "details": details},
            HTTPStatus.BAD_REQUEST,
        )


    @app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
    def health_check(req: func.HttpRequest) -> func.HttpResponse:
        del req
        settings = get_settings()

        return _json_response(
            {
                "status": "healthy",
                "service": "security-posture-api",
                "environment": settings.environment_name,
                "publicHealthDigestWindowDays": (
                    settings.public_health_digest_window_days
                ),
                "publicTelemetryRetentionDays": (
                    settings.public_telemetry_retention_days
                ),
            },
            HTTPStatus.OK,
        )


    @app.route(
        route="public-traffic-events",
        methods=["POST"],
        auth_level=func.AuthLevel.ANONYMOUS,
    )
    def capture_public_traffic_event(req: func.HttpRequest) -> func.HttpResponse:
        from security_posture_api.public_traffic_metrics import (
            record_public_traffic_event_aggregate,
        )
        from security_posture_api.traffic_alerts import (
            PublicTrafficEvent,
            build_public_traffic_alert,
            mask_client_ip,
            send_public_traffic_alert,
        )

        try:
            event = PublicTrafficEvent.model_validate(req.get_json())
        except (ValidationError, ValueError) as error:
            return _validation_error_response(error)

        settings = get_settings()
        alert = build_public_traffic_alert(event, req.headers)
        record_public_traffic_event_aggregate(event, req.headers, settings)
        alert_sent = send_public_traffic_alert(alert, settings)

        logging.info(
            "Captured public traffic event route=%s event=%s site=%s session=%s ip=%s",
            alert.event.route,
            alert.event.event_type,
            alert.event.site_mode,
            alert.event.session_id,
            mask_client_ip(alert.client_ip) or "unknown",
        )

        return _json_response(
            {"alertSent": alert_sent, "status": "accepted"},
            HTTPStatus.ACCEPTED,
        )


    @app.route(
        route="public-metrics-summary",
        methods=["GET"],
        auth_level=func.AuthLevel.ANONYMOUS,
    )
    def get_public_metrics_summary(req: func.HttpRequest) -> func.HttpResponse:
        del req

        from security_posture_api.public_traffic_metrics import (
            build_public_traffic_metrics_summary,
        )

        summary = build_public_traffic_metrics_summary(get_settings())
        logging.info(
            "Built public metrics summary total_events=%s sessions=%s last_event=%s",
            summary.total_events,
            summary.unique_sessions,
            summary.last_event_at_utc or "none",
        )

        return _json_response(summary.model_dump(mode="json"), HTTPStatus.OK)


    @app.timer_trigger(
        arg_name="monitor_timer",
        schedule="0 */30 * * * *",
        use_monitor=True,
    )
    def run_public_site_verifier(monitor_timer: func.TimerRequest) -> None:
        del monitor_timer

        from security_posture_api.public_site_monitor import run_public_site_monitor

        results = run_public_site_monitor(get_settings())
        logging.info(
            "Scheduled public site verifier finished ok=%s public=%s traffic=%s",
            results.get("ok"),
            results.get("public_site"),
            results.get("traffic_event"),
        )


    @app.route(
        route="public-request-context",
        methods=["GET"],
        auth_level=func.AuthLevel.ANONYMOUS,
    )
    def get_public_request_context(req: func.HttpRequest) -> func.HttpResponse:
        from security_posture_api.public_request_context import (
            build_public_request_context,
        )

        request_context = build_public_request_context(req.headers, req.url)
        logging.info(
            "Built public request context request_id=%s secure=%s ip_present=%s",
            request_context.request_id,
            request_context.transport_security,
            request_context.client_ip is not None,
        )

        return _json_response(request_context.model_dump(mode="json"), HTTPStatus.OK)
    '''
).lstrip()

_SETTINGS_TEMPLATE = dedent(
    '''
    """Environment-backed settings for the extracted public security API."""

    from __future__ import annotations

    from functools import lru_cache
    from pathlib import Path

    from pydantic import Field
    from pydantic_settings import BaseSettings, SettingsConfigDict


    class AppSettings(BaseSettings):
        """Public security API settings loaded from environment variables."""

        model_config = SettingsConfigDict(
            env_prefix="DOCINT_",
            case_sensitive=False,
            extra="ignore",
        )

        environment_name: str = "dev"
        function_api_base_url: str | None = None
        public_alert_recipient_email: str | None = None
        public_health_digest_max_checks: int = Field(default=5, ge=1, le=20)
        public_health_digest_window_days: int = Field(default=7, ge=1, le=30)
        public_site_url: str | None = None
        public_telemetry_history_container_name: str = "public-site-telemetry"
        public_telemetry_history_directory: Path = (
            Path("outputs") / "public-site-telemetry"
        )
        public_telemetry_retention_days: int = Field(default=60, ge=1, le=365)
        public_traffic_alerts_enabled: bool = False
        smtp_host: str | None = None
        smtp_password: str | None = None
        smtp_port: int = Field(default=587, ge=1, le=65535)
        smtp_sender_email: str | None = None
        smtp_use_tls: bool = True
        smtp_username: str | None = None
        storage_connection_string: str | None = None


    @lru_cache
    def get_settings() -> AppSettings:
        """Return the cached application settings instance."""

        return AppSettings()
    '''
).lstrip()

_VERIFICATION_SETTINGS_TEMPLATE = dedent(
    '''
    """Helper functions for local settings and storage resolution in verifier flows."""

    from __future__ import annotations

    import json
    from pathlib import Path

    from security_posture_api.utils.public_simulation_verifier import (
        resolve_azure_cli_executable,
        run_azure_cli_text,
    )


    def load_local_values(local_settings_file: Path) -> dict[str, str]:
        """Load the Values section from a local.settings.json file."""

        if not local_settings_file.exists():
            return {}

        payload = json.loads(local_settings_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}

        values = payload.get("Values")
        if not isinstance(values, dict):
            return {}

        return {
            str(key): str(value)
            for key, value in values.items()
            if value is not None
        }


    def _is_placeholder_value(value: str | None) -> bool:
        if value is None:
            return True

        normalized_value = value.strip()
        return not normalized_value or normalized_value.startswith("__REPLACE_")


    def resolve_storage_connection_string(
        azure_resource_group_name: str,
        local_values: dict[str, str],
        *,
        storage_account_name: str = "",
        storage_connection_string: str | None = None,
    ) -> tuple[str, str | None]:
        """Resolve the storage connection string from local settings or Azure CLI."""

        resolved_connection_string = (
            storage_connection_string
            or local_values.get("DOCINT_STORAGE_CONNECTION_STRING")
            or local_values.get("AzureWebJobsStorage")
        )
        if resolved_connection_string and not _is_placeholder_value(
            resolved_connection_string
        ):
            normalized_account_name = storage_account_name.strip() or None
            return resolved_connection_string.strip(), normalized_account_name

        az_executable = resolve_azure_cli_executable()
        normalized_account_name = storage_account_name.strip()
        if not normalized_account_name:
            normalized_account_name = run_azure_cli_text(
                az_executable,
                [
                    "resource",
                    "list",
                    "--resource-group",
                    azure_resource_group_name,
                    "--resource-type",
                    "Microsoft.Storage/storageAccounts",
                    "--query",
                    "[0].name",
                    "--output",
                    "tsv",
                ],
            )

        if not normalized_account_name:
            raise RuntimeError("Could not resolve a storage account name.")

        connection_string = run_azure_cli_text(
            az_executable,
            [
                "storage",
                "account",
                "show-connection-string",
                "--resource-group",
                azure_resource_group_name,
                "--name",
                normalized_account_name,
                "--query",
                "connectionString",
                "--output",
                "tsv",
            ],
        )
        if not connection_string:
            raise RuntimeError("Could not resolve a storage connection string.")

        return connection_string, normalized_account_name
    '''
).lstrip()

_TEST_FUNCTION_APP_TEMPLATE = dedent(
    '''
    """Unit tests for the extracted public Azure Functions entrypoint."""

    from __future__ import annotations

    import importlib
    import json
    import sys
    from pathlib import Path
    from types import ModuleType

    import azure.functions as func
    from pytest import MonkeyPatch

    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


    def load_function_app() -> ModuleType:
        """Load the standalone public Function app module."""

        sys.modules.pop("security_posture_api.public_traffic_metrics", None)
        sys.modules.pop("security_posture_api.settings", None)
        sys.modules.pop("function_app", None)

        module = importlib.import_module("function_app")

        from security_posture_api.settings import get_settings

        get_settings.cache_clear()
        return importlib.reload(module)


    def test_function_app_indexes_public_routes() -> None:
        """The extracted app should expose only the public API surface."""

        module = load_function_app()
        function_names = sorted(
            function.get_function_name() for function in module.app.get_functions()
        )

        assert function_names == [
            "capture_public_traffic_event",
            "get_public_metrics_summary",
            "get_public_request_context",
            "health_check",
            "run_public_site_verifier",
        ]


    def test_public_traffic_event_returns_accepted_payload(
        monkeypatch: MonkeyPatch,
    ) -> None:
        """Public traffic events should validate and return an accepted payload."""

        module = load_function_app()

        from security_posture_api import traffic_alerts

        captured: dict[str, str | None] = {}

        def fake_send_public_traffic_alert(alert: object, settings: object) -> bool:
            del settings
            typed_alert = traffic_alerts.PublicTrafficAlert.model_validate(alert)
            captured["client_ip"] = typed_alert.client_ip
            captured["route"] = typed_alert.event.route
            return False

        monkeypatch.setattr(
            traffic_alerts,
            "send_public_traffic_alert",
            fake_send_public_traffic_alert,
        )

        request = func.HttpRequest(
            method="POST",
            url="http://localhost/api/public-traffic-events",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "pytest-agent",
                "X-Forwarded-For": "203.0.113.77, 10.0.0.4",
            },
            params={},
            route_params={},
            body=json.dumps(
                {
                    "event_type": "page_view",
                    "route": "intake",
                    "session_id": "session-1",
                    "site_mode": "security",
                }
            ).encode("utf-8"),
        )

        response = module.capture_public_traffic_event(request)
        payload = json.loads(response.get_body().decode("utf-8"))

        assert response.status_code == 202
        assert payload == {"alertSent": False, "status": "accepted"}
        assert captured == {
            "client_ip": "203.0.113.77",
            "route": "intake",
        }


    def test_public_request_context_returns_sanitized_payload() -> None:
        """The request-context route should expose only sanitized request data."""

        module = load_function_app()
        request = func.HttpRequest(
            method="GET",
            url="http://localhost/api/public-request-context",
            headers={
                "Host": "func-doc-test.azurewebsites.net",
                "X-ARR-LOG-ID": "abcdef1234567890fedcba",
                "X-Forwarded-For": "203.0.113.55, 10.0.0.4",
                "X-Forwarded-Host": "ryancodes.security.online",
                "X-Forwarded-Proto": "https",
                "X-Geo-Country": "US",
                "X-Geo-Region": "Ohio",
                "X-SSL-Protocol": "TLSv1.3",
            },
            params={},
            route_params={},
            body=b"",
        )

        response = module.get_public_request_context(request)
        payload = json.loads(response.get_body().decode("utf-8"))

        assert response.status_code == 200
        assert payload["client_ip"] == "203.0.113.55"
        assert payload["approximate_location"] == "US / Ohio"
        assert payload["forwarded_host"] == "ryancodes.security.online"
        assert payload["forwarded_proto"] == "https"
        assert payload["transport_security"] == "HTTPS only"
        assert payload["tls_protocol"] == "TLSv1.3"
        assert payload["request_id"] == "req-abcdef123456"
        assert payload["request_timestamp_utc"]


    def test_public_metrics_summary_returns_aggregate_payload(
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """The metrics route should expose aggregate-only public telemetry."""

        monkeypatch.setenv(
            "DOCINT_PUBLIC_TELEMETRY_HISTORY_DIRECTORY",
            str(tmp_path),
        )
        module = load_function_app()

        from security_posture_api import traffic_alerts
        from security_posture_api.public_traffic_metrics import (
            build_public_health_check_record,
            persist_public_health_check_record,
        )

        monkeypatch.setattr(
            traffic_alerts,
            "send_public_traffic_alert",
            lambda alert, settings: False,
        )

        capture_request = func.HttpRequest(
            method="POST",
            url="http://localhost/api/public-traffic-events",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "pytest-agent",
                "X-Forwarded-For": "203.0.113.77, 10.0.0.4",
                "X-Geo-Country": "US",
                "X-Geo-Region": "Ohio",
            },
            params={},
            route_params={},
            body=json.dumps(
                {
                    "event_type": "page_view",
                    "route": "security",
                    "session_id": "session-1",
                    "site_mode": "security",
                }
            ).encode("utf-8"),
        )
        module.capture_public_traffic_event(capture_request)
        persist_public_health_check_record(
            build_public_health_check_record(
                {
                    "alert_settings": {"email_ready": True},
                    "ok": True,
                    "public_site": {"is_reachable": True, "status_code": 200},
                    "traffic_event": {"ok": True, "status_code": 202},
                }
            ),
            module.get_settings(),
        )

        summary_request = func.HttpRequest(
            method="GET",
            url="http://localhost/api/public-metrics-summary",
            headers={},
            params={},
            route_params={},
            body=b"",
        )

        response = module.get_public_metrics_summary(summary_request)
        payload = json.loads(response.get_body().decode("utf-8"))

        assert response.status_code == 200
        assert payload["availability_percentage"] == 100.0
        assert payload["availability_source"] == "External verification history"
        assert payload["collection_mode"] == "Durable sanitized aggregate history"
        assert payload["current_status"] == "Healthy"
        assert payload["latest_alert_configuration_ready"] is True
        assert payload["latest_monitor_name"] == "public-simulation-verifier"
        assert payload["total_events"] == 1
        assert payload["unique_sessions"] == 1
        assert payload["recent_health_checks"][0]["overall_ok"] is True
        assert payload["route_counts"] == [{"label": "security", "count": 1}]
        assert payload["site_mode_counts"] == [{"label": "security", "count": 1}]
        assert payload["geography_counts"] == [{"label": "US / Ohio", "count": 1}]
        assert payload["last_successful_health_check_at_utc"]
        assert payload["last_event_at_utc"]


    def test_health_probe_event_skips_alert_email_and_traffic_counts(
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Scheduled health probes should not inflate public traffic counts."""

        monkeypatch.setenv(
            "DOCINT_PUBLIC_TELEMETRY_HISTORY_DIRECTORY",
            str(tmp_path),
        )
        module = load_function_app()

        probe_request = func.HttpRequest(
            method="POST",
            url="http://localhost/api/public-traffic-events",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "pytest-probe",
            },
            params={},
            route_params={},
            body=json.dumps(
                {
                    "event_type": "health_probe",
                    "route": "security-monitor",
                    "session_id": "probe-1",
                    "site_mode": "simulation",
                }
            ).encode("utf-8"),
        )

        probe_response = module.capture_public_traffic_event(probe_request)
        probe_payload = json.loads(probe_response.get_body().decode("utf-8"))

        assert probe_response.status_code == 202
        assert probe_payload == {"alertSent": False, "status": "accepted"}

        summary_request = func.HttpRequest(
            method="GET",
            url="http://localhost/api/public-metrics-summary",
            headers={},
            params={},
            route_params={},
            body=b"",
        )

        summary_response = module.get_public_metrics_summary(summary_request)
        summary_payload = json.loads(summary_response.get_body().decode("utf-8"))

        assert summary_response.status_code == 200
        assert summary_payload["total_events"] == 0
        assert summary_payload["unique_sessions"] == 0
        assert summary_payload["route_counts"] == []
        assert summary_payload["site_mode_counts"] == []


    def test_public_site_verifier_timer_runs_monitor_helper(
        monkeypatch: MonkeyPatch,
    ) -> None:
        """The scheduled timer should delegate to the public-site monitor helper."""

        module = load_function_app()

        from security_posture_api import public_site_monitor

        captured: dict[str, object] = {}

        def fake_run_public_site_monitor(settings: object) -> dict[str, object]:
            captured["settings"] = settings
            return {
                "ok": True,
                "public_site": {"is_reachable": True},
                "traffic_event": {"ok": True},
            }

        monkeypatch.setattr(
            public_site_monitor,
            "run_public_site_monitor",
            fake_run_public_site_monitor,
        )

        module.run_public_site_verifier(None)

        assert captured["settings"] == module.get_settings()
    '''
).lstrip()


@dataclass(frozen=True)
class SecurityPostureApiDerivativeCopy:
    """One source file copied into the public security API derivative."""

    destination_relative_path: str
    source_relative_path: str


@dataclass(frozen=True)
class SecurityPostureApiDerivativePlan:
    """Resolved extraction plan for the public security API derivative."""

    copied_files: tuple[SecurityPostureApiDerivativeCopy, ...]
    deferred_candidate_sources: tuple[str, ...]
    validation_files: tuple[SecurityPostureApiDerivativeCopy, ...]


def build_security_posture_api_derivative_plan(
    manifest: RepoBoundaryManifest,
) -> SecurityPostureApiDerivativePlan:
    """Build the public security API derivative plan from the boundary manifest."""

    candidate_entries = {
        entry.relative_path: entry
        for entry in manifest.entries
        if entry.exposure == "public_derivative_candidate"
    }

    copied_files = _build_manifest_copied_files(candidate_entries)
    validation_files = _build_validation_files()
    deferred_candidate_sources = tuple(
        sorted(
            relative_path
            for relative_path in candidate_entries
            if relative_path not in _SECURITY_POSTURE_API_SOURCE_DESTINATIONS
            and relative_path not in _SECURITY_POSTURE_API_DERIVATIVE_ARTIFACT_PATHS
        )
    )
    return SecurityPostureApiDerivativePlan(
        copied_files=tuple(copied_files),
        deferred_candidate_sources=deferred_candidate_sources,
        validation_files=tuple(validation_files),
    )


def _build_manifest_copied_files(
    candidate_entries: dict[str, object],
) -> list[SecurityPostureApiDerivativeCopy]:
    copied_files: list[SecurityPostureApiDerivativeCopy] = []
    for source_relative_path, destination_relative_path in (
        _SECURITY_POSTURE_API_SOURCE_DESTINATIONS.items()
    ):
        if source_relative_path not in candidate_entries:
            raise ValueError(
                "Security API derivative source path is not classified as a public "
                f"derivative candidate: '{source_relative_path}'."
            )

        copied_files.append(
            SecurityPostureApiDerivativeCopy(
                destination_relative_path=destination_relative_path,
                source_relative_path=source_relative_path,
            )
        )

    return copied_files


def _build_validation_files() -> list[SecurityPostureApiDerivativeCopy]:
    return [
        SecurityPostureApiDerivativeCopy(
            destination_relative_path=destination_relative_path,
            source_relative_path=source_relative_path,
        )
        for source_relative_path, destination_relative_path in (
            _SECURITY_POSTURE_API_VALIDATION_DESTINATIONS.items()
        )
    ]


def extract_security_posture_api_derivative_package(
    repo_root: Path,
    output_directory: Path,
    manifest: RepoBoundaryManifest,
    manifest_path: Path,
) -> SecurityPostureApiDerivativePlan:
    """Extract the standalone public security API derivative package."""

    plan = build_security_posture_api_derivative_plan(manifest)
    output_directory.mkdir(parents=True, exist_ok=True)

    for copied_file in plan.copied_files:
        source_path = repo_root / copied_file.source_relative_path
        destination_path = output_directory / copied_file.destination_relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(
            _transform_copied_source(copied_file.destination_relative_path, source_path),
            encoding="utf-8",
        )

    for validation_file in plan.validation_files:
        source_path = repo_root / validation_file.source_relative_path
        destination_path = output_directory / validation_file.destination_relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(
            _transform_validation_source(source_path),
            encoding="utf-8",
        )

    del manifest_path

    for relative_path, content in _build_scaffold_files(plan).items():
        destination_path = output_directory / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(content, encoding="utf-8")

    return plan


def _transform_copied_source(destination_relative_path: str, source_path: Path) -> str:
    source_text = source_path.read_text(encoding="utf-8")
    if destination_relative_path == "scripts/verify_public_simulation_stack.py":
        return _transform_verifier_script(source_text)

    return _rewrite_package_imports(source_text)


def _transform_validation_source(source_path: Path) -> str:
    source_text = source_path.read_text(encoding="utf-8")
    source_text = _rewrite_package_imports(source_text)
    return source_text.replace(
        "from document_intelligence import ",
        "from security_posture_api import ",
    )


def _rewrite_package_imports(source_text: str) -> str:
    return source_text.replace("document_intelligence.", "security_posture_api.")


def _transform_verifier_script(source_text: str) -> str:
    transformed_text = source_text.replace(
        "from document_intelligence.inspection import (  # noqa: E402\n"
        "    load_local_values,\n"
        "    resolve_storage_connection_string,\n"
        ")",
        "from security_posture_api.verification_settings import (  # noqa: E402\n"
        "    load_local_values,\n"
        "    resolve_storage_connection_string,\n"
        ")",
    )
    return _rewrite_package_imports(transformed_text)


def _build_scaffold_files(
    plan: SecurityPostureApiDerivativePlan,
) -> dict[str, str]:
    package_name = "ryan-security-posture-api"
    generated_files = sorted(
        [
            ".gitignore",
            "README.md",
            "derivative-sources.json",
            "function_app.py",
            "host.json",
            "local.settings.example.json",
            "pyproject.toml",
            "requirements.txt",
            "src/security_posture_api/__init__.py",
            "src/security_posture_api/settings.py",
            "src/security_posture_api/utils/__init__.py",
            "src/security_posture_api/verification_settings.py",
            "tests/unit/test_function_app.py",
        ]
    )
    derivative_sources_payload = {
        "package_name": package_name,
        "manifest_reference": _PUBLIC_MANIFEST_REFERENCE,
        "package_purpose": "public_demonstration_only",
        "copied_files": [
            item.destination_relative_path for item in plan.copied_files
        ],
        "validation_files": [
            item.destination_relative_path for item in plan.validation_files
        ],
        "generated_files": generated_files,
    }
    return {
        ".gitignore": _build_gitignore(),
        "README.md": _build_readme(plan=plan),
        "derivative-sources.json": json.dumps(
            derivative_sources_payload,
            indent=2,
        )
        + "\n",
        "function_app.py": _FUNCTION_APP_TEMPLATE,
        "host.json": _build_host_json(),
        "local.settings.example.json": _build_local_settings_example_json(),
        "pyproject.toml": _build_pyproject_toml(),
        "requirements.txt": _build_requirements_txt(),
        "src/security_posture_api/__init__.py": (
            '"""Public security posture API package."""\n'
        ),
        "src/security_posture_api/settings.py": _SETTINGS_TEMPLATE,
        "src/security_posture_api/utils/__init__.py": (
            '"""Utility helpers for the public security posture API."""\n'
        ),
        "src/security_posture_api/verification_settings.py": (
            _VERIFICATION_SETTINGS_TEMPLATE
        ),
        "tests/unit/test_function_app.py": _TEST_FUNCTION_APP_TEMPLATE,
    }


def _build_gitignore() -> str:
    return dedent(
        """
        .mypy_cache/
        .pytest_cache/
        .ruff_cache/
        .venv/
        __pycache__/
        local.settings.json
        outputs/
        """
    ).lstrip()


def _build_readme(
    plan: SecurityPostureApiDerivativePlan,
) -> str:
    runtime_file_lines = "\n".join(
        f"- `{item.destination_relative_path}`" for item in plan.copied_files
    )
    validation_file_lines = "\n".join(
        f"- `{item.destination_relative_path}`"
        for item in plan.validation_files
    )
    return "\n".join(
        [
            "# Ryan Security Posture API",
            "",
            "This directory is the extracted public-safe backend slice for the security",
            "posture site.",
            "",
            "It is intended for public demonstration only. The private repo remains the",
            "live operational source of truth.",
            "",
            "It keeps the anonymous request-context route, aggregate metrics route,",
            "scheduled monitor, SMTP-backed public alerts, and verifier helpers in a",
            "standalone Azure Functions package without dragging the private operator",
            "shell, protected workflow routes, or tenant-specific infrastructure wiring.",
            "",
            "## Source Of Truth",
            "",
            "The extraction plan is derived from the private repo boundary manifest.",
            "Machine-specific paths, local settings, and secrets are intentionally excluded",
            "from this public package.",
            "",
            "Rebuild this package from the repo root with:",
            "",
            "```powershell",
            "python scripts/extract_public_security_api_package.py",
            "```",
            "",
            "## Runtime Files",
            "",
            runtime_file_lines,
            "",
            "## Validation Companions",
            "",
            validation_file_lines,
            "",
            "## Environment Variables",
            "",
            "- `DOCINT_ENVIRONMENT_NAME`: public environment label surfaced in summaries.",
            "- `DOCINT_FUNCTION_API_BASE_URL`: explicit base URL used by the monitor when",
            "  the Functions host is not inferable from `WEBSITE_HOSTNAME`.",
            "- `DOCINT_PUBLIC_SITE_URL`: deployed public site URL used by the external",
            "  reachability probe.",
            "- `DOCINT_PUBLIC_TRAFFIC_ALERTS_ENABLED`: enables SMTP-backed alert sends for",
            "  non-health-probe events.",
            "- `DOCINT_PUBLIC_ALERT_RECIPIENT_EMAIL`: target inbox for optional traffic",
            "  alerts.",
            "- `DOCINT_PUBLIC_TELEMETRY_HISTORY_*`: storage and retention settings for the",
            "  sanitized aggregate history.",
            "- `DOCINT_STORAGE_CONNECTION_STRING` or `AzureWebJobsStorage`: durable history",
            "  storage connection string.",
            "- `DOCINT_SMTP_*`: SMTP relay settings for optional alert sends.",
            "",
            "## Local Validation",
            "",
            "```powershell",
            "pip install -r requirements.txt",
            "pip install -e .[dev]",
            "pytest tests/unit",
            "func start",
            "```",
            "",
            "For a full public-surface check after the API package is running, use:",
            "",
            "```powershell",
            "python scripts/verify_public_simulation_stack.py --settings-source local",
            "```",
            "",
        ]
    )


def _build_host_json() -> str:
    return dedent(
        """
        {
          "version": "2.0",
          "extensionBundle": {
            "id": "Microsoft.Azure.Functions.ExtensionBundle",
            "version": "[4.*, 5.0.0)"
          },
          "logging": {
            "applicationInsights": {
              "samplingSettings": {
                "isEnabled": true,
                "excludedTypes": "Request"
              }
            }
          }
        }
        """
    ).lstrip()


def _build_local_settings_example_json() -> str:
    return dedent(
        """
        {
          "IsEncrypted": false,
          "Host": {
            "LocalHttpPort": 7071
          },
          "Values": {
            "AzureWebJobsStorage": "UseDevelopmentStorage=true",
            "FUNCTIONS_WORKER_RUNTIME": "python",
            "PYTHONPATH": "src",
            "DOCINT_ENVIRONMENT_NAME": "dev",
            "DOCINT_STORAGE_CONNECTION_STRING": "UseDevelopmentStorage=true",
            "DOCINT_FUNCTION_API_BASE_URL": "",
            "DOCINT_PUBLIC_SITE_URL": "",
            "DOCINT_PUBLIC_TRAFFIC_ALERTS_ENABLED": "false",
            "DOCINT_PUBLIC_ALERT_RECIPIENT_EMAIL": "",
            "DOCINT_PUBLIC_TELEMETRY_HISTORY_CONTAINER_NAME": "public-site-telemetry",
            "DOCINT_PUBLIC_TELEMETRY_HISTORY_DIRECTORY": "outputs/public-site-telemetry",
            "DOCINT_PUBLIC_TELEMETRY_RETENTION_DAYS": "60",
            "DOCINT_PUBLIC_HEALTH_DIGEST_WINDOW_DAYS": "7",
            "DOCINT_PUBLIC_HEALTH_DIGEST_MAX_CHECKS": "5",
            "DOCINT_SMTP_HOST": "",
            "DOCINT_SMTP_PORT": "587",
            "DOCINT_SMTP_USERNAME": "",
            "DOCINT_SMTP_PASSWORD": "",
            "DOCINT_SMTP_SENDER_EMAIL": "",
            "DOCINT_SMTP_USE_TLS": "true"
          }
        }
        """
    ).lstrip()


def _build_pyproject_toml() -> str:
    return dedent(
        """
        [build-system]
        requires = ["setuptools>=68", "wheel"]
        build-backend = "setuptools.build_meta"

        [project]
        name = "ryan-security-posture-api"
        version = "0.1.0"
        description = "Extracted public-safe API package for the Ryan security posture site."
        readme = "README.md"
        requires-python = ">=3.14,<3.15"
        dependencies = [
          "azure-functions>=1.23.0",
          "azure-storage-blob>=12.24.0",
          "pydantic>=2.10.0",
          "pydantic-settings>=2.7.1",
        ]

        [project.optional-dependencies]
        dev = [
          "mypy>=1.14.1",
          "pytest>=8.3.4",
          "ruff>=0.8.4",
        ]

        [tool.setuptools]
        package-dir = {"" = "src"}

        [tool.setuptools.packages.find]
        where = ["src"]

        [tool.pytest.ini_options]
        pythonpath = ["src"]
        testpaths = ["tests"]

        [tool.ruff]
        line-length = 88
        target-version = "py314"

        [tool.ruff.lint]
        select = ["B", "E", "F", "I", "UP"]

        [tool.mypy]
        python_version = "3.14"
        strict = true
        mypy_path = "src"
        packages = ["security_posture_api"]

        [[tool.mypy.overrides]]
        module = ["azure.functions"]
        ignore_missing_imports = true

        [[tool.mypy.overrides]]
        module = ["function_app"]
        disallow_untyped_decorators = false
        warn_return_any = false
        """
    ).lstrip()


def _build_requirements_txt() -> str:
    return dedent(
        """
        azure-functions>=1.23.0
        azure-storage-blob>=12.24.0
        pydantic>=2.10.0
        pydantic-settings>=2.7.1
        """
    ).lstrip()