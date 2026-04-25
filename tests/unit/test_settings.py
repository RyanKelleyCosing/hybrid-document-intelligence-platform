"""Unit tests for environment-backed application settings."""

from __future__ import annotations

from pytest import MonkeyPatch

from document_intelligence.settings import AppSettings


def test_settings_parse_required_fields_from_environment(
    monkeypatch: MonkeyPatch,
) -> None:
    """Comma-delimited environment variables should become tuples."""
    monkeypatch.setenv(
        "DOCINT_REQUIRED_FIELDS",
        "account_number, statement_date, debtor_name",
    )

    settings = AppSettings()

    assert settings.required_fields == (
        "account_number",
        "statement_date",
        "debtor_name",
    )


def test_settings_allow_threshold_override(monkeypatch: MonkeyPatch) -> None:
    """Environment overrides should support tuning confidence routing."""
    monkeypatch.setenv("DOCINT_LOW_CONFIDENCE_THRESHOLD", "0.91")

    settings = AppSettings()

    assert settings.low_confidence_threshold == 0.91


def test_settings_parse_allowed_reviewer_emails(
    monkeypatch: MonkeyPatch,
) -> None:
    """Allowlisted reviewer emails should be normalized from environment values."""
    monkeypatch.setenv(
        "DOCINT_ALLOWED_REVIEWER_EMAILS",
        "RyanKelley1992@Outlook.com, admin@example.com ",
    )

    settings = AppSettings()

    assert settings.allowed_reviewer_emails == (
        "ryankelley1992@outlook.com",
        "admin@example.com",
    )