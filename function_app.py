"""Azure Functions entrypoints for the document intelligence platform."""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
from collections.abc import Generator
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

APP_ROOT = Path(__file__).resolve().parent
SRC_PATH = APP_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import azure.functions as func  # noqa: E402
from pydantic import ValidationError  # noqa: E402

if TYPE_CHECKING:
    from document_intelligence.models import DocumentIngestionRequest, ReviewQueueItem
    from document_intelligence.settings import AppSettings


REVIEW_API_ADMIN_KEY_HEADER = "x-docint-admin-key"


def _is_setting_enabled(value: str) -> bool:
    """Return whether a string setting should be treated as enabled."""
    return value.strip().lower() not in {"0", "false", "no", "off"}


DURABLE_WORKFLOWS_ENABLED = _is_setting_enabled(
    os.getenv("DOCINT_ENABLE_DURABLE_WORKFLOWS", "true")
)

if DURABLE_WORKFLOWS_ENABLED:
    import azure.durable_functions as durable_functions  # noqa: E402

    app = durable_functions.DFApp(http_auth_level=func.AuthLevel.FUNCTION)
else:
    durable_functions = cast(Any, None)
    app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


def _json_response(
    payload: dict[str, Any],
    status_code: HTTPStatus,
) -> func.HttpResponse:
    """Build a JSON HTTP response."""
    return func.HttpResponse(
        body=json.dumps(payload, indent=2, default=str),
        mimetype="application/json",
        status_code=int(status_code),
    )


def _binary_response(
    content: bytes,
    *,
    content_type: str,
) -> func.HttpResponse:
    """Build a binary HTTP response for protected document preview content."""

    return func.HttpResponse(
        body=content,
        headers={"Cache-Control": "no-store"},
        mimetype=content_type,
        status_code=int(HTTPStatus.OK),
    )


def _load_request(req: func.HttpRequest) -> DocumentIngestionRequest:
    """Parse and validate an ingestion request."""
    from document_intelligence.models import DocumentIngestionRequest

    payload = req.get_json()
    return DocumentIngestionRequest.model_validate(payload)


def _get_settings() -> AppSettings:
    """Return the cached application settings instance."""
    from document_intelligence.settings import get_settings

    return get_settings()


def _get_review_item_model(review_item_payload: dict[str, Any]) -> ReviewQueueItem:
    """Validate a review item payload into a model instance."""
    from document_intelligence.models import ReviewQueueItem

    return ReviewQueueItem.model_validate(review_item_payload)


def _persist_review_item_if_configured(
    review_item: ReviewQueueItem,
    settings: AppSettings,
) -> ReviewQueueItem:
    """Persist a review item when Cosmos DB is configured."""
    from document_intelligence.persistence import CosmosReviewRepository

    review_repository = CosmosReviewRepository(settings)
    if not review_repository.is_configured():
        logging.warning(
            "Cosmos DB review storage is not configured; skipping persistence"
        )
        return review_item

    return review_repository.upsert_review_item(review_item)


def _publish_review_item_if_configured(
    review_item: ReviewQueueItem,
    settings: AppSettings,
) -> None:
    """Publish a review item when Service Bus is configured."""
    from document_intelligence.persistence import ServiceBusReviewQueuePublisher

    publisher = ServiceBusReviewQueuePublisher(settings)
    if not publisher.is_configured():
        logging.warning("Service Bus review queue is not configured; skipping publish")
        return

    publisher.publish_review_item(review_item)


def _run_synchronous_ingestion(request: DocumentIngestionRequest) -> dict[str, Any]:
    """Run the workflow inline and return the final workflow payload."""
    from document_intelligence.workflow import process_document_request

    settings = _get_settings()
    workflow_result = process_document_request(request, settings)
    review_item = workflow_result.review_item

    if review_item is not None:
        persisted_review_item = _persist_review_item_if_configured(
            review_item,
            settings,
        )
        _publish_review_item_if_configured(persisted_review_item, settings)
        workflow_result = workflow_result.model_copy(
            update={"review_item": persisted_review_item}
        )

    return workflow_result.model_dump(mode="json")


def _validation_error_response(
    error: ValidationError | ValueError,
) -> func.HttpResponse:
    """Return a consistent bad-request response for invalid payloads."""
    if isinstance(error, ValidationError):
        details: Any = error.errors(include_url=False)
    else:
        details = str(error)

    return _json_response(
        {
            "status": "invalid_request",
            "details": details,
        },
        HTTPStatus.BAD_REQUEST,
    )


def _service_unavailable_response(message: str) -> func.HttpResponse:
    """Return a consistent response for missing runtime configuration."""
    return _json_response(
        {"status": "configuration_required", "message": message},
        HTTPStatus.SERVICE_UNAVAILABLE,
    )


def _unauthorized_response(message: str) -> func.HttpResponse:
    """Return a consistent response for unauthorized review API calls."""
    return _json_response(
        {"status": "unauthorized", "message": message},
        HTTPStatus.UNAUTHORIZED,
    )


def _forbidden_response(message: str) -> func.HttpResponse:
    """Return a consistent response for forbidden review API calls."""

    return _json_response(
        {"status": "forbidden", "message": message},
        HTTPStatus.FORBIDDEN,
    )


def _not_found_response(message: str) -> func.HttpResponse:
    """Return a consistent response for missing resources."""

    return _json_response(
        {"status": "not_found", "message": message},
        HTTPStatus.NOT_FOUND,
    )


