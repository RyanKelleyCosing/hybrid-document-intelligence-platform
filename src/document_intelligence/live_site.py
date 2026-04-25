"""Authenticated private live-site host for the document intelligence platform."""

from __future__ import annotations

import base64
import binascii
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from flask import Flask, Response, g, jsonify, request, send_from_directory

from document_intelligence.settings import AppSettings, get_settings

REVIEW_API_ADMIN_KEY_HEADER = "x-docint-admin-key"
FAVICON_PATHS = frozenset({"/favicon.ico", "/favicon.svg"})
DEFAULT_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" '
    'role="img" aria-label="Document intelligence favicon">'
    '<rect width="64" height="64" rx="14" fill="#18352f"/>'
    '<path d="M14 18h36v10H14z" fill="#f7f1e7" opacity="0.94"/>'
    '<path d="M14 32h26v10H14z" fill="#bf5b33"/>'
    '<circle cx="49" cy="42" r="7" fill="#f1b44c"/>'
    "</svg>"
)


@dataclass(frozen=True)
class ClientPrincipalClaim:
    """A single Easy Auth claim exposed through the client principal header."""

    claim_type: str
    value: str


@dataclass(frozen=True)
class DecodedClientPrincipal:
    """The decoded Easy Auth principal payload."""

    claims: tuple[ClientPrincipalClaim, ...]
    identity_provider: str | None


@dataclass(frozen=True)
class LiveSitePrincipal:
    """The normalized principal information used by the private site."""

    authenticated: bool
    authorized: bool
    email: str | None
    identity_provider: str | None


def _default_static_dir() -> Path:
    """Return the expected location of the deployed live-site bundle."""
    return Path(__file__).resolve().parents[2] / "dist"


def _decode_client_principal(encoded_header: str) -> DecodedClientPrincipal:
    """Decode the Easy Auth client principal payload when it is present."""
    if not encoded_header:
        return DecodedClientPrincipal(claims=(), identity_provider=None)

    try:
        decoded_bytes = base64.b64decode(encoded_header)
        payload = cast(dict[str, Any], json.loads(decoded_bytes.decode("utf-8")))
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
        logging.warning("Unable to decode the Easy Auth client principal header.")
        return DecodedClientPrincipal(claims=(), identity_provider=None)

    claims_payload = payload.get("claims")
    if not isinstance(claims_payload, list):
        return DecodedClientPrincipal(
            claims=(),
            identity_provider=_read_string_value(payload.get("auth_typ")),
        )

    claims = tuple(
        ClientPrincipalClaim(claim_type=claim_type, value=claim_value)
        for claim in claims_payload
        if isinstance(claim, dict)
        for claim_type, claim_value in [
            (
                _read_string_value(claim.get("typ")),
                _read_string_value(claim.get("val")),
            )
        ]
        if claim_type and claim_value
    )

    return DecodedClientPrincipal(
        claims=claims,
        identity_provider=_read_string_value(payload.get("auth_typ")),
    )


def _read_string_value(value: Any) -> str | None:
    """Normalize a potentially missing string value."""
    if isinstance(value, str):
        normalized_value = value.strip()
        if normalized_value:
            return normalized_value
    return None


def _select_email(
    header_value: str | None,
    claims: tuple[ClientPrincipalClaim, ...],
) -> str | None:
    """Select the best available email-like identifier from Easy Auth headers."""
    normalized_header_value = _read_string_value(header_value)
    if normalized_header_value is not None:
        return normalized_header_value

    for claim in claims:
        normalized_type = claim.claim_type.lower()
        if normalized_type in {"email", "emails", "preferred_username", "upn"}:
            return claim.value
        if normalized_type.endswith("/emailaddress"):
            return claim.value
        if normalized_type.endswith("/preferred_username"):
            return claim.value
        if normalized_type.endswith("/upn"):
            return claim.value
        if normalized_type.endswith("/name") and "@" in claim.value:
            return claim.value

    return None


def _is_authorized_email(email: str | None, settings: AppSettings) -> bool:
    """Return whether the caller should be allowed into the private site."""
    if not settings.allowed_reviewer_emails:
        return True

    if email is None:
        return False

    return email.lower() in settings.allowed_reviewer_emails


