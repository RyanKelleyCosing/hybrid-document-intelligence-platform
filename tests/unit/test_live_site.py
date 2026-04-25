"""Unit tests for the private live-site host."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from pytest import MonkeyPatch

from document_intelligence import live_site as live_site_module
from document_intelligence.settings import AppSettings


def create_bundle(tmp_path: Path) -> Path:
    """Create a minimal React bundle directory for the private site tests."""
    bundle_directory = tmp_path / "dist"
    bundle_directory.mkdir()
    (bundle_directory / "index.html").write_text(
        "<html><body>live admin shell</body></html>",
        encoding="utf-8",
    )
    (bundle_directory / "app.js").write_text(
        "console.log('live admin shell');",
        encoding="utf-8",
    )
    return bundle_directory


def build_principal_headers(email: str) -> dict[str, str]:
    """Build representative Easy Auth headers for a signed-in user."""
    payload = {
        "auth_typ": "aad",
        "claims": [
            {
                "typ": "preferred_username",
                "val": email,
            }
        ],
    }
    encoded_payload = base64.b64encode(
        json.dumps(payload).encode("utf-8")
    ).decode("ascii")
    return {
        "X-MS-CLIENT-PRINCIPAL": encoded_payload,
        "X-MS-CLIENT-PRINCIPAL-IDP": "aad",
        "X-MS-CLIENT-PRINCIPAL-NAME": email,
    }


def test_live_site_returns_allowlisted_session(
    tmp_path: Path,
) -> None:
    """The private site should surface the signed-in allowlisted email."""
    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().get(
        "/api/session",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload == {
        "authenticated": True,
        "authorized": True,
        "email": "ryankelley1992@outlook.com",
        "identityProvider": "aad",
    }


def test_live_site_blocks_non_allowlisted_users(tmp_path: Path) -> None:
    """The private site should deny access for signed-in users outside the allowlist."""
    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().get(
        "/",
        headers=build_principal_headers("someoneelse@example.com"),
    )

    assert response.status_code == 403
    assert b"configured Microsoft account" in response.data


def test_live_site_serves_protected_openapi_contract(tmp_path: Path) -> None:
    """The private site should expose the operator contract only to allowlisted users."""
    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().get(
        "/docs/operator-openapi.json",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["info"]["title"] == "Hybrid Document Intelligence Protected Operator API"
    assert "/packets" in payload["paths"]
    assert "/review-tasks/{review_task_id}/decision" in payload["paths"]
    assert "/review-items" not in payload["paths"]
    assert payload["security"] == [{"adminSession": []}]


def test_live_site_serves_protected_api_docs_surface(tmp_path: Path) -> None:
    """The private site should render a Redoc page for the operator contract."""
    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().get(
        "/docs/operator-api",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Protected Operator API Contract" in body
    assert "/docs/operator-openapi.json" in body
    assert "redoc" in body.lower()


def test_live_site_blocks_protected_api_docs_for_non_allowlisted_users(
    tmp_path: Path,
) -> None:
    """The protected documentation surface should stay behind the same admin auth gate."""
    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().get(
        "/docs/operator-api",
        headers=build_principal_headers("someoneelse@example.com"),
    )

    assert response.status_code == 403
    assert b"configured Microsoft account" in response.data


def test_live_site_proxies_processing_taxonomy_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy the processing taxonomy API with the admin key."""
    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 200, b'{"statuses": [], "stages": []}', "application/json"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().get(
        "/api/processing-taxonomy",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {"statuses": [], "stages": []}
    assert captured == {
        "content_type": None,
        "data": None,
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "GET",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/processing-taxonomy",
    }


def test_live_site_proxies_packet_queue_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy the paged packet queue API with the admin key."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 200, b'{"items": [], "page": 1, "page_size": 25, "total_count": 0, "has_more": false}', "application/json"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().get(
        "/api/packets?page=2&stage_name=review",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "items": [],
        "page": 1,
        "page_size": 25,
        "total_count": 0,
        "has_more": False,
    }
    assert captured == {
        "content_type": None,
        "data": None,
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "GET",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/packets?page=2&stage_name=review",
    }


