"""Unit tests for the Azure Functions entrypoint."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import azure.functions as func
from pytest import MonkeyPatch


def load_function_app(
    monkeypatch: MonkeyPatch,
    durable_enabled: bool,
) -> ModuleType:
    """Load function_app with the requested Durable toggle."""
    monkeypatch.setenv(
        "DOCINT_ENABLE_DURABLE_WORKFLOWS",
        "true" if durable_enabled else "false",
    )
    sys.modules.pop("document_intelligence.public_traffic_metrics", None)
    sys.modules.pop("function_app", None)

    module = importlib.import_module("function_app")

    from document_intelligence.settings import get_settings

    get_settings.cache_clear()
    return importlib.reload(module)


def create_cost_history_fixture(history_directory: Path) -> None:
    """Create a representative public-safe cost history fixture."""

    latest_json_path = history_directory / "json" / "latest.json"
    history_csv_path = history_directory / "csv" / "daily-cost-history.csv"
    latest_json_path.parent.mkdir(parents=True, exist_ok=True)
    history_csv_path.parent.mkdir(parents=True, exist_ok=True)

    latest_json_path.write_text(
        json.dumps(
            {
                "costSummary": {
                    "currency": "USD",
                    "daily_cost_trend": [
                        {
                            "amount": 14.0,
                            "label": "Apr 17",
                            "period_end": "2026-04-17",
                            "period_start": "2026-04-17",
                        },
                        {
                            "amount": 18.25,
                            "label": "Apr 18",
                            "period_end": "2026-04-18",
                            "period_start": "2026-04-18",
                        },
                        {
                            "amount": 22.5,
                            "label": "Apr 19",
                            "period_end": "2026-04-19",
                            "period_start": "2026-04-19",
                        },
                        {
                            "amount": 24.5,
                            "label": "Apr 20",
                            "period_end": "2026-04-20",
                            "period_start": "2026-04-20",
                        },
                    ],
                    "day_over_day_delta": 4.25,
                    "month_to_date_cost": 184.5,
                    "monthly_cost_trend": [
                        {
                            "amount": 184.5,
                            "label": "Apr 2026",
                            "period_end": "2026-04-20",
                            "period_start": "2026-04-01",
                        }
                    ],
                    "previous_day_cost": 18.25,
                    "recent_daily_costs": [
                        {"amount": 14.0, "usage_date": "2026-04-17"},
                        {"amount": 18.25, "usage_date": "2026-04-18"},
                        {"amount": 22.5, "usage_date": "2026-04-19"},
                    ],
                    "today_cost": 24.5,
                    "top_resource_groups": [
                        {"amount": 82.0, "name": "rg-doc-intel-dev"}
                    ],
                    "top_resources": [
                        {"amount": 57.5, "name": "func-doc-test-nwigok"}
                    ],
                    "top_service_families": [
                        {"amount": 44.0, "name": "Azure AI Services"}
                    ],
                    "week_to_date_cost": 104.75,
                    "weekly_cost_trend": [
                        {
                            "amount": 104.75,
                            "label": "Week of Apr 13",
                            "period_end": "2026-04-20",
                            "period_start": "2026-04-13",
                        }
                    ],
                    "year_to_date_cost": 612.25,
                    "yesterday_cost": 22.5,
                },
                "generatedAt": "2026-04-20T17:16:33.262741Z",
                "historyRow": {
                    "currency": "USD",
                    "day_over_day_delta": 4.25,
                    "generated_at": "2026-04-20T17:16:33.262741Z",
                    "month_to_date_cost": 184.5,
                    "previous_day_cost": 18.25,
                    "top_resource_group_name": "rg-doc-intel-dev",
                    "top_resource_name": "func-doc-test-nwigok",
                    "today_cost": 24.5,
                    "week_to_date_cost": 104.75,
                    "year_to_date_cost": 612.25,
                    "yesterday_cost": 22.5,
                },
            }
        ),
        encoding="utf-8",
    )
    history_csv_path.write_text(
        "generated_at,currency,today_cost,week_to_date_cost,month_to_date_cost,year_to_date_cost,yesterday_cost,previous_day_cost,day_over_day_delta,top_resource_name,top_resource_group_name\n"
        "2026-04-17T17:16:33.262741Z,USD,14.0,59.25,144.0,567.0,14.0,10.5,3.5,func-doc-test-nwigok,rg-doc-intel-dev\n"
        "2026-04-18T17:16:33.262741Z,USD,18.25,77.5,162.25,585.25,18.25,14.0,4.25,func-doc-test-nwigok,rg-doc-intel-dev\n"
        "2026-04-19T17:16:33.262741Z,USD,22.5,100.0,184.75,607.75,22.5,18.25,4.25,func-doc-test-nwigok,rg-doc-intel-dev\n"
        "2026-04-20T17:16:33.262741Z,USD,24.5,104.75,184.5,612.25,22.5,18.25,4.25,func-doc-test-nwigok,rg-doc-intel-dev\n",
        encoding="utf-8",
    )


def test_function_app_indexes_http_routes_when_durable_disabled(
    monkeypatch: MonkeyPatch,
) -> None:
    """Disabling Durable should still expose the HTTP routes for Flex testing."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    function_names = sorted(
        function.get_function_name() for function in module.app.get_functions()
    )

    assert function_names == [
        "apply_packet_review_assignment",
        "apply_packet_review_decision",
        "apply_packet_review_extraction_edits",
        "apply_packet_review_note",
        "capture_public_traffic_event",
        "create_intake_source",
        "create_manual_packet",
        "create_packet_review_task",
        "delete_intake_source",
        "get_operator_contracts",
        "get_packet_document_content",
        "get_packet_workspace",
        "get_processing_taxonomy",
        "get_public_api_docs",
        "get_public_cost_history",
        "get_public_cost_latest",
        "get_public_cost_summary",
        "get_public_metrics_summary",
        "get_public_openapi_contract",
        "get_public_request_context",
        "get_public_security_cves",
        "get_public_security_msrc_latest",
        "get_review_item",
        "health_check",
        "ingest_partner_intake_source",
        "list_intake_sources",
        "list_packet_queue",
        "list_review_items",
        "preview_review_item",
        "replay_packet",
        "retry_packet_stage",
        "review_packet_recommendation",
        "run_intake_source",
        "run_packet_classification",
        "run_packet_extraction",
        "run_packet_ocr",
        "run_packet_recommendation",
        "run_public_cost_refresh",
        "run_public_site_verifier",
        "run_public_traffic_daily_digest",
        "set_intake_source_enablement",
        "start_ingestion",
        "update_intake_source",
        "update_review_item_decision",
    ]


