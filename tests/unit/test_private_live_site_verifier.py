"""Unit tests for the private live-site verifier helpers."""

from __future__ import annotations

from email.message import Message
from urllib.error import HTTPError

import pytest

from document_intelligence.utils import private_live_site_verifier as verifier


def test_is_auth_redirect_detects_microsoft_login_redirect() -> None:
    """Microsoft login redirects should count as auth redirects."""
    assert verifier.is_auth_redirect(
        "https://admin-doc-test-nwigok.azurewebsites.net",
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    )


def test_normalize_private_live_site_url_requires_scheme() -> None:
    """Private live site URLs should require an explicit scheme."""
    with pytest.raises(ValueError, match="must start with http:// or https://"):
        verifier.normalize_private_live_site_url("admin-doc-test-nwigok.azurewebsites.net")


def test_fetch_private_live_site_check_accepts_unauthenticated_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 401 should count as a reachable auth challenge for the private site."""

    def raise_unauthorized(*_args: object, **_kwargs: object) -> None:
        headers = Message()
        headers.add_header("Content-Type", "text/html")
        raise HTTPError(
            url="https://admin-doc-test-nwigok.azurewebsites.net",
            code=401,
            msg="Unauthorized",
            hdrs=headers,
            fp=None,
        )

    monkeypatch.setattr(verifier, "urlopen", raise_unauthorized)

    result = verifier.fetch_private_live_site_check(
        "https://admin-doc-test-nwigok.azurewebsites.net"
    )

    assert result.auth_challenge is True
    assert result.auth_redirect is False
    assert result.is_reachable is True
    assert result.status_code == 401


def test_summarize_private_live_auth_settings_reports_ready_configuration() -> None:
    """Expected authsettingsV2 fields should produce a healthy summary."""
    summary = verifier.summarize_private_live_auth_settings(
        {
            "properties": {
                "globalValidation": {
                    "excludedPaths": ["/favicon.ico", "/favicon.svg"],
                    "requireAuthentication": True,
                    "unauthenticatedClientAction": "RedirectToLoginPage",
                },
                "httpSettings": {
                    "requireHttps": True,
                },
                "identityProviders": {
                    "azureActiveDirectory": {
                        "enabled": True,
                    }
                },
                "login": {
                    "tokenStore": {
                        "enabled": True,
                    }
                },
            }
        }
    )

    assert summary.auth_ok is True
    assert summary.missing_expectations == ()
    assert summary.require_authentication is True
    assert summary.unauthenticated_client_action == "RedirectToLoginPage"


def test_summarize_private_live_app_settings_requires_proxy_inputs() -> None:
    """The private live site app settings should surface proxy-readiness details."""
    summary = verifier.summarize_private_live_app_settings(
        {
            "DOCINT_ALLOWED_REVIEWER_EMAILS": "ryankelley1992@outlook.com",
            "DOCINT_FUNCTION_API_BASE_URL": "https://func-doc-test-nwigok.azurewebsites.net/api",
            "DOCINT_REVIEW_API_ADMIN_KEY": "private-admin-key",
        },
        "ryankelley1992@outlook.com",
    )

    assert summary.allowed_reviewer_emails == ("ryankelley1992@outlook.com",)
    assert summary.expected_allowed_user_present is True
    assert summary.has_allowed_reviewer_email is True
    assert summary.proxy_ready is True


def test_summarize_private_live_hostname_binding_matches_custom_domain() -> None:
    """The hostname binding summary should find the requested custom domain."""
    summary = verifier.summarize_private_live_hostname_binding(
        [
            {
                "hostNameType": "Verified",
                "name": "admin.ryancodes.online",
                "sslState": "SniEnabled",
                "thumbprint": "ABC123",
            }
        ],
        "admin.ryancodes.online",
    )

    assert summary.binding_present is True
    assert summary.host_name_type == "Verified"
    assert summary.ssl_state == "SniEnabled"
    assert summary.thumbprint_present is True