def test_live_site_proxies_packet_workspace_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy packet workspace requests with the admin key."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 200, b'{"packet": {"packet_id": "pkt_demo_001"}}', "application/json"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().get(
        "/api/packets/pkt_demo_001/workspace",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {"packet": {"packet_id": "pkt_demo_001"}}
    assert captured == {
        "content_type": None,
        "data": None,
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "GET",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/packets/pkt_demo_001/workspace",
    }


def test_live_site_proxies_packet_document_preview_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy protected document preview content."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 200, b"%PDF-1.4 demo", "application/pdf"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().get(
        "/api/packets/pkt_demo_001/documents/doc_demo_001/content",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data == b"%PDF-1.4 demo"
    assert captured == {
        "content_type": None,
        "data": None,
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "GET",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/packets/pkt_demo_001/documents/doc_demo_001/content",
    }


def test_live_site_proxies_packet_stage_execution_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy packet stage execution calls."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 200, b'{"packet_id": "pkt_demo_001", "status": "extracting"}', "application/json"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().post(
        "/api/packets/pkt_demo_001/ocr/execute",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "packet_id": "pkt_demo_001",
        "status": "extracting",
    }
    assert captured == {
        "content_type": None,
        "data": b"",
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "POST",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/packets/pkt_demo_001/ocr/execute",
    }


def test_live_site_proxies_packet_stage_retry_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy packet-stage retry calls."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 200, b'{"packet_id": "pkt_demo_001", "requeued_document_count": 1}', "application/json"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().post(
        "/api/packets/pkt_demo_001/stages/ocr/retry",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "packet_id": "pkt_demo_001",
        "requeued_document_count": 1,
    }
    assert captured == {
        "content_type": None,
        "data": b"",
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "POST",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/packets/pkt_demo_001/stages/ocr/retry",
    }


def test_live_site_proxies_packet_replay_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy packet replay calls."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 200, b'{"packet_id": "pkt_demo_001", "action": "retry"}', "application/json"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().post(
        "/api/packets/pkt_demo_001/replay",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "packet_id": "pkt_demo_001",
        "action": "retry",
    }
    assert captured == {
        "content_type": None,
        "data": b"",
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "POST",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/packets/pkt_demo_001/replay",
    }


def test_live_site_proxies_recommendation_review_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy recommendation review calls."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 200, b'{"packet_id": "pkt_demo_001"}', "application/json"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().post(
        "/api/packets/pkt_demo_001/recommendation-results/recres_001/review",
        headers={
            **build_principal_headers("ryankelley1992@outlook.com"),
            "Content-Type": "application/json",
        },
        data=json.dumps({"disposition": "accepted"}),
    )

    assert response.status_code == 200
    assert response.get_json() == {"packet_id": "pkt_demo_001"}
    assert captured == {
        "content_type": "application/json",
        "data": b'{"disposition": "accepted"}',
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "POST",
        "timeout_seconds": 45,
        "url": (
            "https://func-doc-test.azurewebsites.net/api/packets/"
            "pkt_demo_001/recommendation-results/recres_001/review"
        ),
    }