def test_public_traffic_event_returns_accepted_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """Public traffic events should validate, log, and return an accepted payload."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import traffic_alerts

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


def test_public_openapi_contract_returns_public_routes_only(
    monkeypatch: MonkeyPatch,
) -> None:
    """The anonymous contract route should expose only the public API surface."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/docs/public-openapi.json",
        headers={},
        params={},
        route_params={},
        body=None,
    )

    response = module.get_public_openapi_contract(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["openapi"] == "3.1.0"
    assert payload["info"]["title"] == "Hybrid Document Intelligence Public API"
    assert "/health" in payload["paths"]
    assert "/public-request-context" in payload["paths"]
    assert "/public-cost-summary" in payload["paths"]
    assert "/security/cves" in payload["paths"]
    assert "/security/msrc-latest" in payload["paths"]
    assert "PublicSecurityCveFeed" in payload["components"]["schemas"]
    assert "PublicSecurityMsrcFeed" in payload["components"]["schemas"]
    assert "/packets" not in payload["paths"]
    assert "protected operator queue" in payload["info"]["description"].lower()


def test_public_api_docs_returns_redoc_html(
    monkeypatch: MonkeyPatch,
) -> None:
    """The anonymous docs route should render a Redoc page for the public contract."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/docs/public-api",
        headers={},
        params={},
        route_params={},
        body=None,
    )

    response = module.get_public_api_docs(request)
    body = response.get_body().decode("utf-8")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert "Public API Contract" in body
    assert "/api/docs/public-openapi.json" in body
    assert "redoc" in body.lower()


def test_public_request_context_returns_sanitized_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The public request-context route should expose only sanitized request data."""
    module = load_function_app(monkeypatch, durable_enabled=False)

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
    assert payload["enrichment_provider_name"] is None
    assert payload["enrichment_status"].startswith("No provider-backed network enrichment")
    assert payload["public_network_enrichment_enabled"] is True
    assert payload["public_security_globe_enabled"] is True


def test_public_request_context_returns_provider_backed_enrichment(
    monkeypatch: MonkeyPatch,
) -> None:
    """The public request-context route should expose bounded provider-backed fields."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import public_network_enrichment
    from document_intelligence.public_network_enrichment import PublicNetworkEnrichment

    class _StubEnrichmentProvider:
        provider_name = "IPQualityScore"

        def enrich(self, client_ip: str) -> PublicNetworkEnrichment | None:
            if client_ip != "203.0.113.55":
                return None

            return PublicNetworkEnrichment(
                approximate_location="US / Ohio",
                hosting_provider="Azure Front Door",
                network_asn="AS8075",
                network_owner="Microsoft Corporation",
                reputation_summary="Low observed abuse risk · fraud score 18/100",
                vpn_proxy_status="Data Center/Web Hosting/Transit path observed by IPQualityScore.",
            )

    monkeypatch.setattr(
        public_network_enrichment,
        "build_public_network_enrichment_provider",
        lambda settings: _StubEnrichmentProvider(),
    )

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/public-request-context",
        headers={
            "Host": "func-doc-test.azurewebsites.net",
            "X-Forwarded-For": "203.0.113.55, 10.0.0.4",
            "X-Forwarded-Host": "ryancodes.security.online",
            "X-Forwarded-Proto": "https",
        },
        params={},
        route_params={},
        body=b"",
    )

    response = module.get_public_request_context(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["approximate_location"] == "US / Ohio"
    assert payload["enrichment_provider_name"] == "IPQualityScore"
    assert payload["enrichment_status"] == (
        "Provider-backed network signals loaded from IPQualityScore."
    )
    assert payload["network_asn"] == "AS8075"
    assert payload["network_owner"] == "Microsoft Corporation"
    assert payload["hosting_provider"] == "Azure Front Door"
    assert payload["public_network_enrichment_enabled"] is True
    assert payload["public_security_globe_enabled"] is True
    assert payload["vpn_proxy_status"] == (
        "Data Center/Web Hosting/Transit path observed by IPQualityScore."
    )
    assert payload["reputation_summary"] == (
        "Low observed abuse risk · fraud score 18/100"
    )


def test_public_request_context_honors_feature_flags(
    monkeypatch: MonkeyPatch,
) -> None:
    """The public request-context route should surface rollout flags from settings."""

    monkeypatch.setenv("DOCINT_PUBLIC_NETWORK_ENRICHMENT_ENABLED", "false")
    monkeypatch.setenv("DOCINT_PUBLIC_SECURITY_GLOBE_ENABLED", "false")
    module = load_function_app(monkeypatch, durable_enabled=False)

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/public-request-context",
        headers={
            "Host": "func-doc-test.azurewebsites.net",
            "X-Forwarded-For": "203.0.113.55, 10.0.0.4",
            "X-Forwarded-Host": "ryancodes.security.online",
            "X-Forwarded-Proto": "https",
        },
        params={},
        route_params={},
        body=b"",
    )

    response = module.get_public_request_context(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["public_network_enrichment_enabled"] is False
    assert payload["public_security_globe_enabled"] is False
    assert payload["enrichment_provider_name"] is None
    assert payload["enrichment_status"] == (
        "Provider-backed network enrichment is disabled by feature flag."
    )


def test_public_metrics_summary_returns_aggregate_payload(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The public metrics route should expose aggregate-only public telemetry."""
    monkeypatch.setenv("DOCINT_PUBLIC_TELEMETRY_HISTORY_DIRECTORY", str(tmp_path))
    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import traffic_alerts
    from document_intelligence.public_traffic_metrics import (
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
        module._get_settings(),
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
    assert payload["recent_activity_window"].startswith("Short-lived in-memory")
    assert payload["recent_activity"][0]["route"] == "security"
    assert payload["route_counts"] == [{"label": "security", "count": 1}]
    assert payload["site_mode_counts"] == [{"label": "security", "count": 1}]
    assert payload["geography_counts"] == [{"label": "US / Ohio", "count": 1}]
    assert payload["traffic_cadence_window"].startswith("Last 12 hourly buckets")
    assert len(payload["traffic_cadence"]) == 12
    assert payload["last_successful_health_check_at_utc"]
    assert payload["last_event_at_utc"]


def test_health_probe_event_skips_alert_email_and_traffic_counts(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Scheduled health probes should verify the route without inflating traffic counts."""

    monkeypatch.setenv("DOCINT_PUBLIC_TELEMETRY_HISTORY_DIRECTORY", str(tmp_path))
    module = load_function_app(monkeypatch, durable_enabled=False)

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
    assert summary_payload["recent_activity"] == []
    assert summary_payload["total_events"] == 0
    assert summary_payload["unique_sessions"] == 0
    assert summary_payload["route_counts"] == []
    assert summary_payload["site_mode_counts"] == []


def test_public_cost_routes_return_sanitized_history_payloads(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The public cost routes should expose the latest JSON and CSV history."""

    history_directory = tmp_path / "cost-history"
    create_cost_history_fixture(history_directory)
    monkeypatch.setenv("DOCINT_PUBLIC_COST_HISTORY_DIRECTORY", str(history_directory))
    module = load_function_app(monkeypatch, durable_enabled=False)

    summary_request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/public-cost-summary",
        headers={},
        params={},
        route_params={},
        body=b"",
    )
    latest_request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/public-cost-latest",
        headers={},
        params={},
        route_params={},
        body=b"",
    )
    history_request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/public-cost-history",
        headers={},
        params={},
        route_params={},
        body=b"",
    )

    summary_response = module.get_public_cost_summary(summary_request)
    latest_response = module.get_public_cost_latest(latest_request)
    history_response = module.get_public_cost_history(history_request)

    summary_payload = json.loads(summary_response.get_body().decode("utf-8"))
    latest_payload = json.loads(latest_response.get_body().decode("utf-8"))
    history_payload = history_response.get_body().decode("utf-8")

    assert summary_response.status_code == 200
    assert summary_payload["collection_mode"] == "Durable public-safe cost history"
    assert summary_payload["history_row_count"] == 4
    assert summary_payload["today_cost"] == 24.5
    assert summary_payload["week_to_date_cost"] == 104.75
    assert summary_payload["month_to_date_cost"] == 184.5
    assert summary_payload["year_to_date_cost"] == 612.25
    assert summary_payload["daily_cost_trend"][-1]["label"] == "Apr 20"
    assert summary_payload["top_resources"] == [
        {"amount": 57.5, "name": "Public API application"}
    ]
    assert latest_response.status_code == 200
    assert latest_payload["costSummary"]["yesterday_cost"] == 22.5
    assert latest_payload["costSummary"]["top_resources"] == [
        {"amount": 57.5, "name": "Public API application"}
    ]
    assert history_response.status_code == 200
    assert history_response.mimetype == "text/csv"
    assert "generated_at,currency,today_cost,week_to_date_cost" in history_payload
    assert "Public API application" in history_payload


def test_public_site_verifier_timer_runs_monitor_helper(
    monkeypatch: MonkeyPatch,
) -> None:
    """The scheduled timer should delegate to the public-site monitor helper."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import public_site_monitor

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

    assert captured["settings"] == module._get_settings()


def test_public_cost_refresh_timer_runs_refresh_helper(
    monkeypatch: MonkeyPatch,
) -> None:
    """The scheduled timer should delegate to the public cost refresh helper."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import public_cost_refresh

    captured: dict[str, object] = {}

    def fake_refresh_public_cost_history(settings: object) -> dict[str, object]:
        captured["settings"] = settings
        return {
            "history_row_count": 4,
            "ok": True,
            "status": "refreshed",
        }

    monkeypatch.setattr(
        public_cost_refresh,
        "refresh_public_cost_history",
        fake_refresh_public_cost_history,
    )

    module.run_public_cost_refresh(None)

    assert captured["settings"] == module._get_settings()