def _build_principal(
    headers: Mapping[str, Any],
    settings: AppSettings,
) -> LiveSitePrincipal:
    """Build a normalized principal from the App Service authentication headers."""
    normalized_headers = {
        str(key).lower(): value
        for key, value in headers.items()
    }
    decoded_principal = _decode_client_principal(
        _read_string_value(normalized_headers.get("x-ms-client-principal")) or ""
    )
    email = _select_email(
        _read_string_value(normalized_headers.get("x-ms-client-principal-name")),
        decoded_principal.claims,
    )
    identity_provider = _read_string_value(
        normalized_headers.get("x-ms-client-principal-idp")
    ) or decoded_principal.identity_provider
    authenticated = bool(email or decoded_principal.claims or identity_provider)

    return LiveSitePrincipal(
        authenticated=authenticated,
        authorized=_is_authorized_email(email, settings),
        email=email,
        identity_provider=identity_provider,
    )


def _build_access_denied_response(path: str) -> Response:
    """Return a consistent access-denied response for blocked requests."""
    message = "This admin site only allows the configured Microsoft account."
    if path.startswith("/api/"):
        response = jsonify({"message": message, "status": "forbidden"})
        response.status_code = 403
        return response
    return Response(message, mimetype="text/plain", status=403)


def _get_request_principal() -> LiveSitePrincipal:
    """Return the principal stored for the current request."""
    principal = getattr(g, "live_site_principal", None)
    if isinstance(principal, LiveSitePrincipal):
        return principal

    return LiveSitePrincipal(
        authenticated=False,
        authorized=False,
        email=None,
        identity_provider=None,
    )


def _build_proxy_url(base_url: str, path: str, query: str) -> str:
    """Build the target Functions API URL for a proxied review request."""
    target_url = urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))
    if query:
        return f"{target_url}?{query}"
    return target_url


def _perform_proxy_request(
    *,
    content_type: str | None,
    data: bytes | None,
    headers: dict[str, str],
    method: str,
    timeout_seconds: int,
    url: str,
) -> tuple[int, bytes, str | None]:
    """Send a request to the protected Functions API and capture the response."""
    if content_type is not None:
        headers["Content-Type"] = content_type

    request_object = Request(url=url, data=data, headers=headers, method=method)

    try:
        with urlopen(request_object, timeout=timeout_seconds) as response:
            return (
                response.status,
                response.read(),
                response.headers.get("Content-Type"),
            )
    except HTTPError as error:
        return error.code, error.read(), error.headers.get("Content-Type")
    except URLError as error:
        logging.exception("Unable to reach the protected Functions review API.")
        payload = json.dumps(
            {
                "message": "Unable to reach the protected Functions review API.",
                "details": str(error.reason),
                "status": "bad_gateway",
            }
        ).encode("utf-8")
        return 502, payload, "application/json"


def _proxy_review_request(settings: AppSettings, path: str) -> Response:
    """Proxy a review API request to the Function App with the admin key."""
    if not settings.function_api_base_url or not settings.review_api_admin_key:
        response = jsonify(
            {
                "message": (
                    "The private live site is missing review API proxy settings."
                ),
                "status": "configuration_required",
            }
        )
        response.status_code = 503
        return response

    query_string = urlencode(list(request.args.items(multi=True)), doseq=True)
    target_url = _build_proxy_url(settings.function_api_base_url, path, query_string)
    data = request.get_data() if request.method != "GET" else None
    status_code, payload, response_content_type = _perform_proxy_request(
        content_type=request.headers.get("Content-Type"),
        data=data,
        headers={
            "Accept": request.headers.get("Accept", "application/json"),
            REVIEW_API_ADMIN_KEY_HEADER: settings.review_api_admin_key,
        },
        method=request.method,
        timeout_seconds=settings.review_api_proxy_timeout_seconds,
        url=target_url,
    )
    return Response(
        payload,
        content_type=response_content_type or "application/json",
        status=status_code,
    )


def _serve_react_bundle(static_dir: Path, requested_path: str) -> Response:
    """Serve the deployed React bundle and fall back to index.html for SPA routes."""
    if not static_dir.exists():
        return Response(
            "The live admin bundle has not been deployed yet.",
            mimetype="text/plain",
            status=503,
        )

    candidate_path = static_dir / requested_path
    if requested_path and candidate_path.is_file():
        return send_from_directory(static_dir, requested_path)

    return send_from_directory(static_dir, "index.html")