def test_live_site_proxies_operator_contract_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy the operator contracts API with the admin key."""
    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 200, b'{"classification_definitions": []}', "application/json"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().get(
        "/api/operator-contracts",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {"classification_definitions": []}
    assert captured == {
        "content_type": None,
        "data": None,
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "GET",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/operator-contracts",
    }


def test_live_site_proxies_intake_source_execution_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy watched intake-source execution calls."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 200, b'{"processed_blob_count": 1}', "application/json"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().post(
        "/api/intake-sources/src_ops_blob/execute",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {"processed_blob_count": 1}
    assert captured == {
        "content_type": None,
        "data": b"",
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "POST",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/intake-sources/src_ops_blob/execute",
    }


def test_live_site_proxies_intake_source_update_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy intake-source update calls."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 200, b'{"source_id": "src_ops_blob"}', "application/json"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().put(
        "/api/intake-sources/src_ops_blob",
        data=json.dumps({"source_name": "Ops blob watcher"}),
        content_type="application/json",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {"source_id": "src_ops_blob"}
    assert captured == {
        "content_type": "application/json",
        "data": b'{"source_name": "Ops blob watcher"}',
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "PUT",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/intake-sources/src_ops_blob",
    }


def test_live_site_proxies_intake_source_enablement_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy intake-source pause or resume calls."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 200, b'{"source_id": "src_ops_blob", "is_enabled": false}', "application/json"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().post(
        "/api/intake-sources/src_ops_blob/enablement",
        data=json.dumps({"is_enabled": False}),
        content_type="application/json",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "source_id": "src_ops_blob",
        "is_enabled": False,
    }
    assert captured == {
        "content_type": "application/json",
        "data": b'{"is_enabled": false}',
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "POST",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/intake-sources/src_ops_blob/enablement",
    }


def test_live_site_proxies_intake_source_delete_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy intake-source delete calls."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 200, b'{"deleted": true, "source_id": "src_ops_blob"}', "application/json"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().delete(
        "/api/intake-sources/src_ops_blob",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "deleted": True,
        "source_id": "src_ops_blob",
    }
    assert captured == {
        "content_type": None,
        "data": b"",
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "DELETE",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/intake-sources/src_ops_blob",
    }


def test_live_site_proxies_manual_packet_requests(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy manual packet uploads with the admin key."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return 201, b'{"packet_id": "pkt_demo_001"}', "application/json"

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().post(
        "/api/packets/manual-intake",
        data=json.dumps(
            {
                "packet_name": "demo packet",
                "source": "scanned_upload",
                "documents": [
                    {
                        "file_name": "sample.pdf",
                        "content_type": "application/pdf",
                        "document_content_base64": "JVBERi0xLjQ=",
                    }
                ],
            }
        ),
        content_type="application/json",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 201
    assert response.get_json() == {"packet_id": "pkt_demo_001"}
    assert captured == {
        "content_type": "application/json",
        "data": (
            b'{"packet_name": "demo packet", "source": "scanned_upload", '
            b'"documents": [{"file_name": "sample.pdf", "content_type": '
            b'"application/pdf", "document_content_base64": "JVBERi0xLjQ="}]}'
        ),
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "POST",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/packets/manual-intake",
    }


def test_live_site_proxies_packet_review_decisions(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy packet review decisions with the admin key."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return (
            200,
            b'{"review_task_id": "task_001", "packet_status": "ready_for_recommendation"}',
            "application/json",
        )

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().post(
        "/api/review-tasks/task_001/decision",
        data=json.dumps(
            {
                "decision_status": "approved",
                "decided_by_email": "reviewer@example.com",
                "expected_row_version": "0000000000000001",
            }
        ),
        content_type="application/json",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "review_task_id": "task_001",
        "packet_status": "ready_for_recommendation",
    }
    assert captured == {
        "content_type": "application/json",
        "data": (
            b'{"decision_status": "approved", "decided_by_email": '
            b'"reviewer@example.com", "expected_row_version": '
            b'"0000000000000001"}'
        ),
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "POST",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/review-tasks/task_001/decision",
    }


def test_live_site_proxies_packet_review_assignments(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy review-task assignment updates with the admin key."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return (
            200,
            b'{"review_task_id": "task_001", "assigned_user_email": "qa.reviewer@example.com"}',
            "application/json",
        )

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().post(
        "/api/review-tasks/task_001/assignment",
        data=json.dumps(
            {
                "assigned_by_email": "lead.reviewer@example.com",
                "assigned_user_email": "qa.reviewer@example.com",
                "expected_row_version": "0000000000000001",
            }
        ),
        content_type="application/json",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "review_task_id": "task_001",
        "assigned_user_email": "qa.reviewer@example.com",
    }
    assert captured == {
        "content_type": "application/json",
        "data": (
            b'{"assigned_by_email": "lead.reviewer@example.com", '
            b'"assigned_user_email": "qa.reviewer@example.com", '
            b'"expected_row_version": "0000000000000001"}'
        ),
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "POST",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/review-tasks/task_001/assignment",
    }


def test_live_site_proxies_packet_review_task_creates(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy review-task creation writes with the admin key."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return (
            200,
            b'{"review_task_id": "task_created_001"}',
            "application/json",
        )

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().post(
        "/api/packets/pkt_archive_001/documents/doc_child_001/review-tasks",
        data=json.dumps(
            {
                "created_by_email": "lead.reviewer@example.com",
                "notes_summary": "Manual follow-up requested from the protected review tab.",
            }
        ),
        content_type="application/json",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {"review_task_id": "task_created_001"}
    assert captured == {
        "content_type": "application/json",
        "data": (
            b'{"created_by_email": "lead.reviewer@example.com", '
            b'"notes_summary": "Manual follow-up requested from the protected review tab."}'
        ),
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "POST",
        "timeout_seconds": 45,
        "url": (
            "https://func-doc-test.azurewebsites.net/api/packets/"
            "pkt_archive_001/documents/doc_child_001/review-tasks"
        ),
    }


def test_live_site_proxies_packet_review_extraction_edits(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy extraction edit saves with the admin key."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return (
            200,
            b'{"review_task_id": "task_001", "changed_fields": [{"field_name": "account_number"}]}',
            "application/json",
        )

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().post(
        "/api/review-tasks/task_001/extraction-edits",
        data=json.dumps(
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
        ),
        content_type="application/json",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "review_task_id": "task_001",
        "changed_fields": [{"field_name": "account_number"}],
    }
    assert captured == {
        "content_type": "application/json",
        "data": (
            b'{"edited_by_email": "reviewer@example.com", "expected_row_version": '
            b'"0000000000000001", "field_edits": [{"field_name": '
            b'"account_number", "value": "5678"}]}'
        ),
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "POST",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/review-tasks/task_001/extraction-edits",
    }


def test_live_site_proxies_packet_review_notes(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The private site should proxy review-task notes with the admin key."""

    captured: dict[str, object] = {}

    def fake_perform_proxy_request(
        *,
        content_type: str | None,
        data: bytes | None,
        headers: dict[str, str],
        method: str,
        timeout_seconds: int,
        url: str,
    ) -> tuple[int, bytes, str | None]:
        captured["content_type"] = content_type
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        captured["url"] = url
        return (
            200,
            b'{"review_task_id": "task_001", "packet_id": "pkt_archive_001", "operator_note": {"note_text": "Need one more statement page before approval."}}',
            "application/json",
        )

    monkeypatch.setattr(
        live_site_module,
        "_perform_proxy_request",
        fake_perform_proxy_request,
    )

    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
            function_api_base_url="https://func-doc-test.azurewebsites.net/api",
            review_api_admin_key="private-admin-key",
            review_api_proxy_timeout_seconds=45,
        ),
        static_dir=create_bundle(tmp_path),
    )

    response = app.test_client().post(
        "/api/review-tasks/task_001/notes",
        data=json.dumps(
            {
                "created_by_email": "reviewer@example.com",
                "expected_row_version": "0000000000000001",
                "note_text": "Need one more statement page before approval.",
            }
        ),
        content_type="application/json",
        headers=build_principal_headers("ryankelley1992@outlook.com"),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "review_task_id": "task_001",
        "packet_id": "pkt_archive_001",
        "operator_note": {
            "note_text": "Need one more statement page before approval.",
        },
    }
    assert captured == {
        "content_type": "application/json",
        "data": (
            b'{"created_by_email": "reviewer@example.com", "expected_row_version": '
            b'"0000000000000001", "note_text": "Need one more statement page before approval."}'
        ),
        "headers": {
            "Accept": "application/json",
            live_site_module.REVIEW_API_ADMIN_KEY_HEADER: "private-admin-key",
        },
        "method": "POST",
        "timeout_seconds": 45,
        "url": "https://func-doc-test.azurewebsites.net/api/review-tasks/task_001/notes",
    }


def test_live_site_returns_default_favicon_when_not_bundled(tmp_path: Path) -> None:
    """The live site should serve a default favicon when the bundle has none."""
    app = live_site_module.create_live_site_app(
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
        ),
        static_dir=create_bundle(tmp_path),
    )

    favicon_ico_response = app.test_client().get("/favicon.ico")
    favicon_svg_response = app.test_client().get("/favicon.svg")

    assert favicon_ico_response.status_code == 200
    assert favicon_ico_response.mimetype == "image/svg+xml"
    assert b"<svg" in favicon_ico_response.data
    assert favicon_svg_response.status_code == 200
    assert favicon_svg_response.mimetype == "image/svg+xml"