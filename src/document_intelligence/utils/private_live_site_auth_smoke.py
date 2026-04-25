"""Representative authenticated smoke checks for the private live site."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from document_intelligence.live_site import create_live_site_app
from document_intelligence.settings import AppSettings


def run_private_live_site_auth_smoke(
    *,
    allowlisted_email: str,
    denied_email: str,
    settings: AppSettings,
    static_dir: Path | None = None,
) -> dict[str, Any]:
    """Exercise allowlisted and denied principals through the live-site app."""

    normalized_allowlisted_email = allowlisted_email.strip().lower()
    normalized_denied_email = denied_email.strip().lower()
    configured_allowlist = tuple(settings.allowed_reviewer_emails)

    checks = {
        "allowlisted_email_configured": (
            normalized_allowlisted_email in configured_allowlist
        ),
        "denied_email_not_allowlisted": (
            normalized_denied_email not in configured_allowlist
        ),
    }
    if not all(checks.values()):
        return {
            "checks": checks,
            "configured_allowlist": list(configured_allowlist),
            "ok": False,
            "status": "configuration_required",
        }

    app = create_live_site_app(settings=settings, static_dir=static_dir)
    client = app.test_client()

    allowlisted_session_response = client.get(
        "/api/session",
        headers=_build_principal_headers(normalized_allowlisted_email),
    )
    allowlisted_session_payload = allowlisted_session_response.get_json()

    denied_session_response = client.get(
        "/api/session",
        headers=_build_principal_headers(normalized_denied_email),
    )
    denied_session_payload = denied_session_response.get_json()

    denied_root_response = client.get(
        "/",
        headers=_build_principal_headers(normalized_denied_email),
    )
    denied_root_body = denied_root_response.get_data(as_text=True)

    checks.update(
        {
            "allowlisted_session_authorized": (
                allowlisted_session_response.status_code == 200
                and isinstance(allowlisted_session_payload, dict)
                and bool(allowlisted_session_payload.get("authenticated"))
                and bool(allowlisted_session_payload.get("authorized"))
                and allowlisted_session_payload.get("email")
                == normalized_allowlisted_email
            ),
            "denied_session_blocked": (
                denied_session_response.status_code == 403
                and isinstance(denied_session_payload, dict)
                and denied_session_payload.get("status") == "forbidden"
            ),
            "denied_root_blocked": (
                denied_root_response.status_code == 403
                and "configured Microsoft account" in denied_root_body
            ),
        }
    )

    return {
        "allowlisted_email": normalized_allowlisted_email,
        "allowlisted_session": {
            "payload": allowlisted_session_payload,
            "status_code": allowlisted_session_response.status_code,
        },
        "checks": checks,
        "configured_allowlist": list(configured_allowlist),
        "denied_email": normalized_denied_email,
        "denied_root": {
            "body": denied_root_body,
            "status_code": denied_root_response.status_code,
        },
        "denied_session": {
            "payload": denied_session_payload,
            "status_code": denied_session_response.status_code,
        },
        "ok": all(checks.values()),
        "status": "ok" if all(checks.values()) else "failed",
    }


def _build_principal_headers(email: str) -> dict[str, str]:
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


__all__ = ["run_private_live_site_auth_smoke"]