def _serve_favicon(static_dir: Path, requested_name: str) -> Response:
    """Serve a bundled favicon when present and otherwise return a default SVG."""
    normalized_name = requested_name.strip("/") or "favicon.ico"
    requested_path = static_dir / normalized_name
    if requested_path.is_file():
        return send_from_directory(static_dir, normalized_name)

    if normalized_name == "favicon.ico":
        svg_path = static_dir / "favicon.svg"
        if svg_path.is_file():
            return send_from_directory(static_dir, "favicon.svg")

    return Response(DEFAULT_FAVICON_SVG, mimetype="image/svg+xml", status=200)


def _json_text_response(payload: dict[str, Any]) -> Response:
    """Serialize a JSON payload for non-proxied live-site routes."""

    return Response(
        json.dumps(payload, indent=2, sort_keys=True),
        mimetype="application/json",
        status=200,
    )


def create_live_site_app(
    *,
    settings: AppSettings | None = None,
    static_dir: Path | None = None,
) -> Flask:
    """Create the private live-site app that fronts the protected review APIs."""
    app_settings = settings or get_settings()
    asset_directory = static_dir or _default_static_dir()
    app = Flask(__name__, static_folder=None)

    @app.before_request
    def authorize_request() -> Response | None:
        if request.path.startswith("/.auth/") or request.path in FAVICON_PATHS:
            return None

        principal = _build_principal(dict(request.headers), app_settings)
        g.live_site_principal = principal
        if principal.authorized:
            return None

        return _build_access_denied_response(request.path)

    @app.get("/api/session")
    def get_session() -> Response:
        principal = _get_request_principal()
        return jsonify(
            {
                "authenticated": principal.authenticated,
                "authorized": principal.authorized,
                "email": principal.email,
                "identityProvider": principal.identity_provider,
            }
        )

    @app.get("/api/packets")
    def list_packet_queue() -> Response:
        return _proxy_review_request(app_settings, "packets")

    @app.get("/api/packets/<packet_id>/workspace")
    def get_packet_workspace(packet_id: str) -> Response:
        return _proxy_review_request(app_settings, f"packets/{packet_id}/workspace")

    @app.get("/api/packets/<packet_id>/documents/<document_id>/content")
    def get_packet_document_content(packet_id: str, document_id: str) -> Response:
        return _proxy_review_request(
            app_settings,
            f"packets/{packet_id}/documents/{document_id}/content",
        )

    @app.post("/api/packets/<packet_id>/classification/execute")
    def run_packet_classification(packet_id: str) -> Response:
        return _proxy_review_request(
            app_settings,
            f"packets/{packet_id}/classification/execute",
        )

    @app.post("/api/packets/<packet_id>/ocr/execute")
    def run_packet_ocr(packet_id: str) -> Response:
        return _proxy_review_request(
            app_settings,
            f"packets/{packet_id}/ocr/execute",
        )

    @app.post("/api/packets/<packet_id>/extraction/execute")
    def run_packet_extraction(packet_id: str) -> Response:
        return _proxy_review_request(
            app_settings,
            f"packets/{packet_id}/extraction/execute",
        )

    @app.post("/api/packets/<packet_id>/recommendation/execute")
    def run_packet_recommendation(packet_id: str) -> Response:
        return _proxy_review_request(
            app_settings,
            f"packets/{packet_id}/recommendation/execute",
        )

    @app.post("/api/packets/<packet_id>/stages/<stage_name>/retry")
    def retry_packet_stage(packet_id: str, stage_name: str) -> Response:
        return _proxy_review_request(
            app_settings,
            f"packets/{packet_id}/stages/{stage_name}/retry",
        )

    @app.post("/api/packets/<packet_id>/replay")
    def replay_packet(packet_id: str) -> Response:
        return _proxy_review_request(app_settings, f"packets/{packet_id}/replay")

    @app.post(
        "/api/packets/<packet_id>/recommendation-results/"
        "<recommendation_result_id>/review"
    )
    def review_packet_recommendation(
        packet_id: str,
        recommendation_result_id: str,
    ) -> Response:
        return _proxy_review_request(
            app_settings,
            (
                f"packets/{packet_id}/recommendation-results/"
                f"{recommendation_result_id}/review"
            ),
        )

    @app.get("/api/intake-sources")
    def list_intake_sources() -> Response:
        return _proxy_review_request(app_settings, "intake-sources")

    @app.post("/api/packets/manual-intake")
    def create_manual_packet() -> Response:
        return _proxy_review_request(app_settings, "packets/manual-intake")

    @app.post("/api/packets/<packet_id>/documents/<document_id>/review-tasks")
    def create_packet_review_task(packet_id: str, document_id: str) -> Response:
        return _proxy_review_request(
            app_settings,
            f"packets/{packet_id}/documents/{document_id}/review-tasks",
        )

    @app.post("/api/intake-sources")
    def create_intake_source() -> Response:
        return _proxy_review_request(app_settings, "intake-sources")

    @app.put("/api/intake-sources/<source_id>")
    def update_intake_source(source_id: str) -> Response:
        return _proxy_review_request(app_settings, f"intake-sources/{source_id}")

    @app.post("/api/intake-sources/<source_id>/enablement")
    def set_intake_source_enablement(source_id: str) -> Response:
        return _proxy_review_request(
            app_settings,
            f"intake-sources/{source_id}/enablement",
        )

    @app.delete("/api/intake-sources/<source_id>")
    def delete_intake_source(source_id: str) -> Response:
        return _proxy_review_request(app_settings, f"intake-sources/{source_id}")

    @app.post("/api/intake-sources/<source_id>/execute")
    def run_intake_source(source_id: str) -> Response:
        return _proxy_review_request(
            app_settings,
            f"intake-sources/{source_id}/execute",
        )

    @app.get("/api/processing-taxonomy")
    def get_processing_taxonomy() -> Response:
        return _proxy_review_request(app_settings, "processing-taxonomy")

    @app.get("/api/operator-contracts")
    def get_operator_contracts() -> Response:
        return _proxy_review_request(app_settings, "operator-contracts")

    @app.post("/api/review-tasks/<review_task_id>/assignment")
    def apply_review_task_assignment(review_task_id: str) -> Response:
        return _proxy_review_request(
            app_settings,
            f"review-tasks/{review_task_id}/assignment",
        )

    @app.post("/api/review-tasks/<review_task_id>/decision")
    def apply_review_task_decision(review_task_id: str) -> Response:
        return _proxy_review_request(
            app_settings,
            f"review-tasks/{review_task_id}/decision",
        )

    @app.post("/api/review-tasks/<review_task_id>/notes")
    def apply_review_task_note(review_task_id: str) -> Response:
        return _proxy_review_request(
            app_settings,
            f"review-tasks/{review_task_id}/notes",
        )

    @app.post("/api/review-tasks/<review_task_id>/extraction-edits")
    def apply_review_task_extraction_edits(review_task_id: str) -> Response:
        return _proxy_review_request(
            app_settings,
            f"review-tasks/{review_task_id}/extraction-edits",
        )

    @app.get("/docs/operator-openapi.json")
    def get_operator_openapi_contract() -> Response:
        from document_intelligence.api_contracts import build_protected_openapi_document

        return _json_text_response(build_protected_openapi_document())

    @app.get("/docs/operator-api")
    def get_operator_api_docs() -> Response:
        from document_intelligence.api_contracts import build_protected_api_docs_html

        return Response(
            build_protected_api_docs_html("/docs/operator-openapi.json"),
            mimetype="text/html",
            status=200,
        )

    @app.get("/favicon.ico")
    def serve_favicon() -> Response:
        return _serve_favicon(asset_directory, "favicon.ico")

    @app.get("/favicon.svg")
    def serve_favicon_svg() -> Response:
        return _serve_favicon(asset_directory, "favicon.svg")

    @app.get("/")
    def serve_index() -> Response:
        return _serve_react_bundle(asset_directory, "")

    @app.get("/<path:requested_path>")
    def serve_static_asset(requested_path: str) -> Response:
        if requested_path.startswith("api/") or requested_path.startswith(".auth/"):
            return Response(status=404)
        return _serve_react_bundle(asset_directory, requested_path)

    return app