def test_review_items_require_admin_key_when_configured(
    monkeypatch: MonkeyPatch,
) -> None:
    """Configured review API keys should block direct anonymous access."""
    monkeypatch.setenv("DOCINT_REVIEW_API_ADMIN_KEY", "private-admin-key")
    module = load_function_app(monkeypatch, durable_enabled=False)

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/review-items",
        headers={},
        params={},
        route_params={},
        body=b"",
    )

    response = module.list_review_items(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 401
    assert payload == {
        "message": "Review API access requires the configured admin key.",
        "status": "unauthorized",
    }


def test_review_items_allow_admin_key_before_repository_checks(
    monkeypatch: MonkeyPatch,
) -> None:
    """Requests with the admin key should continue into normal repository checks."""
    monkeypatch.setenv("DOCINT_REVIEW_API_ADMIN_KEY", "private-admin-key")
    monkeypatch.delenv("DOCINT_COSMOS_ENDPOINT", raising=False)
    monkeypatch.delenv("DOCINT_COSMOS_KEY", raising=False)
    module = load_function_app(monkeypatch, durable_enabled=False)

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/review-items",
        headers={"x-docint-admin-key": "private-admin-key"},
        params={},
        route_params={},
        body=b"",
    )

    response = module.list_review_items(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 503
    assert payload == {
        "message": "Cosmos DB review storage is not configured.",
        "status": "configuration_required",
    }


def test_create_manual_packet_returns_created_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """Manual packet intake should return the created packet payload."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import manual_intake
    from document_intelligence.models import (
        DocumentSource,
        ManualPacketDocumentRecord,
        ManualPacketIntakeResponse,
    )

    def fake_create_manual_packet_intake(
        request: object,
        settings: object,
    ) -> ManualPacketIntakeResponse:
        del request, settings
        return ManualPacketIntakeResponse(
            packet_id="pkt_demo_001",
            packet_name="demo packet",
            source=DocumentSource.SCANNED_UPLOAD,
            source_uri="manual://packets/pkt_demo_001",
            submitted_by="operator@example.com",
            document_count=1,
            received_at_utc=datetime(2026, 4, 4, 12, 0, tzinfo=UTC),
            documents=(
                ManualPacketDocumentRecord(
                    document_id="doc_demo_001",
                    file_name="sample.pdf",
                    content_type="application/pdf",
                    blob_uri="https://storage.example/raw/sample.pdf",
                    file_hash_sha256="8d74e7eed6a76016ff7858d11d2f74c07a814e3cd3f81c4b6cf2e5f0376ea9d4",
                    processing_job_id="job_demo_001",
                ),
            ),
        )

    monkeypatch.setattr(
        manual_intake,
        "create_manual_packet_intake",
        fake_create_manual_packet_intake,
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/packets/manual-intake",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={},
        body=json.dumps(
            {
                "packet_name": "demo packet",
                "source": "scanned_upload",
                "submitted_by": "operator@example.com",
                "documents": [
                    {
                        "file_name": "sample.pdf",
                        "content_type": "application/pdf",
                        "document_content_base64": "JVBERi0xLjQ=",
                    }
                ],
            }
        ).encode("utf-8"),
    )

    response = module.create_manual_packet(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 201
    assert payload["packet_id"] == "pkt_demo_001"
    assert payload["document_count"] == 1


def test_run_packet_classification_returns_execution_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The packet classification route should return the execution summary."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import packet_classification
    from document_intelligence.models import (
        ClassificationResultSource,
        PacketClassificationExecutionDocumentResult,
        PacketClassificationExecutionResponse,
        PacketStatus,
        ProcessingStageName,
        PromptProfileId,
    )

    def fake_execute_packet_classification_stage(
        packet_id: str,
        settings: object,
    ) -> PacketClassificationExecutionResponse:
        del settings
        return PacketClassificationExecutionResponse(
            executed_document_count=1,
            next_stage=ProcessingStageName.OCR,
            packet_id=packet_id,
            processed_documents=(
                PacketClassificationExecutionDocumentResult(
                    classification_id="cls_bank_correspondence",
                    classification_job_id="job_cls_001",
                    classification_result_id="clsr_001",
                    document_id="doc_child_001",
                    document_type_id="doc_bank_statement",
                    ocr_job_id="job_ocr_001",
                    packet_id=packet_id,
                    prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                    result_source=ClassificationResultSource.RULE,
                    status=PacketStatus.OCR_RUNNING,
                ),
            ),
            skipped_document_ids=("doc_parent_001",),
            status=PacketStatus.OCR_RUNNING,
        )

    monkeypatch.setattr(
        packet_classification,
        "execute_packet_classification_stage",
        fake_execute_packet_classification_stage,
    )

    request = func.HttpRequest(
        method="POST",
        url=(
            "http://localhost/api/packets/pkt_archive_001/classification/execute"
        ),
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"packet_id": "pkt_archive_001"},
        body=b"",
    )

    response = module.run_packet_classification(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["packet_id"] == "pkt_archive_001"
    assert payload["status"] == "ocr_running"
    assert payload["next_stage"] == "ocr"
    assert payload["processed_documents"][0]["classification_id"] == (
        "cls_bank_correspondence"
    )


def test_run_packet_ocr_returns_execution_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The packet OCR route should return the execution summary."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import packet_ocr
    from document_intelligence.models import (
        ExtractionStrategySelection,
        PacketOcrExecutionDocumentResult,
        PacketOcrExecutionResponse,
        PacketStatus,
        ProcessingStageName,
        PromptProfileId,
    )

    def fake_execute_packet_ocr_stage(
        packet_id: str,
        settings: object,
    ) -> PacketOcrExecutionResponse:
        del settings
        return PacketOcrExecutionResponse(
            executed_document_count=1,
            next_stage=ProcessingStageName.EXTRACTION,
            packet_id=packet_id,
            processed_documents=(
                PacketOcrExecutionDocumentResult(
                    classification_result_id="clsr_001",
                    document_id="doc_child_001",
                    extraction_job_id="job_ext_001",
                    extraction_strategy=ExtractionStrategySelection(
                        classification_result_id="clsr_001",
                        document_type_id="doc_bank_statement",
                        document_type_key="bank_statement",
                        matching_path="account_number_lookup",
                        prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                        required_fields=("account_number", "statement_date"),
                        strategy_source="classification_contract",
                    ),
                    ocr_confidence=0.94,
                    ocr_job_id="job_ocr_001",
                    ocr_result_id="ocr_001",
                    packet_id=packet_id,
                    page_count=2,
                    provider="azure_document_intelligence",
                    status=PacketStatus.EXTRACTING,
                    text_storage_uri="https://storage.example/ocr/ocr_001.txt",
                ),
            ),
            skipped_document_ids=("doc_parent_001",),
            status=PacketStatus.EXTRACTING,
        )

    monkeypatch.setattr(
        packet_ocr,
        "execute_packet_ocr_stage",
        fake_execute_packet_ocr_stage,
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/packets/pkt_archive_001/ocr/execute",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"packet_id": "pkt_archive_001"},
        body=b"",
    )

    response = module.run_packet_ocr(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["packet_id"] == "pkt_archive_001"
    assert payload["status"] == "extracting"
    assert payload["next_stage"] == "extraction"
    assert payload["processed_documents"][0]["ocr_result_id"] == "ocr_001"
    assert payload["processed_documents"][0]["extraction_strategy"] == {
        "classification_result_id": "clsr_001",
        "document_type_id": "doc_bank_statement",
        "document_type_key": "bank_statement",
        "matching_path": "account_number_lookup",
        "prompt_profile_id": "bank_statement",
        "required_fields": ["account_number", "statement_date"],
        "strategy_source": "classification_contract",
    }


def test_run_packet_extraction_returns_execution_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The packet extraction route should return the execution summary."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import packet_extraction
    from document_intelligence.models import (
        AccountMatchResult,
        AccountMatchStatus,
        ExtractionStrategySelection,
        PacketExtractionExecutionDocumentResult,
        PacketExtractionExecutionResponse,
        PacketStatus,
        ProcessingStageName,
        PromptProfileId,
        ReviewDecision,
    )

    def fake_execute_packet_extraction_stage(
        packet_id: str,
        settings: object,
    ) -> PacketExtractionExecutionResponse:
        del settings
        return PacketExtractionExecutionResponse(
            executed_document_count=1,
            next_stage=ProcessingStageName.RECOMMENDATION,
            packet_id=packet_id,
            processed_documents=(
                PacketExtractionExecutionDocumentResult(
                    account_match=AccountMatchResult(
                        candidates=(),
                        rationale="Matched to a single request candidate.",
                        selected_account_id="acct_123",
                        status=AccountMatchStatus.MATCHED,
                    ),
                    classification_result_id="clsr_001",
                    document_id="doc_child_001",
                    extraction_job_id="job_ext_001",
                    extraction_result_id="ext_001",
                    extraction_strategy=ExtractionStrategySelection(
                        classification_result_id="clsr_001",
                        document_type_id="doc_bank_statement",
                        document_type_key="bank_statement",
                        matching_path="account_number_lookup",
                        prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                        required_fields=("account_number", "statement_date"),
                        strategy_source="classification_contract",
                    ),
                    match_run_id="match_001",
                    packet_id=packet_id,
                    prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                    recommendation_job_id="job_rec_001",
                    review_decision=ReviewDecision(
                        requires_manual_review=False,
                        reasons=(),
                        average_confidence=0.94,
                        minimum_confidence=0.91,
                        missing_required_fields=(),
                    ),
                    review_task_id=None,
                    selected_account_id="acct_123",
                    status=PacketStatus.READY_FOR_RECOMMENDATION,
                ),
            ),
            skipped_document_ids=("doc_parent_001",),
            status=PacketStatus.READY_FOR_RECOMMENDATION,
        )

    monkeypatch.setattr(
        packet_extraction,
        "execute_packet_extraction_stage",
        fake_execute_packet_extraction_stage,
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/packets/pkt_archive_001/extraction/execute",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"packet_id": "pkt_archive_001"},
        body=b"",
    )

    response = module.run_packet_extraction(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["packet_id"] == "pkt_archive_001"
    assert payload["status"] == "ready_for_recommendation"
    assert payload["next_stage"] == "recommendation"
    assert payload["processed_documents"][0]["extraction_result_id"] == "ext_001"
    assert payload["processed_documents"][0]["recommendation_job_id"] == (
        "job_rec_001"
    )
    assert payload["processed_documents"][0]["selected_account_id"] == "acct_123"


def test_run_packet_recommendation_returns_execution_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The packet recommendation route should return the execution summary."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import packet_recommendation
    from document_intelligence.models import (
        PacketRecommendationExecutionDocumentResult,
        PacketRecommendationExecutionResponse,
        PacketStatus,
        ProcessingStageName,
        RecommendationDisposition,
    )

    def fake_execute_packet_recommendation_stage(
        packet_id: str,
        settings: object,
    ) -> PacketRecommendationExecutionResponse:
        del settings
        return PacketRecommendationExecutionResponse(
            executed_document_count=1,
            next_stage=ProcessingStageName.RECOMMENDATION,
            packet_id=packet_id,
            processed_documents=(
                PacketRecommendationExecutionDocumentResult(
                    classification_prior_id="prior_001",
                    classification_result_id="clsr_001",
                    confidence=0.94,
                    disposition=RecommendationDisposition.PENDING,
                    document_id="doc_child_001",
                    packet_id=packet_id,
                    recommendation_job_id="job_rec_001",
                    recommendation_kind="bank_statement",
                    recommendation_result_id="recres_001",
                    recommendation_run_id="recrun_001",
                    selected_account_id="acct_123",
                    status=PacketStatus.COMPLETED,
                    summary=(
                        "Recommendation-ready evidence: statement.pdf, "
                        "bank_statement, linked to acct_123"
                    ),
                ),
            ),
            skipped_document_ids=("doc_parent_001",),
            status=PacketStatus.COMPLETED,
        )

    monkeypatch.setattr(
        packet_recommendation,
        "execute_packet_recommendation_stage",
        fake_execute_packet_recommendation_stage,
    )

    request = func.HttpRequest(
        method="POST",
        url=(
            "http://localhost/api/packets/pkt_archive_001/recommendation/execute"
        ),
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"packet_id": "pkt_archive_001"},
        body=b"",
    )

    response = module.run_packet_recommendation(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["packet_id"] == "pkt_archive_001"
    assert payload["status"] == "completed"
    assert payload["processed_documents"][0]["recommendation_result_id"] == (
        "recres_001"
    )


def test_apply_packet_review_decision_returns_execution_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The packet review-decision route should return the SQL-backed response."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import packet_review
    from document_intelligence.models import (
        PacketReviewDecisionResponse,
        PacketStatus,
        ReviewDecisionRecord,
        ReviewStatus,
    )

    def fake_apply_packet_review_decision(
        review_task_id: str,
        request: object,
        settings: object,
    ) -> PacketReviewDecisionResponse:
        del request, settings
        return PacketReviewDecisionResponse(
            decision=ReviewDecisionRecord(
                decision_id="decision_001",
                review_task_id=review_task_id,
                packet_id="pkt_archive_001",
                document_id="doc_child_001",
                decision_status=ReviewStatus.APPROVED,
                decision_reason_code=None,
                selected_account_id="acct_123",
                review_notes="Approved from the packet workspace.",
                decided_by_user_id=None,
                decided_by_email="reviewer@example.com",
                decided_at_utc=datetime(2026, 4, 10, 14, 0, tzinfo=UTC),
            ),
            document_status=PacketStatus.READY_FOR_RECOMMENDATION,
            operator_note=None,
            packet_id="pkt_archive_001",
            packet_status=PacketStatus.READY_FOR_RECOMMENDATION,
            queued_recommendation_job_id="job_rec_001",
            review_task_id=review_task_id,
            review_task_status=PacketStatus.READY_FOR_RECOMMENDATION,
        )

    monkeypatch.setattr(
        packet_review,
        "apply_packet_review_decision",
        fake_apply_packet_review_decision,
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/review-tasks/task_001/decision",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"review_task_id": "task_001"},
        body=json.dumps(
            {
                "decision_status": "approved",
                "decided_by_email": "reviewer@example.com",
                "expected_row_version": "0000000000000001",
                "review_notes": "Approved from the packet workspace.",
                "selected_account_id": "acct_123",
            }
        ).encode("utf-8"),
    )

    response = module.apply_packet_review_decision(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["review_task_id"] == "task_001"
    assert payload["packet_status"] == "ready_for_recommendation"
    assert payload["queued_recommendation_job_id"] == "job_rec_001"
    assert payload["decision"]["decision_status"] == "approved"


def test_apply_packet_review_assignment_returns_execution_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The review-task assignment route should return the persisted assignee."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import packet_review
    from document_intelligence.models import PacketReviewAssignmentResponse

    def fake_apply_packet_review_assignment(
        review_task_id: str,
        request: object,
        settings: object,
    ) -> PacketReviewAssignmentResponse:
        del settings
        return PacketReviewAssignmentResponse(
            assigned_user_email=getattr(request, "assigned_user_email"),
            assigned_user_id=getattr(request, "assigned_user_id"),
            packet_id="pkt_archive_001",
            review_task_id=review_task_id,
        )

    monkeypatch.setattr(
        packet_review,
        "apply_packet_review_assignment",
        fake_apply_packet_review_assignment,
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/review-tasks/task_001/assignment",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"review_task_id": "task_001"},
        body=json.dumps(
            {
                "assigned_by_email": "lead.reviewer@example.com",
                "assigned_user_email": "qa.reviewer@example.com",
                "expected_row_version": "0000000000000001",
            }
        ).encode("utf-8"),
    )

    response = module.apply_packet_review_assignment(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload == {
        "assigned_user_email": "qa.reviewer@example.com",
        "assigned_user_id": None,
        "packet_id": "pkt_archive_001",
        "review_task_id": "task_001",
    }


def test_create_packet_review_task_returns_execution_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The review-task create route should return the created task ids."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import packet_review
    from document_intelligence.models import PacketReviewTaskCreateResponse

    def fake_create_packet_review_task(
        packet_id: str,
        document_id: str,
        request: object,
        settings: object,
    ) -> PacketReviewTaskCreateResponse:
        del request, settings
        return PacketReviewTaskCreateResponse(
            document_id=document_id,
            packet_id=packet_id,
            review_task_id="task_created_001",
        )

    monkeypatch.setattr(
        packet_review,
        "create_packet_review_task",
        fake_create_packet_review_task,
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/packets/pkt_archive_001/documents/doc_child_001/review-tasks",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"packet_id": "pkt_archive_001", "document_id": "doc_child_001"},
        body=json.dumps(
            {
                "created_by_email": "lead.reviewer@example.com",
                "notes_summary": "Manual follow-up requested from the protected review tab.",
            }
        ).encode("utf-8"),
    )

    response = module.create_packet_review_task(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload == {
        "document_id": "doc_child_001",
        "packet_id": "pkt_archive_001",
        "review_task_id": "task_created_001",
    }


def test_apply_packet_review_extraction_edits_returns_execution_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The extraction edit route should return the SQL-backed edit response."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import packet_review
    from document_intelligence.models import (
        AuditEventRecord,
        ExtractionFieldChangeRecord,
        ExtractionResultRecord,
        PacketReviewExtractionEditResponse,
    )

    def fake_apply_packet_review_extraction_edits(
        review_task_id: str,
        request: object,
        settings: object,
    ) -> PacketReviewExtractionEditResponse:
        del request, settings
        return PacketReviewExtractionEditResponse(
            audit_event=AuditEventRecord(
                actor_email="reviewer@example.com",
                actor_user_id=None,
                audit_event_id=401,
                created_at_utc=datetime(2026, 4, 10, 14, 5, tzinfo=UTC),
                document_id="doc_child_001",
                event_payload={"changedFieldCount": 1},
                event_type="review.extraction.fields.updated",
                packet_id="pkt_archive_001",
                review_task_id=review_task_id,
            ),
            changed_fields=(
                ExtractionFieldChangeRecord(
                    confidence=0.94,
                    current_value="5678",
                    field_name="account_number",
                    original_value="1234",
                ),
            ),
            document_id="doc_child_001",
            extraction_result=ExtractionResultRecord(
                created_at_utc=datetime(2026, 4, 10, 14, 5, tzinfo=UTC),
                document_id="doc_child_001",
                document_type="bank_statement",
                extraction_result_id="ext_002",
                model_name="gpt-5.4",
                packet_id="pkt_archive_001",
                prompt_profile_id="bank_statement",
                provider="azure_openai",
                result_payload={
                    "extractedFields": [
                        {
                            "name": "account_number",
                            "value": "5678",
                        }
                    ]
                },
                summary="Updated extraction result.",
            ),
            packet_id="pkt_archive_001",
            review_task_id=review_task_id,
        )

    monkeypatch.setattr(
        packet_review,
        "apply_packet_review_extraction_edits",
        fake_apply_packet_review_extraction_edits,
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/review-tasks/task_001/extraction-edits",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"review_task_id": "task_001"},
        body=json.dumps(
            {
                "edited_by_email": "reviewer@example.com",
                "expected_row_version": "0000000000000001",
                "field_edits": [
                    {
                        "field_name": "account_number",
                        "value": "5678",
                    }
                ],
            }
        ).encode("utf-8"),
    )

    response = module.apply_packet_review_extraction_edits(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["review_task_id"] == "task_001"
    assert payload["changed_fields"][0]["field_name"] == "account_number"
    assert payload["extraction_result"]["extraction_result_id"] == "ext_002"


def test_apply_packet_review_note_returns_execution_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The review-task note route should return the SQL-backed note response."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import packet_review
    from document_intelligence.models import (
        OperatorNoteRecord,
        PacketReviewNoteResponse,
    )

    def fake_apply_packet_review_note(
        review_task_id: str,
        request: object,
        settings: object,
    ) -> PacketReviewNoteResponse:
        del request, settings
        return PacketReviewNoteResponse(
            operator_note=OperatorNoteRecord(
                created_at_utc=datetime(2026, 4, 10, 14, 10, tzinfo=UTC),
                created_by_email="reviewer@example.com",
                created_by_user_id=None,
                document_id="doc_child_001",
                is_private=False,
                note_id="note_001",
                note_text="Need one more statement page before approval.",
                packet_id="pkt_archive_001",
                review_task_id=review_task_id,
            ),
            packet_id="pkt_archive_001",
            review_task_id=review_task_id,
        )

    monkeypatch.setattr(
        packet_review,
        "apply_packet_review_note",
        fake_apply_packet_review_note,
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/review-tasks/task_001/notes",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"review_task_id": "task_001"},
        body=json.dumps(
            {
                "created_by_email": "reviewer@example.com",
                "expected_row_version": "0000000000000001",
                "note_text": "Need one more statement page before approval.",
            }
        ).encode("utf-8"),
    )

    response = module.apply_packet_review_note(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["review_task_id"] == "task_001"
    assert payload["packet_id"] == "pkt_archive_001"
    assert payload["operator_note"]["note_text"] == (
        "Need one more statement page before approval."
    )


def test_list_intake_sources_returns_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The intake-source list route should return the SQL-backed payload."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import intake_sources
    from document_intelligence.models import (
        IntakeSourceListResponse,
        IntakeSourceRecord,
        WatchedBlobPrefixSourceConfiguration,
    )

    monkeypatch.setattr(
        intake_sources,
        "list_intake_sources",
        lambda settings: IntakeSourceListResponse(
            items=(
                IntakeSourceRecord(
                    source_id="src_ops_blob",
                    source_name="Ops blob watcher",
                    is_enabled=True,
                    polling_interval_minutes=5,
                    credentials_reference="kv://storage/ops-watcher",
                    configuration=WatchedBlobPrefixSourceConfiguration(
                        storage_account_name="stdocdev123",
                        container_name="raw-documents",
                        blob_prefix="ops/inbox/",
                    ),
                    created_at_utc=datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                    updated_at_utc=datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                ),
            )
        ),
    )

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/intake-sources",
        headers={},
        params={},
        route_params={},
        body=b"",
    )

    response = module.list_intake_sources(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["items"][0]["source_id"] == "src_ops_blob"
    assert payload["items"][0]["configuration"]["source_kind"] == (
        "watched_blob_prefix"
    )


def test_create_intake_source_returns_created_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The intake-source create route should return the persisted payload."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import intake_sources
    from document_intelligence.models import (
        IntakeSourceRecord,
        PartnerApiFeedSourceConfiguration,
    )

    def fake_create_intake_source(
        request: object,
        settings: object,
    ) -> IntakeSourceRecord:
        del request, settings
        return IntakeSourceRecord(
            source_id="src_partner_001",
            source_name="County referrals",
            description="Inbound partner referral webhook",
            is_enabled=True,
            owner_email="ops@example.com",
            credentials_reference="kv://partner/referrals",
            configuration=PartnerApiFeedSourceConfiguration(
                partner_name="County court partner",
                relative_path="/api/intake/partner-referrals/v1",
                auth_scheme="hmac",
            ),
            created_at_utc=datetime(2026, 4, 5, 13, 0, tzinfo=UTC),
            updated_at_utc=datetime(2026, 4, 5, 13, 0, tzinfo=UTC),
        )

    monkeypatch.setattr(
        intake_sources,
        "create_intake_source",
        fake_create_intake_source,
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/intake-sources",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={},
        body=json.dumps(
            {
                "source_name": "County referrals",
                "description": "Inbound partner referral webhook",
                "owner_email": "ops@example.com",
                "credentials_reference": "kv://partner/referrals",
                "configuration": {
                    "source_kind": "partner_api_feed",
                    "partner_name": "County court partner",
                    "relative_path": "/api/intake/partner-referrals/v1",
                    "auth_scheme": "hmac",
                },
            }
        ).encode("utf-8"),
    )

    response = module.create_intake_source(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 201
    assert payload["source_id"] == "src_partner_001"
    assert payload["configuration"]["source_kind"] == "partner_api_feed"


def test_update_intake_source_returns_updated_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The intake-source update route should return the persisted payload."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import intake_sources
    from document_intelligence.models import (
        IntakeSourceRecord,
        WatchedBlobPrefixSourceConfiguration,
    )

    def fake_update_intake_source(
        source_id: str,
        request: object,
        settings: object,
    ) -> IntakeSourceRecord:
        del request, settings
        assert source_id == "src_ops_blob"
        return IntakeSourceRecord(
            source_id=source_id,
            source_name="Ops blob watcher",
            description="Updated blob source",
            is_enabled=True,
            owner_email="ops@example.com",
            polling_interval_minutes=10,
            configuration=WatchedBlobPrefixSourceConfiguration(
                storage_account_name="stdocdev123",
                container_name="raw-documents",
                blob_prefix="ops/updated/",
            ),
            created_at_utc=datetime(2026, 4, 5, 13, 0, tzinfo=UTC),
            updated_at_utc=datetime(2026, 4, 6, 13, 0, tzinfo=UTC),
        )

    monkeypatch.setattr(
        intake_sources,
        "update_intake_source",
        fake_update_intake_source,
    )

    request = func.HttpRequest(
        method="PUT",
        url="http://localhost/api/intake-sources/src_ops_blob",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"source_id": "src_ops_blob"},
        body=json.dumps(
            {
                "source_name": "Ops blob watcher",
                "description": "Updated blob source",
                "owner_email": "ops@example.com",
                "polling_interval_minutes": 10,
                "configuration": {
                    "source_kind": "watched_blob_prefix",
                    "storage_account_name": "stdocdev123",
                    "container_name": "raw-documents",
                    "blob_prefix": "ops/updated/",
                },
            }
        ).encode("utf-8"),
    )

    response = module.update_intake_source(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["source_id"] == "src_ops_blob"
    assert payload["description"] == "Updated blob source"
    assert payload["configuration"]["blob_prefix"] == "ops/updated/"


def test_set_intake_source_enablement_returns_updated_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The intake-source enablement route should return the toggled payload."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import intake_sources
    from document_intelligence.models import (
        IntakeSourceRecord,
        WatchedBlobPrefixSourceConfiguration,
    )

    def fake_set_intake_source_enablement(
        source_id: str,
        request: object,
        settings: object,
    ) -> IntakeSourceRecord:
        del request, settings
        assert source_id == "src_ops_blob"
        return IntakeSourceRecord(
            source_id=source_id,
            source_name="Ops blob watcher",
            is_enabled=False,
            configuration=WatchedBlobPrefixSourceConfiguration(
                storage_account_name="stdocdev123",
                container_name="raw-documents",
                blob_prefix="ops/inbox/",
            ),
            created_at_utc=datetime(2026, 4, 5, 13, 0, tzinfo=UTC),
            updated_at_utc=datetime(2026, 4, 6, 14, 0, tzinfo=UTC),
        )

    monkeypatch.setattr(
        intake_sources,
        "set_intake_source_enablement",
        fake_set_intake_source_enablement,
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/intake-sources/src_ops_blob/enablement",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"source_id": "src_ops_blob"},
        body=json.dumps({"is_enabled": False}).encode("utf-8"),
    )

    response = module.set_intake_source_enablement(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["source_id"] == "src_ops_blob"
    assert payload["is_enabled"] is False


def test_delete_intake_source_returns_deleted_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The intake-source delete route should return the deleted summary."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import intake_sources
    from document_intelligence.models import IntakeSourceDeleteResponse

    monkeypatch.setattr(
        intake_sources,
        "delete_intake_source",
        lambda source_id, settings: IntakeSourceDeleteResponse(
            source_id=source_id,
            source_name="Ops blob watcher",
        ),
    )

    request = func.HttpRequest(
        method="DELETE",
        url="http://localhost/api/intake-sources/src_ops_blob",
        headers={},
        params={},
        route_params={"source_id": "src_ops_blob"},
        body=b"",
    )

    response = module.delete_intake_source(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload == {
        "deleted": True,
        "source_id": "src_ops_blob",
        "source_name": "Ops blob watcher",
    }


def test_ingest_partner_intake_source_returns_created_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """Partner source ingestion should return the created packet payload."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import intake_sources
    from document_intelligence.models import (
        DocumentSource,
        ManualPacketDocumentRecord,
        ManualPacketIntakeResponse,
    )

    def fake_ingest_partner_source_packet(
        source_id: str,
        request: object,
        settings: object,
    ) -> ManualPacketIntakeResponse:
        del request, settings
        assert source_id == "src_partner_001"
        return ManualPacketIntakeResponse(
            packet_id="pkt_partner_001",
            packet_name="county-referral-1001",
            source=DocumentSource.PARTNER_API_FEED,
            source_uri="partner://src_partner_001/api/intake/partner-referrals/v1",
            submitted_by="partners@example.com",
            document_count=1,
            received_at_utc=datetime(2026, 4, 7, 12, 0, tzinfo=UTC),
            documents=(
                ManualPacketDocumentRecord(
                    document_id="doc_partner_001",
                    file_name="referral.pdf",
                    content_type="application/pdf",
                    blob_uri="https://storage.example/raw/referral.pdf",
                    file_hash_sha256=(
                        "8d74e7eed6a76016ff7858d11d2f74c07a814e3cd3f81c4b6cf2e5f0376ea9d4"
                    ),
                    processing_job_id="job_partner_001",
                ),
            ),
        )

    monkeypatch.setattr(
        intake_sources,
        "ingest_partner_source_packet",
        fake_ingest_partner_source_packet,
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/intake-sources/src_partner_001/ingest",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"source_id": "src_partner_001"},
        body=json.dumps(
            {
                "packet_name": "county-referral-1001",
                "documents": [
                    {
                        "file_name": "referral.pdf",
                        "content_type": "application/pdf",
                        "document_content_base64": "JVBERi0xLjQ=",
                    }
                ],
            }
        ).encode("utf-8"),
    )

    response = module.ingest_partner_intake_source(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 201
    assert payload["packet_id"] == "pkt_partner_001"
    assert payload["source"] == "partner_api_feed"


def test_run_intake_source_returns_execution_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The intake-source execution route should return the watched blob result."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    from document_intelligence import intake_sources
    from document_intelligence.models import (
        DuplicateDetectionStatus,
        IntakeSourceExecutionPacketResult,
        IntakeSourceExecutionResponse,
        IntakeSourceKind,
        PacketStatus,
    )

    monkeypatch.setattr(
        intake_sources,
        "execute_intake_source",
        lambda source_id, settings: IntakeSourceExecutionResponse(
            executed_at_utc=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            packet_results=(
                IntakeSourceExecutionPacketResult(
                    blob_name="ops/inbox/statement.pdf",
                    blob_uri=(
                        "https://storage.example/landing-documents/ops/inbox/statement.pdf"
                    ),
                    content_length_bytes=64,
                    content_type="application/pdf",
                    document_count=1,
                    duplicate_detection_status=DuplicateDetectionStatus.UNIQUE,
                    packet_id="pkt_blob_001",
                    packet_name="statement.pdf",
                    status=PacketStatus.RECEIVED,
                ),
            ),
            processed_blob_count=1,
            seen_blob_count=1,
            source_id=source_id,
            source_kind=IntakeSourceKind.WATCHED_BLOB_PREFIX,
            source_name="Ops blob watcher",
        ),
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/intake-sources/src_ops_blob/execute",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"source_id": "src_ops_blob"},
        body=b"",
    )

    response = module.run_intake_source(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["source_id"] == "src_ops_blob"
    assert payload["source_kind"] == "watched_blob_prefix"
    assert payload["packet_results"][0]["packet_id"] == "pkt_blob_001"


def test_get_processing_taxonomy_returns_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The processing-taxonomy route should return the canonical status contract."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    import document_intelligence.processing_taxonomy as taxonomy_service
    from document_intelligence.models import (
        PacketStatus,
        PacketStatusCategory,
        PacketStatusDefinition,
        ProcessingStageDefinition,
        ProcessingStageName,
        ProcessingTaxonomyResponse,
    )

    monkeypatch.setattr(
        taxonomy_service,
        "get_processing_taxonomy",
        lambda: ProcessingTaxonomyResponse(
            stages=(
                ProcessingStageDefinition(
                    stage_name=ProcessingStageName.CLASSIFICATION,
                    display_name="Classification",
                    description="Classify before extraction.",
                    statuses=(PacketStatus.CLASSIFYING,),
                ),
            ),
            statuses=(
                PacketStatusDefinition(
                    status=PacketStatus.CLASSIFYING,
                    display_name="Classifying",
                    description="Classification is running.",
                    category=PacketStatusCategory.ACTIVE,
                    stage_name=ProcessingStageName.CLASSIFICATION,
                ),
            ),
        ),
    )

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/processing-taxonomy",
        headers={},
        params={},
        route_params={},
        body=b"",
    )

    response = module.get_processing_taxonomy(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["statuses"][0]["status"] == "classifying"
    assert payload["stages"][0]["stage_name"] == "classification"


def test_get_packet_workspace_returns_snapshot_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The packet workspace route should return the SQL-backed snapshot."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    import document_intelligence.operator_state as operator_state
    from document_intelligence.models import (
        ArchiveDocumentLineage,
        ArchivePreflightDisposition,
        ArchivePreflightResult,
        DocumentSource,
        PacketDocumentRecord,
        PacketRecord,
        PacketStatus,
        PacketWorkspaceSnapshot,
        ReviewTaskPriority,
        ReviewTaskRecord,
    )

    class FakeRepository:
        """Repository stub that returns one packet workspace snapshot."""

        def __init__(self, settings: object) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self,
            packet_id: str,
        ) -> PacketWorkspaceSnapshot:
            return PacketWorkspaceSnapshot(
                packet=PacketRecord(
                    packet_id=packet_id,
                    packet_name="archive packet",
                    source=DocumentSource.SCANNED_UPLOAD,
                    status=PacketStatus.QUARANTINED,
                    received_at_utc=datetime(2026, 4, 5, 15, 0, tzinfo=UTC),
                    created_at_utc=datetime(2026, 4, 5, 15, 0, tzinfo=UTC),
                    updated_at_utc=datetime(2026, 4, 5, 15, 5, tzinfo=UTC),
                ),
                documents=(
                    PacketDocumentRecord(
                        document_id="doc_archive_child",
                        packet_id=packet_id,
                        file_name="unsupported.rar",
                        content_type="application/vnd.rar",
                        source=DocumentSource.SCANNED_UPLOAD,
                        status=PacketStatus.QUARANTINED,
                        archive_preflight=ArchivePreflightResult(
                            archive_format="rar",
                            disposition=(
                                ArchivePreflightDisposition.UNSUPPORTED_ARCHIVE
                            ),
                            is_archive=True,
                            message="Unsupported child archive.",
                        ),
                        lineage=ArchiveDocumentLineage(
                            archive_depth=1,
                            archive_member_path="nested/unsupported.rar",
                            parent_document_id="doc_archive_parent",
                            source_asset_id="asset_archive_parent",
                        ),
                        received_at_utc=datetime(2026, 4, 5, 15, 0, tzinfo=UTC),
                        created_at_utc=datetime(2026, 4, 5, 15, 0, tzinfo=UTC),
                        updated_at_utc=datetime(2026, 4, 5, 15, 1, tzinfo=UTC),
                    ),
                ),
                review_tasks=(
                    ReviewTaskRecord(
                        review_task_id="task_archive_001",
                        packet_id=packet_id,
                        document_id="doc_archive_child",
                        status=PacketStatus.AWAITING_REVIEW,
                        priority=ReviewTaskPriority.HIGH,
                        reason_codes=("archive_unsupported",),
                        notes_summary="Unsupported child archive.",
                        created_at_utc=datetime(2026, 4, 5, 15, 1, tzinfo=UTC),
                        row_version="00000000000000a1",
                        updated_at_utc=datetime(2026, 4, 5, 15, 1, tzinfo=UTC),
                    ),
                ),
            )

    monkeypatch.setattr(
        operator_state,
        "SqlOperatorStateRepository",
        FakeRepository,
    )

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/packets/pkt_archive_001/workspace",
        headers={},
        params={},
        route_params={"packet_id": "pkt_archive_001"},
        body=b"",
    )

    response = module.get_packet_workspace(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["packet"]["packet_id"] == "pkt_archive_001"
    assert payload["documents"][0]["lineage"]["parent_document_id"] == (
        "doc_archive_parent"
    )
    assert payload["documents"][0]["archive_preflight"]["disposition"] == (
        "unsupported_archive"
    )
    assert payload["review_tasks"][0]["reason_codes"] == ["archive_unsupported"]


def test_list_packet_queue_returns_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The packet queue route should return the paged SQL-backed queue payload."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    import document_intelligence.packet_queue as packet_queue_service
    from document_intelligence.models import (
        DocumentSource,
        IssuerCategory,
        PacketAssignmentState,
        PacketQueueItem,
        PacketQueueListResponse,
        PacketStatus,
        ProcessingJobStatus,
        ProcessingStageName,
    )

    captured: dict[str, object] = {}

    def fake_list_packet_queue(request: object, settings: object) -> PacketQueueListResponse:
        del settings
        captured["request"] = request
        return PacketQueueListResponse(
            items=(
                PacketQueueItem(
                    packet_id="pkt_demo_001",
                    packet_name="demo packet",
                    source=DocumentSource.SCANNED_UPLOAD,
                    source_uri="manual://packets/pkt_demo_001",
                    status=PacketStatus.AWAITING_REVIEW,
                    stage_name=ProcessingStageName.REVIEW,
                    document_count=2,
                    awaiting_review_document_count=1,
                    completed_document_count=0,
                    review_task_count=1,
                    assignment_state=PacketAssignmentState.ASSIGNED,
                    assigned_user_email="ops@example.com",
                    received_at_utc=datetime(2026, 4, 7, 8, 0, tzinfo=UTC),
                    updated_at_utc=datetime(2026, 4, 7, 8, 5, tzinfo=UTC),
                    primary_document_id="doc_demo_001",
                    primary_file_name="statement.pdf",
                    primary_issuer_name="Fabrikam Bank",
                    primary_issuer_category=IssuerCategory.BANK,
                    latest_job_stage_name=ProcessingStageName.EXTRACTION,
                    latest_job_status=ProcessingJobStatus.QUEUED,
                    classification_keys=("bank_correspondence",),
                    document_type_keys=("bank_statement",),
                    operator_note_count=1,
                    audit_event_count=3,
                    queue_age_hours=12.5,
                ),
            ),
            page=2,
            page_size=10,
            total_count=11,
            has_more=True,
        )

    monkeypatch.setattr(
        packet_queue_service,
        "list_packet_queue",
        fake_list_packet_queue,
    )

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/packets",
        headers={},
        params={
            "page": "2",
            "page_size": "10",
            "source": "scanned_upload",
            "stage_name": "review",
            "assigned_user_email": "ops@example.com",
        },
        route_params={},
        body=b"",
    )

    response = module.list_packet_queue(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["page"] == 2
    assert payload["page_size"] == 10
    assert payload["total_count"] == 11
    assert payload["has_more"] is True
    assert payload["items"][0]["packet_id"] == "pkt_demo_001"
    assert payload["items"][0]["stage_name"] == "review"
    assert payload["items"][0]["classification_keys"] == ["bank_correspondence"]
    typed_request = captured["request"]
    assert typed_request.page == 2
    assert typed_request.page_size == 10
    assert typed_request.source == DocumentSource.SCANNED_UPLOAD
    assert typed_request.stage_name == ProcessingStageName.REVIEW
    assert typed_request.assigned_user_email == "ops@example.com"


def test_get_packet_workspace_returns_not_found_for_missing_packet(
    monkeypatch: MonkeyPatch,
) -> None:
    """Missing packet workspace requests should translate to a 404 JSON payload."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    import document_intelligence.operator_state as operator_state

    class MissingPacketRepository:
        """Repository stub that raises the same missing-packet error as SQL."""

        def __init__(self, settings: object) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(self, packet_id: str) -> object:
            raise RuntimeError(f"Packet '{packet_id}' could not be loaded.")

    monkeypatch.setattr(
        operator_state,
        "SqlOperatorStateRepository",
        MissingPacketRepository,
    )

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/packets/pkt_missing/workspace",
        headers={},
        params={},
        route_params={"packet_id": "pkt_missing"},
        body=b"",
    )

    response = module.get_packet_workspace(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 404
    assert payload == {
        "status": "not_found",
        "message": "Packet 'pkt_missing' could not be loaded.",
    }


def test_get_packet_document_content_returns_binary_preview(
    monkeypatch: MonkeyPatch,
) -> None:
    """The protected document-preview route should return raw preview bytes."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    import document_intelligence.document_viewer as document_viewer

    monkeypatch.setattr(
        document_viewer,
        "get_packet_document_preview",
        lambda packet_id, document_id, settings: document_viewer.PacketDocumentPreview(
            content=b"%PDF-1.4 demo",
            content_type="application/pdf",
            file_name=f"{packet_id}-{document_id}.pdf",
        ),
    )

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/packets/pkt_archive_001/documents/doc_child_001/content",
        headers={},
        params={},
        route_params={
            "packet_id": "pkt_archive_001",
            "document_id": "doc_child_001",
        },
        body=b"",
    )

    response = module.get_packet_document_content(request)

    assert response.status_code == 200
    assert response.get_body() == b"%PDF-1.4 demo"


def test_get_packet_document_content_returns_forbidden_when_preview_is_blocked(
    monkeypatch: MonkeyPatch,
) -> None:
    """The protected document-preview route should reject quarantined documents."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    import document_intelligence.document_viewer as document_viewer

    monkeypatch.setattr(
        document_viewer,
        "get_packet_document_preview",
        lambda packet_id, document_id, settings: (_ for _ in ()).throw(
            document_viewer.DocumentPreviewPolicyError(
                f"Packet document '{document_id}' is quarantined and cannot be previewed."
            )
        ),
    )

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/packets/pkt_archive_001/documents/doc_child_001/content",
        headers={},
        params={},
        route_params={
            "packet_id": "pkt_archive_001",
            "document_id": "doc_child_001",
        },
        body=b"",
    )

    response = module.get_packet_document_content(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 403
    assert payload == {
        "status": "forbidden",
        "message": "Packet document 'doc_child_001' is quarantined and cannot be previewed.",
    }


def test_retry_packet_stage_returns_retry_summary(
    monkeypatch: MonkeyPatch,
) -> None:
    """The packet-stage retry route should return the retry execution summary."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    import document_intelligence.packet_pipeline_actions as packet_pipeline_actions
    from document_intelligence.models import (
        PacketStageRetryResponse,
        PacketStatus,
        ProcessingStageName,
    )

    monkeypatch.setattr(
        packet_pipeline_actions,
        "retry_packet_stage",
        lambda packet_id, stage_name, settings: PacketStageRetryResponse(
            executed_document_count=1,
            failed_job_count=1,
            next_stage=ProcessingStageName.RECOMMENDATION,
            packet_id=packet_id,
            requeued_document_count=1,
            skipped_document_ids=("doc_parent_001",),
            stage_name=ProcessingStageName(stage_name),
            stale_running_job_count=0,
            status=PacketStatus.READY_FOR_RECOMMENDATION,
        ),
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/packets/pkt_archive_001/stages/extraction/retry",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={
            "packet_id": "pkt_archive_001",
            "stage_name": "extraction",
        },
        body=b"",
    )

    response = module.retry_packet_stage(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload == {
        "executed_document_count": 1,
        "failed_job_count": 1,
        "next_stage": "recommendation",
        "packet_id": "pkt_archive_001",
        "requeued_document_count": 1,
        "skipped_document_ids": ["doc_parent_001"],
        "stage_name": "extraction",
        "stale_running_job_count": 0,
        "status": "ready_for_recommendation",
    }


def test_replay_packet_returns_execution_summary(
    monkeypatch: MonkeyPatch,
) -> None:
    """The packet replay route should return the replay execution summary."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    import document_intelligence.packet_replay as packet_replay
    from document_intelligence.models import (
        PacketReplayResponse,
        PacketStatus,
        ProcessingStageName,
    )

    monkeypatch.setattr(
        packet_replay,
        "replay_packet",
        lambda packet_id, settings: PacketReplayResponse(
            action="retry",
            executed_document_count=1,
            failed_job_count=1,
            message="Retried extraction for 1 document(s).",
            next_stage=ProcessingStageName.RECOMMENDATION,
            packet_id=packet_id,
            requeued_document_count=1,
            skipped_document_ids=("doc_parent_001",),
            stage_name=ProcessingStageName.EXTRACTION,
            stale_running_job_count=0,
            status=PacketStatus.READY_FOR_RECOMMENDATION,
        ),
    )

    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/packets/pkt_archive_001/replay",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={"packet_id": "pkt_archive_001"},
        body=b"",
    )

    response = module.replay_packet(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload == {
        "action": "retry",
        "executed_document_count": 1,
        "failed_job_count": 1,
        "message": "Retried extraction for 1 document(s).",
        "next_stage": "recommendation",
        "packet_id": "pkt_archive_001",
        "requeued_document_count": 1,
        "skipped_document_ids": ["doc_parent_001"],
        "stage_name": "extraction",
        "stale_running_job_count": 0,
        "status": "ready_for_recommendation",
    }


def test_review_packet_recommendation_returns_review_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The recommendation review route should return the reviewed result."""

    module = load_function_app(monkeypatch, durable_enabled=False)

    import document_intelligence.packet_recommendation_review as recommendation_review
    from document_intelligence.models import (
        PacketRecommendationReviewResponse,
        RecommendationDisposition,
        RecommendationResultRecord,
    )

    monkeypatch.setattr(
        recommendation_review,
        "review_packet_recommendation",
        lambda packet_id, recommendation_result_id, request, settings: (
            PacketRecommendationReviewResponse(
                packet_id=packet_id,
                recommendation_result=RecommendationResultRecord(
                    recommendation_result_id=recommendation_result_id,
                    recommendation_run_id="recrun_001",
                    packet_id=packet_id,
                    document_id="doc_demo_001",
                    recommendation_kind="settlement_offer",
                    summary="Offer a reduced payment plan.",
                    rationale_payload={"basis": "income verified"},
                    evidence_items=(),
                    confidence=0.91,
                    advisory_text="Recommend settlement outreach.",
                    disposition=RecommendationDisposition.ACCEPTED,
                    reviewed_by_user_id=request.reviewed_by_user_id,
                    reviewed_by_email=request.reviewed_by_email,
                    reviewed_at_utc=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
                    created_at_utc=datetime(2026, 4, 14, 9, 0, tzinfo=UTC),
                    updated_at_utc=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
                ),
            )
        ),
    )

    request = func.HttpRequest(
        method="POST",
        url=(
            "http://localhost/api/packets/pkt_demo_001/"
            "recommendation-results/recres_001/review"
        ),
        headers={"Content-Type": "application/json"},
        params={},
        route_params={
            "packet_id": "pkt_demo_001",
            "recommendation_result_id": "recres_001",
        },
        body=json.dumps(
            {
                "disposition": "accepted",
                "reviewed_by_email": "reviewer@example.com",
            }
        ).encode("utf-8"),
    )

    response = module.review_packet_recommendation(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["packet_id"] == "pkt_demo_001"
    assert payload["recommendation_result"]["recommendation_result_id"] == "recres_001"
    assert payload["recommendation_result"]["disposition"] == "accepted"


def test_get_operator_contracts_returns_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    """The operator-contracts route should return the managed SQL contract bundle."""
    module = load_function_app(monkeypatch, durable_enabled=False)

    import document_intelligence.operator_contracts as operator_contract_service
    from document_intelligence.models import (
        IssuerCategory,
        ManagedClassificationDefinitionRecord,
        ManagedDocumentTypeDefinitionRecord,
        ManagedPromptProfileRecord,
        OperatorContractsResponse,
        ProcessingTaxonomyResponse,
        PromptProfileId,
        PromptProfileVersionRecord,
        RecommendationContractDefinition,
    )

    monkeypatch.setattr(
        operator_contract_service,
        "get_operator_contracts",
        lambda settings: OperatorContractsResponse(
            classification_definitions=(
                ManagedClassificationDefinitionRecord(
                    classification_id="cls_bank_correspondence",
                    classification_key="bank_correspondence",
                    display_name="Bank Correspondence",
                    issuer_category=IssuerCategory.BANK,
                    default_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                    created_at_utc=datetime(2026, 4, 5, 14, 0, tzinfo=UTC),
                    updated_at_utc=datetime(2026, 4, 5, 14, 0, tzinfo=UTC),
                ),
            ),
            document_type_definitions=(
                ManagedDocumentTypeDefinitionRecord(
                    document_type_id="doc_bank_statement",
                    document_type_key="bank_statement",
                    display_name="Bank Statement",
                    classification_id="cls_bank_correspondence",
                    default_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                    required_fields=("account_number", "statement_date"),
                    created_at_utc=datetime(2026, 4, 5, 14, 0, tzinfo=UTC),
                    updated_at_utc=datetime(2026, 4, 5, 14, 0, tzinfo=UTC),
                ),
            ),
            processing_taxonomy=ProcessingTaxonomyResponse(),
            prompt_profiles=(
                ManagedPromptProfileRecord(
                    prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                    display_name="Bank Statement",
                    issuer_category=IssuerCategory.BANK,
                    created_at_utc=datetime(2026, 4, 5, 14, 0, tzinfo=UTC),
                    updated_at_utc=datetime(2026, 4, 5, 14, 0, tzinfo=UTC),
                ),
            ),
            prompt_profile_versions=(
                PromptProfileVersionRecord(
                    prompt_profile_version_id="ppv_bank_statement_v1",
                    prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                    version_number=1,
                    definition_payload={"requiredFields": ["account_number"]},
                    created_at_utc=datetime(2026, 4, 5, 14, 0, tzinfo=UTC),
                ),
            ),
            recommendation_contract=RecommendationContractDefinition(),
        ),
    )

    request = func.HttpRequest(
        method="GET",
        url="http://localhost/api/operator-contracts",
        headers={},
        params={},
        route_params={},
        body=b"",
    )

    response = module.get_operator_contracts(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["classification_definitions"][0]["classification_key"] == (
        "bank_correspondence"
    )
    assert payload["document_type_definitions"][0]["document_type_key"] == (
        "bank_statement"
    )
    assert payload["prompt_profiles"][0]["prompt_profile_id"] == "bank_statement"


def test_sync_ingestion_returns_completed_payload_when_durable_disabled(
    monkeypatch: MonkeyPatch,
) -> None:
    """The Flex-safe ingestion path should return a completed workflow payload."""
    for name in (
        "DOCINT_AZURE_OPENAI_ENDPOINT",
        "DOCINT_AZURE_OPENAI_API_KEY",
        "DOCINT_COSMOS_ENDPOINT",
        "DOCINT_COSMOS_KEY",
        "DOCINT_DOCUMENT_INTELLIGENCE_ENDPOINT",
        "DOCINT_DOCUMENT_INTELLIGENCE_KEY",
        "DOCINT_SERVICE_BUS_CONNECTION_STRING",
        "DOCINT_SQL_CONNECTION_STRING",
    ):
        monkeypatch.delenv(name, raising=False)

    module = load_function_app(monkeypatch, durable_enabled=False)
    request = func.HttpRequest(
        method="POST",
        url="http://localhost/api/ingestions",
        headers={"Content-Type": "application/json"},
        params={},
        route_params={},
        body=json.dumps(
            {
                "content_type": "image/png",
                "document_id": "doc-3001",
                "document_text": (
                    "Validation notice for Jordan Patel with disputed account balance."
                ),
                "extracted_fields": [
                    {
                        "confidence": 0.91,
                        "name": "debtor_name",
                        "value": "Jordan Patel",
                    }
                ],
                "file_name": "letter-001.png",
                "issuer_category": "collection_agency",
                "received_at_utc": "2026-04-01T15:00:00+00:00",
                "source": "scanned_upload",
                "source_uri": "scan://box-03/letter-001",
            }
        ).encode("utf-8"),
    )

    response = module.start_ingestion(request)
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["runtimeStatus"] == "Completed"
    assert payload["workflowMode"] == "synchronous"
    assert payload["output"]["document_id"] == "doc-3001"
    assert payload["output"]["target_status"] == "pending_review"