def _require_review_api_access(
    req: func.HttpRequest,
    settings: AppSettings,
) -> func.HttpResponse | None:
    """Validate the server-side admin key when review API protection is enabled."""
    configured_key = settings.review_api_admin_key
    if not configured_key:
        return None

    provided_key = req.headers.get(REVIEW_API_ADMIN_KEY_HEADER, "")
    if secrets.compare_digest(provided_key, configured_key):
        return None

    logging.warning("Blocked review API request because the admin key was missing.")
    return _unauthorized_response(
        "Review API access requires the configured admin key."
    )


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Return a lightweight readiness payload."""
    from document_intelligence.profiles import PROFILE_CATALOG

    del req
    settings = _get_settings()

    return _json_response(
        {
            "status": "healthy",
            "service": "hybrid-document-intelligence-platform",
            "environment": settings.environment_name,
            "reviewQueue": settings.review_queue_name,
            "requiredFields": list(settings.required_fields),
            "supportedPromptProfiles": len(PROFILE_CATALOG),
            "cosmosConfigured": bool(settings.cosmos_endpoint and settings.cosmos_key),
            "sqlConfigured": bool(settings.sql_connection_string),
            "manualIntakeReady": bool(
                settings.sql_connection_string and settings.storage_connection_string
            ),
            "durableWorkflowsEnabled": DURABLE_WORKFLOWS_ENABLED,
            "workflowMode": "durable" if DURABLE_WORKFLOWS_ENABLED else "synchronous",
        },
        HTTPStatus.OK,
    )


@app.route(
    route="public-traffic-events",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def capture_public_traffic_event(req: func.HttpRequest) -> func.HttpResponse:
    """Capture public simulation traffic and optionally send an email alert."""
    from document_intelligence.public_traffic_metrics import (
        record_public_traffic_event_aggregate,
    )
    from document_intelligence.traffic_alerts import (
        PublicTrafficEvent,
        build_public_traffic_alert,
        mask_client_ip,
        send_public_traffic_alert,
    )

    try:
        event = PublicTrafficEvent.model_validate(req.get_json())
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)

    settings = _get_settings()
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
        {
            "alertSent": alert_sent,
            "status": "accepted",
        },
        HTTPStatus.ACCEPTED,
    )


@app.route(
    route="public-metrics-summary",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_public_metrics_summary(req: func.HttpRequest) -> func.HttpResponse:
    """Return aggregate public metrics for the security posture site."""
    del req

    from document_intelligence.public_traffic_metrics import (
        build_public_traffic_metrics_summary,
    )

    summary = build_public_traffic_metrics_summary(_get_settings())

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
    """Persist a scheduled public-site availability probe for the security page."""
    del monitor_timer

    from document_intelligence.public_site_monitor import run_public_site_monitor

    results = run_public_site_monitor(_get_settings())
    logging.info(
        "Scheduled public site verifier finished ok=%s public=%s traffic=%s",
        results.get("ok"),
        results.get("public_site"),
        results.get("traffic_event"),
    )


@app.timer_trigger(
    arg_name="cost_refresh_timer",
    schedule="0 7 */6 * * *",
    use_monitor=True,
)
def run_public_cost_refresh(cost_refresh_timer: func.TimerRequest) -> None:
    """Refresh retained public-safe cost history on a fixed timer."""
    del cost_refresh_timer

    from document_intelligence.public_cost_refresh import refresh_public_cost_history

    results = refresh_public_cost_history(_get_settings())
    logging.info(
        "Scheduled public cost refresh finished ok=%s status=%s rows=%s",
        results.get("ok"),
        results.get("status"),
        results.get("history_row_count"),
    )


@app.timer_trigger(
    arg_name="daily_digest_timer",
    schedule="0 30 13 * * *",
    use_monitor=True,
)
def run_public_traffic_daily_digest(daily_digest_timer: func.TimerRequest) -> None:
    """Send a once-per-day consolidated public traffic digest email."""
    del daily_digest_timer

    from document_intelligence.traffic_alerts import send_public_traffic_daily_digest

    sent = send_public_traffic_daily_digest(_get_settings())
    logging.info("Scheduled public traffic daily digest sent=%s", sent)


@app.route(
    route="public-request-context",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_public_request_context(req: func.HttpRequest) -> func.HttpResponse:
    """Return sanitized request context for the public security posture site."""
    from document_intelligence.public_network_enrichment import (
        build_public_network_enrichment_provider,
    )
    from document_intelligence.public_request_context import build_public_request_context

    settings = _get_settings()
    request_context = build_public_request_context(
        req.headers,
        req.url,
        enrichment_provider=build_public_network_enrichment_provider(settings),
        enrichment_enabled=settings.public_network_enrichment_enabled,
        security_globe_enabled=settings.public_security_globe_enabled,
    )

    logging.info(
        "Built public request context request_id=%s secure=%s ip_present=%s enrichment_enabled=%s globe_enabled=%s provider=%s",
        request_context.request_id,
        request_context.transport_security,
        request_context.client_ip is not None,
        request_context.public_network_enrichment_enabled,
        request_context.public_security_globe_enabled,
        request_context.enrichment_provider_name,
    )

    return _json_response(request_context.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="security/cves",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_public_security_cves(req: func.HttpRequest) -> func.HttpResponse:
    """Return the latest sanitized CVE feed for the public security site."""
    del req

    from document_intelligence.public_security_feeds import (
        load_public_security_cve_feed,
    )

    feed = load_public_security_cve_feed(_get_settings())
    logging.info(
        "Built public CVE feed total=%s keywords=%s",
        feed.total_count,
        ",".join(feed.keyword_terms) or "none",
    )
    return _json_response(feed.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="security/msrc-latest",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_public_security_msrc_latest(req: func.HttpRequest) -> func.HttpResponse:
    """Return the latest sanitized MSRC release index for the public security site."""
    del req

    from document_intelligence.public_security_feeds import (
        load_public_security_msrc_feed,
    )

    feed = load_public_security_msrc_feed(_get_settings())
    logging.info("Built public MSRC release index total=%s", feed.total_count)
    return _json_response(feed.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="public-cost-summary",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_public_cost_summary(req: func.HttpRequest) -> func.HttpResponse:
    """Return the latest public-safe cost summary and ranked contributors."""
    del req

    from document_intelligence.public_cost_metrics import (
        load_public_cost_metrics_summary,
    )

    summary = load_public_cost_metrics_summary(_get_settings())
    if summary is None:
        return _service_unavailable_response(
            "Public cost history is not available yet."
        )

    logging.info(
        "Built public cost summary month_to_date=%s rows=%s source=%s",
        summary.month_to_date_cost,
        summary.history_row_count,
        summary.history_source,
    )
    return _json_response(summary.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="public-cost-latest",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_public_cost_latest(req: func.HttpRequest) -> func.HttpResponse:
    """Return the latest raw public-safe cost snapshot JSON payload."""
    del req

    from document_intelligence.public_cost_metrics import load_public_cost_latest_json

    payload = load_public_cost_latest_json(_get_settings())
    if payload is None:
        return _service_unavailable_response(
            "Public cost history is not available yet."
        )

    return _json_response(payload, HTTPStatus.OK)


@app.route(
    route="public-cost-history",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_public_cost_history(req: func.HttpRequest) -> func.HttpResponse:
    """Return the retained public-safe cost CSV history payload."""
    del req

    from document_intelligence.public_cost_metrics import load_public_cost_history_csv

    payload = load_public_cost_history_csv(_get_settings())
    if payload is None:
        return _service_unavailable_response(
            "Public cost history is not available yet."
        )

    return func.HttpResponse(
        body=payload,
        headers={"Cache-Control": "no-store"},
        mimetype="text/csv",
        status_code=int(HTTPStatus.OK),
    )


@app.route(
    route="docs/public-openapi.json",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_public_openapi_contract(req: func.HttpRequest) -> func.HttpResponse:
    """Return the anonymous public OpenAPI contract."""
    del req

    from document_intelligence.api_contracts import (
        build_public_openapi_document,
        render_openapi_json,
    )

    return func.HttpResponse(
        body=render_openapi_json(build_public_openapi_document()),
        mimetype="application/json",
        status_code=int(HTTPStatus.OK),
    )


@app.route(
    route="docs/public-api",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_public_api_docs(req: func.HttpRequest) -> func.HttpResponse:
    """Return the anonymous Redoc surface for the public API contract."""
    del req

    from document_intelligence.api_contracts import build_public_api_docs_html

    return func.HttpResponse(
        body=build_public_api_docs_html("/api/docs/public-openapi.json"),
        mimetype="text/html",
        status_code=int(HTTPStatus.OK),
    )


@app.route(
    route="packets/manual-intake",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def create_manual_packet(req: func.HttpRequest) -> func.HttpResponse:
    """Stage a manual packet upload into Blob storage and Azure SQL."""
    from document_intelligence.manual_intake import (
        ManualIntakeConfigurationError,
        create_manual_packet_intake,
    )
    from document_intelligence.models import ManualPacketIntakeRequest

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    try:
        request = ManualPacketIntakeRequest.model_validate(req.get_json())
        response = create_manual_packet_intake(request, settings)
    except ManualIntakeConfigurationError as error:
        return _service_unavailable_response(str(error))
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)

    return _json_response(response.model_dump(mode="json"), HTTPStatus.CREATED)


@app.route(
    route="intake-sources",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def list_intake_sources(req: func.HttpRequest) -> func.HttpResponse:
    """List durable operator intake-source definitions from Azure SQL."""
    import document_intelligence.intake_sources as intake_source_service

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    try:
        response = intake_source_service.list_intake_sources(settings)
    except intake_source_service.IntakeSourceConfigurationError as error:
        return _service_unavailable_response(str(error))

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="intake-sources",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def create_intake_source(req: func.HttpRequest) -> func.HttpResponse:
    """Create a durable operator intake-source definition in Azure SQL."""
    import document_intelligence.intake_sources as intake_source_service
    from document_intelligence.models import IntakeSourceCreateRequest

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    try:
        request = IntakeSourceCreateRequest.model_validate(req.get_json())
        response = intake_source_service.create_intake_source(request, settings)
    except intake_source_service.IntakeSourceConfigurationError as error:
        return _service_unavailable_response(str(error))
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)

    return _json_response(response.model_dump(mode="json"), HTTPStatus.CREATED)


@app.route(
    route="intake-sources/{source_id}",
    methods=["PUT"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def update_intake_source(req: func.HttpRequest) -> func.HttpResponse:
    """Replace one durable operator intake-source definition in Azure SQL."""
    import document_intelligence.intake_sources as intake_source_service
    from document_intelligence.models import IntakeSourceUpdateRequest

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    source_id = req.route_params.get("source_id")
    if not source_id:
        return _validation_error_response(ValueError("source_id is required"))

    try:
        request = IntakeSourceUpdateRequest.model_validate(req.get_json())
        response = intake_source_service.update_intake_source(
            source_id,
            request,
            settings,
        )
    except intake_source_service.IntakeSourceConfigurationError as error:
        return _service_unavailable_response(str(error))
    except RuntimeError as error:
        if "not found" in str(error).lower():
            return _not_found_response(str(error))
        raise
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="intake-sources/{source_id}/enablement",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def set_intake_source_enablement(req: func.HttpRequest) -> func.HttpResponse:
    """Pause or resume one durable operator intake-source definition."""
    import document_intelligence.intake_sources as intake_source_service
    from document_intelligence.models import IntakeSourceEnablementRequest

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    source_id = req.route_params.get("source_id")
    if not source_id:
        return _validation_error_response(ValueError("source_id is required"))

    try:
        request = IntakeSourceEnablementRequest.model_validate(req.get_json())
        response = intake_source_service.set_intake_source_enablement(
            source_id,
            request,
            settings,
        )
    except intake_source_service.IntakeSourceConfigurationError as error:
        return _service_unavailable_response(str(error))
    except RuntimeError as error:
        if "not found" in str(error).lower():
            return _not_found_response(str(error))
        raise
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="intake-sources/{source_id}",
    methods=["DELETE"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def delete_intake_source(req: func.HttpRequest) -> func.HttpResponse:
    """Delete one durable operator intake-source definition from Azure SQL."""
    import document_intelligence.intake_sources as intake_source_service

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    source_id = req.route_params.get("source_id")
    if not source_id:
        return _validation_error_response(ValueError("source_id is required"))

    try:
        response = intake_source_service.delete_intake_source(source_id, settings)
    except intake_source_service.IntakeSourceConfigurationError as error:
        return _service_unavailable_response(str(error))
    except RuntimeError as error:
        if "not found" in str(error).lower():
            return _not_found_response(str(error))
        raise

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="intake-sources/{source_id}/execute",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def run_intake_source(req: func.HttpRequest) -> func.HttpResponse:
    """Execute one supported operator-managed intake source."""
    import document_intelligence.intake_sources as intake_source_service

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    source_id = req.route_params.get("source_id")
    if not source_id:
        return _validation_error_response(ValueError("source_id is required"))

    try:
        response = intake_source_service.execute_intake_source(source_id, settings)
    except intake_source_service.IntakeSourceConfigurationError as error:
        return _service_unavailable_response(str(error))
    except RuntimeError as error:
        if "not found" in str(error).lower():
            return _not_found_response(str(error))
        raise

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="intake-sources/{source_id}/ingest",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def ingest_partner_intake_source(req: func.HttpRequest) -> func.HttpResponse:
    """Stage one partner-submitted packet for a configured intake source."""
    import document_intelligence.intake_sources as intake_source_service
    from document_intelligence.models import SourcePacketIngestionRequest

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    source_id = req.route_params.get("source_id")
    if not source_id:
        return _validation_error_response(ValueError("source_id is required"))

    try:
        request = SourcePacketIngestionRequest.model_validate(req.get_json())
        response = intake_source_service.ingest_partner_source_packet(
            source_id,
            request,
            settings,
        )
    except intake_source_service.IntakeSourceConfigurationError as error:
        return _service_unavailable_response(str(error))
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)
    except RuntimeError as error:
        if "not found" in str(error).lower():
            return _not_found_response(str(error))
        raise

    return _json_response(response.model_dump(mode="json"), HTTPStatus.CREATED)


@app.route(
    route="processing-taxonomy",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_processing_taxonomy(req: func.HttpRequest) -> func.HttpResponse:
    """Return the canonical packet-processing statuses and stages."""
    import document_intelligence.processing_taxonomy as taxonomy_service

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    response = taxonomy_service.get_processing_taxonomy()
    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="operator-contracts",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_operator_contracts(req: func.HttpRequest) -> func.HttpResponse:
    """Return the SQL-backed operator contracts needed by later app tabs."""
    import document_intelligence.operator_contracts as operator_contract_service

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    try:
        response = operator_contract_service.get_operator_contracts(settings)
    except operator_contract_service.OperatorContractsConfigurationError as error:
        return _service_unavailable_response(str(error))

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="packets",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def list_packet_queue(req: func.HttpRequest) -> func.HttpResponse:
    """Return the SQL-backed packet queue used by the Epic 3 shell."""

    import document_intelligence.packet_queue as packet_queue_service
    from document_intelligence.models import PacketQueueListRequest

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    request_payload = {
        "assigned_user_email": req.params.get("assigned_user_email"),
        "classification_key": req.params.get("classification_key"),
        "document_type_key": req.params.get("document_type_key"),
        "min_queue_age_hours": req.params.get("min_queue_age_hours"),
        "page": req.params.get("page"),
        "page_size": req.params.get("page_size"),
        "source": req.params.get("source"),
        "stage_name": req.params.get("stage_name") or req.params.get("stage"),
        "status": req.params.get("status"),
    }
    request_payload = {
        key: value
        for key, value in request_payload.items()
        if value is not None and str(value).strip()
    }

    try:
        request = PacketQueueListRequest.model_validate(request_payload)
        response = packet_queue_service.list_packet_queue(request, settings)
    except packet_queue_service.PacketQueueConfigurationError as error:
        return _service_unavailable_response(str(error))
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="packets/{packet_id}/workspace",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_packet_workspace(req: func.HttpRequest) -> func.HttpResponse:
    """Return the SQL-backed packet workspace snapshot for operator views."""

    from document_intelligence.operator_state import SqlOperatorStateRepository

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    packet_id = req.route_params.get("packet_id")
    if not packet_id:
        return _validation_error_response(ValueError("packet_id is required"))

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        return _service_unavailable_response(
            "Azure SQL operator-state storage is not configured."
        )

    try:
        snapshot = repository.get_packet_workspace_snapshot(packet_id)
    except RuntimeError as error:
        error_message = str(error)
        if (
            "not found" in error_message.lower()
            or "could not be loaded" in error_message.lower()
        ):
            return _not_found_response(error_message)
        raise

    return _json_response(snapshot.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="packets/{packet_id}/documents/{document_id}/content",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_packet_document_content(req: func.HttpRequest) -> func.HttpResponse:
    """Return protected binary preview content for one packet document."""

    from document_intelligence.document_viewer import (
        DocumentPreviewConfigurationError,
        DocumentPreviewPolicyError,
        get_packet_document_preview,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    packet_id = req.route_params.get("packet_id")
    if not packet_id:
        return _validation_error_response(ValueError("packet_id is required"))

    document_id = req.route_params.get("document_id")
    if not document_id:
        return _validation_error_response(ValueError("document_id is required"))

    try:
        preview = get_packet_document_preview(packet_id, document_id, settings)
    except DocumentPreviewConfigurationError as error:
        return _service_unavailable_response(str(error))
    except DocumentPreviewPolicyError as error:
        return _forbidden_response(str(error))
    except RuntimeError as error:
        error_message = str(error)
        if (
            "not found" in error_message.lower()
            or "could not be previewed" in error_message.lower()
        ):
            return _not_found_response(error_message)
        raise

    return _binary_response(preview.content, content_type=preview.content_type)


@app.route(
    route="packets/{packet_id}/classification/execute",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def run_packet_classification(req: func.HttpRequest) -> func.HttpResponse:
    """Execute queued packet classification work and queue OCR handoff."""

    from document_intelligence.packet_classification import (
        PacketClassificationConfigurationError,
        execute_packet_classification_stage,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    packet_id = req.route_params.get("packet_id")
    if not packet_id:
        return _validation_error_response(ValueError("packet_id is required"))

    try:
        response = execute_packet_classification_stage(packet_id, settings)
    except PacketClassificationConfigurationError as error:
        return _service_unavailable_response(str(error))
    except RuntimeError as error:
        if (
            "not found" in str(error).lower()
            or "could not be loaded" in str(error).lower()
        ):
            return _not_found_response(str(error))
        raise

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="packets/{packet_id}/ocr/execute",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def run_packet_ocr(req: func.HttpRequest) -> func.HttpResponse:
    """Execute queued packet OCR work and queue extraction handoff."""

    from document_intelligence.packet_ocr import (
        PacketOcrConfigurationError,
        execute_packet_ocr_stage,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    packet_id = req.route_params.get("packet_id")
    if not packet_id:
        return _validation_error_response(ValueError("packet_id is required"))

    try:
        response = execute_packet_ocr_stage(packet_id, settings)
    except PacketOcrConfigurationError as error:
        return _service_unavailable_response(str(error))
    except RuntimeError as error:
        if (
            "not found" in str(error).lower()
            or "could not be loaded" in str(error).lower()
        ):
            return _not_found_response(str(error))
        raise

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="packets/{packet_id}/extraction/execute",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def run_packet_extraction(req: func.HttpRequest) -> func.HttpResponse:
    """Execute queued packet extraction work and persist downstream routing."""

    from document_intelligence.packet_extraction import (
        PacketExtractionConfigurationError,
        execute_packet_extraction_stage,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    packet_id = req.route_params.get("packet_id")
    if not packet_id:
        return _validation_error_response(ValueError("packet_id is required"))

    try:
        response = execute_packet_extraction_stage(packet_id, settings)
    except PacketExtractionConfigurationError as error:
        return _service_unavailable_response(str(error))
    except RuntimeError as error:
        if (
            "not found" in str(error).lower()
            or "could not be loaded" in str(error).lower()
        ):
            return _not_found_response(str(error))
        raise

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="packets/{packet_id}/recommendation/execute",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def run_packet_recommendation(req: func.HttpRequest) -> func.HttpResponse:
    """Execute queued packet recommendation work and persist final advisories."""

    from document_intelligence.packet_recommendation import (
        PacketRecommendationConfigurationError,
        execute_packet_recommendation_stage,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    packet_id = req.route_params.get("packet_id")
    if not packet_id:
        return _validation_error_response(ValueError("packet_id is required"))

    try:
        response = execute_packet_recommendation_stage(packet_id, settings)
    except PacketRecommendationConfigurationError as error:
        return _service_unavailable_response(str(error))
    except RuntimeError as error:
        if (
            "not found" in str(error).lower()
            or "could not be loaded" in str(error).lower()
        ):
            return _not_found_response(str(error))
        raise

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="packets/{packet_id}/stages/{stage_name}/retry",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def retry_packet_stage(req: func.HttpRequest) -> func.HttpResponse:
    """Retry failed or stale work for one supported packet-processing stage."""

    from document_intelligence.packet_pipeline_actions import (
        PacketPipelineActionConfigurationError,
        retry_packet_stage as retry_packet_stage_action,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    packet_id = req.route_params.get("packet_id")
    if not packet_id:
        return _validation_error_response(ValueError("packet_id is required"))

    stage_name = req.route_params.get("stage_name")
    if not stage_name:
        return _validation_error_response(ValueError("stage_name is required"))

    try:
        response = retry_packet_stage_action(packet_id, stage_name, settings)
    except PacketPipelineActionConfigurationError as error:
        return _service_unavailable_response(str(error))
    except RuntimeError as error:
        if (
            "not found" in str(error).lower()
            or "could not be loaded" in str(error).lower()
        ):
            return _not_found_response(str(error))
        raise
    except ValueError as error:
        return _validation_error_response(error)

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="packets/{packet_id}/replay",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def replay_packet(req: func.HttpRequest) -> func.HttpResponse:
    """Replay the next actionable packet stage from the Intake workspace."""

    from document_intelligence.packet_replay import (
        PacketReplayConfigurationError,
        replay_packet as replay_packet_service,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    packet_id = req.route_params.get("packet_id")
    if not packet_id:
        return _validation_error_response(ValueError("packet_id is required"))

    try:
        response = replay_packet_service(packet_id, settings)
    except PacketReplayConfigurationError as error:
        return _service_unavailable_response(str(error))
    except ValueError as error:
        return _validation_error_response(error)
    except RuntimeError as error:
        if (
            "not found" in str(error).lower()
            or "could not be loaded" in str(error).lower()
        ):
            return _not_found_response(str(error))
        raise

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route=(
        "packets/{packet_id}/recommendation-results/"
        "{recommendation_result_id}/review"
    ),
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def review_packet_recommendation(req: func.HttpRequest) -> func.HttpResponse:
    """Approve or reject one stored packet recommendation result."""

    from document_intelligence.models import PacketRecommendationReviewRequest
    from document_intelligence.packet_recommendation_review import (
        PacketRecommendationReviewConfigurationError,
        review_packet_recommendation as review_packet_recommendation_service,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    packet_id = req.route_params.get("packet_id")
    if not packet_id:
        return _validation_error_response(ValueError("packet_id is required"))

    recommendation_result_id = req.route_params.get("recommendation_result_id")
    if not recommendation_result_id:
        return _validation_error_response(
            ValueError("recommendation_result_id is required")
        )

    try:
        request = PacketRecommendationReviewRequest.model_validate(req.get_json())
        response = review_packet_recommendation_service(
            packet_id,
            recommendation_result_id,
            request,
            settings,
        )
    except PacketRecommendationReviewConfigurationError as error:
        return _service_unavailable_response(str(error))
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)
    except RuntimeError as error:
        error_message = str(error)
        if (
            "not found" in error_message.lower()
            or "could not be loaded" in error_message.lower()
        ):
            return _not_found_response(error_message)
        return _json_response(
            {"message": error_message, "status": "conflict"},
            HTTPStatus.CONFLICT,
        )

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="packets/{packet_id}/documents/{document_id}/review-tasks",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def create_packet_review_task(req: func.HttpRequest) -> func.HttpResponse:
    """Create one SQL-backed review task for a packet document."""

    from document_intelligence.models import PacketReviewTaskCreateRequest
    from document_intelligence.packet_review import (
        PacketReviewConfigurationError,
        create_packet_review_task as create_packet_review_task_service,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    packet_id = req.route_params.get("packet_id")
    if not packet_id:
        return _validation_error_response(ValueError("packet_id is required"))

    document_id = req.route_params.get("document_id")
    if not document_id:
        return _validation_error_response(ValueError("document_id is required"))

    try:
        request = PacketReviewTaskCreateRequest.model_validate(req.get_json())
        response = create_packet_review_task_service(
            packet_id,
            document_id,
            request,
            settings,
        )
    except PacketReviewConfigurationError as error:
        return _service_unavailable_response(str(error))
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)
    except RuntimeError as error:
        error_message = str(error)
        if (
            "not found" in error_message.lower()
            or "could not be loaded" in error_message.lower()
        ):
            return _not_found_response(error_message)
        return _json_response(
            {"message": error_message, "status": "conflict"},
            HTTPStatus.CONFLICT,
        )

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="review-tasks/{review_task_id}/assignment",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def apply_packet_review_assignment(req: func.HttpRequest) -> func.HttpResponse:
    """Persist one SQL-backed review-task assignment change."""

    from document_intelligence.models import PacketReviewAssignmentRequest
    from document_intelligence.packet_review import (
        PacketReviewConfigurationError,
        apply_packet_review_assignment as apply_packet_review_assignment_service,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    review_task_id = req.route_params.get("review_task_id")
    if not review_task_id:
        return _validation_error_response(ValueError("review_task_id is required"))

    try:
        request = PacketReviewAssignmentRequest.model_validate(req.get_json())
        response = apply_packet_review_assignment_service(
            review_task_id,
            request,
            settings,
        )
    except PacketReviewConfigurationError as error:
        return _service_unavailable_response(str(error))
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)
    except RuntimeError as error:
        error_message = str(error)
        if (
            "not found" in error_message.lower()
            or "could not be loaded" in error_message.lower()
        ):
            return _not_found_response(error_message)
        return _json_response(
            {"message": error_message, "status": "conflict"},
            HTTPStatus.CONFLICT,
        )

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="review-tasks/{review_task_id}/decision",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def apply_packet_review_decision(req: func.HttpRequest) -> func.HttpResponse:
    """Apply a SQL-backed review decision to one packet review task."""

    from document_intelligence.models import PacketReviewDecisionRequest
    from document_intelligence.packet_review import (
        PacketReviewConfigurationError,
        apply_packet_review_decision as apply_packet_review_decision_service,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    review_task_id = req.route_params.get("review_task_id")
    if not review_task_id:
        return _validation_error_response(ValueError("review_task_id is required"))

    try:
        request = PacketReviewDecisionRequest.model_validate(req.get_json())
        response = apply_packet_review_decision_service(
            review_task_id,
            request,
            settings,
        )
    except PacketReviewConfigurationError as error:
        return _service_unavailable_response(str(error))
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)
    except RuntimeError as error:
        error_message = str(error)
        if (
            "not found" in error_message.lower()
            or "could not be loaded" in error_message.lower()
        ):
            return _not_found_response(error_message)
        return _json_response(
            {"message": error_message, "status": "conflict"},
            HTTPStatus.CONFLICT,
        )

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="review-tasks/{review_task_id}/notes",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def apply_packet_review_note(req: func.HttpRequest) -> func.HttpResponse:
    """Persist one SQL-backed operator note for a review task."""

    from document_intelligence.models import PacketReviewNoteRequest
    from document_intelligence.packet_review import (
        PacketReviewConfigurationError,
        apply_packet_review_note as apply_packet_review_note_service,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    review_task_id = req.route_params.get("review_task_id")
    if not review_task_id:
        return _validation_error_response(ValueError("review_task_id is required"))

    try:
        request = PacketReviewNoteRequest.model_validate(req.get_json())
        response = apply_packet_review_note_service(
            review_task_id,
            request,
            settings,
        )
    except PacketReviewConfigurationError as error:
        return _service_unavailable_response(str(error))
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)
    except RuntimeError as error:
        error_message = str(error)
        if (
            "not found" in error_message.lower()
            or "could not be loaded" in error_message.lower()
        ):
            return _not_found_response(error_message)
        return _json_response(
            {"message": error_message, "status": "conflict"},
            HTTPStatus.CONFLICT,
        )

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="review-tasks/{review_task_id}/extraction-edits",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def apply_packet_review_extraction_edits(req: func.HttpRequest) -> func.HttpResponse:
    """Persist extracted-field edits for one SQL-backed review task."""

    from document_intelligence.models import PacketReviewExtractionEditRequest
    from document_intelligence.packet_review import (
        PacketReviewConfigurationError,
        apply_packet_review_extraction_edits as apply_packet_review_extraction_edits_service,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    review_task_id = req.route_params.get("review_task_id")
    if not review_task_id:
        return _validation_error_response(ValueError("review_task_id is required"))

    try:
        request = PacketReviewExtractionEditRequest.model_validate(req.get_json())
        response = apply_packet_review_extraction_edits_service(
            review_task_id,
            request,
            settings,
        )
    except PacketReviewConfigurationError as error:
        return _service_unavailable_response(str(error))
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)
    except RuntimeError as error:
        error_message = str(error)
        if (
            "not found" in error_message.lower()
            or "could not be loaded" in error_message.lower()
        ):
            return _not_found_response(error_message)
        return _json_response(
            {"message": error_message, "status": "conflict"},
            HTTPStatus.CONFLICT,
        )

    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(route="review-items/preview", methods=["POST"])
def preview_review_item(req: func.HttpRequest) -> func.HttpResponse:
    """Preview manual-review routing for a synthetic request."""
    from document_intelligence.orchestration import build_processing_preview

    try:
        request = _load_request(req)
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)

    preview = build_processing_preview(request, _get_settings())
    return _json_response(preview.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="review-items",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def list_review_items(req: func.HttpRequest) -> func.HttpResponse:
    """List persisted manual-review items from Cosmos DB."""
    from document_intelligence.models import ReviewStatus
    from document_intelligence.persistence import CosmosReviewRepository

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    repository = CosmosReviewRepository(settings)
    if not repository.is_configured():
        return _service_unavailable_response(
            "Cosmos DB review storage is not configured."
        )

    status_name = req.params.get("status", ReviewStatus.PENDING_REVIEW.value)
    limit_name = req.params.get("limit")

    try:
        status = ReviewStatus(status_name)
        limit = int(limit_name) if limit_name else settings.review_api_default_limit
    except ValueError as error:
        return _validation_error_response(error)

    response = repository.list_review_items(status=status, limit=limit)
    return _json_response(response.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="review-items/{document_id}",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_review_item(req: func.HttpRequest) -> func.HttpResponse:
    """Get a single manual-review item from Cosmos DB."""
    from document_intelligence.persistence import CosmosReviewRepository

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    repository = CosmosReviewRepository(settings)
    if not repository.is_configured():
        return _service_unavailable_response(
            "Cosmos DB review storage is not configured."
        )

    document_id = req.route_params.get("document_id")
    if not document_id:
        return _validation_error_response(ValueError("document_id is required"))

    review_item = repository.get_review_item(document_id)
    if review_item is None:
        return _json_response(
            {"status": "not_found", "document_id": document_id},
            HTTPStatus.NOT_FOUND,
        )

    return _json_response(review_item.model_dump(mode="json"), HTTPStatus.OK)


@app.route(
    route="review-items/{document_id}/decision",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def update_review_item_decision(req: func.HttpRequest) -> func.HttpResponse:
    """Apply a reviewer decision to a persisted review item."""
    from document_intelligence.models import ReviewDecisionUpdate, ReviewStatus
    from document_intelligence.persistence import (
        CosmosReviewRepository,
        ServiceBusReviewQueuePublisher,
    )

    settings = _get_settings()
    unauthorized_response = _require_review_api_access(req, settings)
    if unauthorized_response is not None:
        return unauthorized_response

    repository = CosmosReviewRepository(settings)
    if not repository.is_configured():
        return _service_unavailable_response(
            "Cosmos DB review storage is not configured."
        )

    document_id = req.route_params.get("document_id")
    if not document_id:
        return _validation_error_response(ValueError("document_id is required"))

    try:
        update = ReviewDecisionUpdate.model_validate(req.get_json())
    except (ValidationError, ValueError) as error:
        return _validation_error_response(error)

    updated_item = repository.apply_review_decision(document_id, update)
    if updated_item is None:
        return _json_response(
            {"status": "not_found", "document_id": document_id},
            HTTPStatus.NOT_FOUND,
        )

    if update.status == ReviewStatus.REPROCESS_REQUESTED:
        ServiceBusReviewQueuePublisher(settings).publish_review_item(updated_item)

    return _json_response(updated_item.model_dump(mode="json"), HTTPStatus.OK)


if DURABLE_WORKFLOWS_ENABLED:
    durable_app = cast(Any, app)

    @app.route(route="ingestions", methods=["POST"])
    @durable_app.durable_client_input(client_name="client")
    async def start_ingestion(
        req: func.HttpRequest,
        client: Any,
    ) -> func.HttpResponse:
        """Start the durable ingestion workflow."""
        try:
            request = _load_request(req)
        except (ValidationError, ValueError) as error:
            return _validation_error_response(error)

        instance_id = await client.start_new(
            "document_ingestion_orchestrator",
            None,
            request.model_dump(mode="json"),
        )

        logging.info(
            "Started ingestion orchestration %s for %s",
            instance_id,
            request.document_id,
        )
        return client.create_check_status_response(req, instance_id)

    @durable_app.orchestration_trigger(context_name="context")
    def document_ingestion_orchestrator(
        context: Any,
    ) -> Generator[Any, Any, dict[str, Any]]:
        """Run the durable normalization, extraction, and routing workflow."""
        request_payload = context.get_input()
        normalized_request = yield context.call_activity(
            "normalize_ingestion_request_activity",
            request_payload,
        )
        workflow_result = yield context.call_activity(
            "process_document_request_activity",
            normalized_request,
        )

        review_item = workflow_result.get("review_item")
        if review_item is not None:
            persisted_review_item = yield context.call_activity(
                "persist_review_item_activity",
                review_item,
            )
            workflow_result["review_item"] = persisted_review_item
            yield context.call_activity(
                "publish_review_queue_activity",
                persisted_review_item,
            )

        workflow_result["instance_id"] = context.instance_id
        return workflow_result

    @durable_app.activity_trigger(input_name="request_payload")
    def normalize_ingestion_request_activity(
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalize a request before enrichment steps are added."""
        from document_intelligence.models import DocumentIngestionRequest
        from document_intelligence.orchestration import normalize_request

        request = DocumentIngestionRequest.model_validate(request_payload)
        normalized_request = normalize_request(request)
        return normalized_request.model_dump(mode="json")

    @durable_app.activity_trigger(input_name="request_payload")
    def process_document_request_activity(
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Run the extraction, matching, and routing workflow."""
        from document_intelligence.models import DocumentIngestionRequest
        from document_intelligence.workflow import process_document_request

        request = DocumentIngestionRequest.model_validate(request_payload)
        workflow_result = process_document_request(request, _get_settings())
        return workflow_result.model_dump(mode="json")

    @durable_app.activity_trigger(input_name="review_item_payload")
    def persist_review_item_activity(
        review_item_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist a review item into Cosmos DB when configured."""
        item = _get_review_item_model(review_item_payload)
        persisted_item = _persist_review_item_if_configured(item, _get_settings())
        return persisted_item.model_dump(mode="json")

    @durable_app.activity_trigger(input_name="review_item_payload")
    def publish_review_queue_activity(review_item_payload: dict[str, Any]) -> None:
        """Publish a persisted review item to the manual review queue."""
        review_item = _get_review_item_model(review_item_payload)
        _publish_review_item_if_configured(review_item, _get_settings())
else:

    @app.route(route="ingestions", methods=["POST"])
    def start_ingestion(req: func.HttpRequest) -> func.HttpResponse:
        """Run the ingestion workflow inline when Durable is disabled."""
        try:
            request = _load_request(req)
        except (ValidationError, ValueError) as error:
            return _validation_error_response(error)

        output = _run_synchronous_ingestion(request)
        return _json_response(
            {
                "instanceId": None,
                "output": output,
                "runtimeStatus": "Completed",
                "workflowMode": "synchronous",
            },
            HTTPStatus.OK,
        )
