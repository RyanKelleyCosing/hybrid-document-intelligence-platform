"""Unit tests for the private live-site auth smoke helper."""

from __future__ import annotations

from pathlib import Path

from document_intelligence.settings import AppSettings
from document_intelligence.utils.private_live_site_auth_smoke import (
    run_private_live_site_auth_smoke,
)


def create_bundle(tmp_path: Path) -> Path:
    """Create a minimal React bundle directory for the auth smoke tests."""

    bundle_directory = tmp_path / "dist"
    bundle_directory.mkdir()
    (bundle_directory / "index.html").write_text(
        "<html><body>live admin shell</body></html>",
        encoding="utf-8",
    )
    return bundle_directory


def test_private_live_site_auth_smoke_allows_and_blocks_expected_users(
    tmp_path: Path,
) -> None:
    """The auth smoke should prove allowlisted and denied behavior."""

    result = run_private_live_site_auth_smoke(
        allowlisted_email="ryankelley1992@outlook.com",
        denied_email="blocked-user@example.com",
        settings=AppSettings(
            allowed_reviewer_emails=("ryankelley1992@outlook.com",),
        ),
        static_dir=create_bundle(tmp_path),
    )

    assert result["ok"] is True
    assert result["allowlisted_session"]["status_code"] == 200
    assert result["allowlisted_session"]["payload"]["authorized"] is True
    assert result["denied_session"]["status_code"] == 403
    assert result["denied_root"]["status_code"] == 403


def test_private_live_site_auth_smoke_reports_missing_allowlist_configuration(
    tmp_path: Path,
) -> None:
    """The smoke should fail fast when the expected allowlisted user is absent."""

    result = run_private_live_site_auth_smoke(
        allowlisted_email="ryankelley1992@outlook.com",
        denied_email="blocked-user@example.com",
        settings=AppSettings(allowed_reviewer_emails=("different@example.com",)),
        static_dir=create_bundle(tmp_path),
    )

    assert result["ok"] is False
    assert result["status"] == "configuration_required"
    assert result["checks"]["allowlisted_email_configured"] is False