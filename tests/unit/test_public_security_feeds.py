"""Unit tests for the public security feed loaders."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from document_intelligence import public_security_feeds
from document_intelligence.public_security_feeds import (
    CVE_COLLECTION_MODE,
    MSRC_COLLECTION_MODE,
    NVD_CVE_API_URL,
    PublicSecurityCveFeed,
    PublicSecurityMsrcFeed,
    load_public_security_cve_feed,
    load_public_security_msrc_feed,
)
from document_intelligence.settings import AppSettings


def _frozen_now(value: datetime) -> "callable":
    return lambda: value


def _make_settings(**overrides: Any) -> AppSettings:
    base = {
        "public_security_cve_feed_enabled": True,
        "public_security_cve_keyword_terms": ("python",),
        "public_security_cve_max_items": 5,
        "public_security_msrc_feed_enabled": True,
        "public_security_msrc_max_items": 5,
        "storage_connection_string": None,
    }
    base.update(overrides)
    return AppSettings.model_validate(base)


def test_load_cve_feed_returns_disabled_empty_when_flag_off() -> None:
    settings = _make_settings(public_security_cve_feed_enabled=False)
    feed = load_public_security_cve_feed(
        settings,
        http_fetcher=lambda url, headers, timeout: pytest.fail("must not fetch"),
        now_utc=_frozen_now(datetime(2026, 4, 24, tzinfo=UTC)),
    )

    assert feed.total_count == 0
    assert feed.items == ()
    assert feed.collection_mode == CVE_COLLECTION_MODE


def test_load_cve_feed_parses_nvd_payload_and_sorts_by_published() -> None:
    settings = _make_settings()
    payload: dict[str, Any] = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-0001",
                    "published": "2026-04-20T12:00:00.000",
                    "lastModified": "2026-04-21T12:00:00.000",
                    "descriptions": [
                        {"lang": "es", "value": "ignored"},
                        {"lang": "en", "value": "Older issue."},
                    ],
                    "metrics": {
                        "cvssMetricV31": [
                            {
                                "cvssData": {
                                    "baseScore": 6.5,
                                    "baseSeverity": "MEDIUM",
                                }
                            }
                        ]
                    },
                    "references": [{"url": "https://example.test/older"}],
                }
            },
            {
                "cve": {
                    "id": "CVE-2026-0002",
                    "published": "2026-04-23T08:00:00Z",
                    "descriptions": [{"lang": "en", "value": "Newer issue."}],
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseScore": 9.1, "baseSeverity": "CRITICAL"}}
                        ]
                    },
                    "references": [{"url": "https://example.test/newer"}],
                }
            },
        ]
    }

    captured_urls: list[str] = []

    def fetcher(url: str, headers: Mapping[str, str], timeout: float) -> dict[str, Any]:
        del headers, timeout
        captured_urls.append(url)
        return payload

    feed = load_public_security_cve_feed(
        settings,
        http_fetcher=fetcher,
        now_utc=_frozen_now(datetime(2026, 4, 24, tzinfo=UTC)),
    )

    assert len(captured_urls) == 1
    assert captured_urls[0].startswith(NVD_CVE_API_URL + "?")
    assert "keywordSearch=python" in captured_urls[0]
    assert feed.total_count == 2
    assert feed.items[0].cve_id == "CVE-2026-0002"
    assert feed.items[0].cvss_score == 9.1
    assert feed.items[0].severity == "CRITICAL"
    assert feed.items[1].cve_id == "CVE-2026-0001"
    assert feed.items[0].reference_url == "https://example.test/newer"


def test_load_cve_feed_returns_empty_on_fetch_failure() -> None:
    settings = _make_settings()

    def failing_fetcher(url: str, headers: Mapping[str, str], timeout: float) -> dict[str, Any]:
        raise RuntimeError("simulated outage")

    feed = load_public_security_cve_feed(
        settings,
        http_fetcher=failing_fetcher,
        now_utc=_frozen_now(datetime(2026, 4, 24, tzinfo=UTC)),
    )

    assert feed.total_count == 0
    assert feed.items == ()
    assert feed.keyword_terms == ("python",)


def test_load_cve_feed_uses_blob_cache_within_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(
        storage_connection_string="UseDevelopmentStorage=true",
        public_security_cve_cache_ttl_seconds=3600,
    )
    cached_feed = PublicSecurityCveFeed(
        collection_mode=CVE_COLLECTION_MODE,
        generated_at_utc=datetime(2026, 4, 24, 11, 30, tzinfo=UTC),
        items=(),
        keyword_terms=("python",),
        source=NVD_CVE_API_URL,
        total_count=0,
    )

    monkeypatch.setattr(
        public_security_feeds,
        "_read_cached_feed",
        lambda *args, **kwargs: cached_feed,
    )

    def fetcher(url: str, headers: Mapping[str, str], timeout: float) -> dict[str, Any]:
        pytest.fail("Cached feed must not trigger fetcher")

    feed = load_public_security_cve_feed(
        settings,
        http_fetcher=fetcher,
        now_utc=_frozen_now(datetime(2026, 4, 24, 12, 0, tzinfo=UTC)),
    )

    assert feed is cached_feed


def test_load_msrc_feed_parses_releases_and_sorts_by_release_date() -> None:
    settings = _make_settings()
    payload: dict[str, Any] = {
        "value": [
            {
                "ID": "2026-Mar",
                "Alias": "2026-Mar",
                "DocumentTitle": "March 2026 Security Updates",
                "InitialReleaseDate": "2026-03-11T08:00:00Z",
                "CvrfUrl": "https://example.test/cvrf/2026-mar",
            },
            {
                "ID": "2026-Apr",
                "Alias": "2026-Apr",
                "DocumentTitle": "April 2026 Security Updates",
                "InitialReleaseDate": "2026-04-08T08:00:00Z",
                "CvrfUrl": "https://example.test/cvrf/2026-apr",
            },
        ]
    }

    feed = load_public_security_msrc_feed(
        settings,
        http_fetcher=lambda url, headers, timeout: payload,
        now_utc=_frozen_now(datetime(2026, 4, 24, tzinfo=UTC)),
    )

    assert feed.total_count == 2
    assert feed.collection_mode == MSRC_COLLECTION_MODE
    assert feed.items[0].msrc_id == "2026-Apr"
    assert feed.items[0].alias == "2026-Apr"
    assert feed.items[0].cvrf_url == "https://example.test/cvrf/2026-apr"
    assert feed.items[1].msrc_id == "2026-Mar"


def test_load_msrc_feed_returns_disabled_empty_when_flag_off() -> None:
    settings = _make_settings(public_security_msrc_feed_enabled=False)
    feed = load_public_security_msrc_feed(
        settings,
        http_fetcher=lambda url, headers, timeout: pytest.fail("must not fetch"),
        now_utc=_frozen_now(datetime(2026, 4, 24, tzinfo=UTC)),
    )

    assert feed.total_count == 0
    assert feed.items == ()


def test_cve_keyword_terms_csv_setting_is_parsed() -> None:
    """CSV env strings should normalize into a lowercase tuple."""
    settings = AppSettings.model_validate(
        {"public_security_cve_keyword_terms": "Azure Functions, Python, React"}
    )
    assert settings.public_security_cve_keyword_terms == (
        "azure functions",
        "python",
        "react",
    )
