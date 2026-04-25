"""Public-safe security feed loaders for the security posture site.

Exposes two read endpoints:
  * :func:`load_public_security_cve_feed` - filtered NVD CVE feed.
  * :func:`load_public_security_msrc_feed` - latest MSRC CVRF release index.

Both helpers cache responses in Azure Blob storage when
``DOCINT_STORAGE_CONNECTION_STRING`` is configured. When storage is not
configured the helpers fall back to fetching on every call. All outbound
calls go through ``urllib`` so the module mirrors the existing public
network enrichment helper and avoids pulling a new HTTP dependency.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from document_intelligence.settings import AppSettings

PUBLIC_SECURITY_FEEDS_CONTAINER = "public-security-feeds"
CVE_CACHE_BLOB_NAME = "cves-latest.json"
MSRC_CACHE_BLOB_NAME = "msrc-latest.json"

NVD_CVE_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
MSRC_CVRF_API_URL = "https://api.msrc.microsoft.com/cvrf/v3.0/updates"

CVE_COLLECTION_MODE = "NVD CVE keyword search (1h cache)"
MSRC_COLLECTION_MODE = "MSRC CVRF release index (6h cache)"

_USER_AGENT = "docint-public-security-feeds/1.0"
_REQUEST_TIMEOUT_SECONDS = 8.0


HttpFetcher = Callable[[str, Mapping[str, str], float], dict[str, Any]]


class PublicSecurityCveItem(BaseModel):
    """One CVE record exposed to the public security site."""

    model_config = ConfigDict(str_strip_whitespace=True)

    cve_id: str = Field(min_length=1, max_length=32)
    cvss_score: float | None = Field(default=None, ge=0.0, le=10.0)
    last_modified_utc: datetime | None = None
    published_utc: datetime | None = None
    reference_url: str | None = Field(default=None, max_length=400)
    severity: str | None = Field(default=None, max_length=32)
    summary: str = Field(min_length=1, max_length=600)


class PublicSecurityCveFeed(BaseModel):
    """Sanitized CVE feed returned by ``/api/security/cves``."""

    model_config = ConfigDict(str_strip_whitespace=True)

    collection_mode: str = Field(min_length=1, max_length=80)
    generated_at_utc: datetime
    items: tuple[PublicSecurityCveItem, ...] = ()
    keyword_terms: tuple[str, ...] = ()
    source: str = Field(min_length=1, max_length=200)
    total_count: int = Field(ge=0)


class PublicSecurityMsrcItem(BaseModel):
    """One MSRC CVRF release record exposed to the public security site."""

    model_config = ConfigDict(str_strip_whitespace=True)

    alias: str | None = Field(default=None, max_length=64)
    cvrf_url: str | None = Field(default=None, max_length=400)
    document_title: str | None = Field(default=None, max_length=240)
    initial_release_utc: datetime | None = None
    msrc_id: str = Field(min_length=1, max_length=64)


class PublicSecurityMsrcFeed(BaseModel):
    """Sanitized MSRC release index returned by ``/api/security/msrc-latest``."""

    model_config = ConfigDict(str_strip_whitespace=True)

    collection_mode: str = Field(min_length=1, max_length=80)
    generated_at_utc: datetime
    items: tuple[PublicSecurityMsrcItem, ...] = ()
    source: str = Field(min_length=1, max_length=200)
    total_count: int = Field(ge=0)


def load_public_security_cve_feed(
    settings: AppSettings,
    *,
    http_fetcher: HttpFetcher | None = None,
    now_utc: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> PublicSecurityCveFeed:
    """Return the latest sanitized CVE feed for the public security site."""

    if not settings.public_security_cve_feed_enabled:
        return _empty_cve_feed(settings, now_utc())

    cached = _read_cached_feed(
        settings,
        CVE_CACHE_BLOB_NAME,
        ttl_seconds=settings.public_security_cve_cache_ttl_seconds,
        model_cls=PublicSecurityCveFeed,
        now_utc=now_utc(),
    )
    if cached is not None:
        return cached

    fetcher = http_fetcher or _fetch_json
    try:
        feed = _build_cve_feed(settings, fetcher, now_utc())
    except Exception as error:  # noqa: BLE001 - never crash the public route
        logging.warning("CVE feed fetch failed: %s", error)
        return _empty_cve_feed(settings, now_utc())

    _write_cached_feed(settings, CVE_CACHE_BLOB_NAME, feed)
    return feed


def load_public_security_msrc_feed(
    settings: AppSettings,
    *,
    http_fetcher: HttpFetcher | None = None,
    now_utc: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> PublicSecurityMsrcFeed:
    """Return the latest sanitized MSRC release index for the public security site."""

    if not settings.public_security_msrc_feed_enabled:
        return _empty_msrc_feed(settings, now_utc())

    cached = _read_cached_feed(
        settings,
        MSRC_CACHE_BLOB_NAME,
        ttl_seconds=settings.public_security_msrc_cache_ttl_seconds,
        model_cls=PublicSecurityMsrcFeed,
        now_utc=now_utc(),
    )
    if cached is not None:
        return cached

    fetcher = http_fetcher or _fetch_json
    try:
        feed = _build_msrc_feed(settings, fetcher, now_utc())
    except Exception as error:  # noqa: BLE001 - never crash the public route
        logging.warning("MSRC feed fetch failed: %s", error)
        return _empty_msrc_feed(settings, now_utc())

    _write_cached_feed(settings, MSRC_CACHE_BLOB_NAME, feed)
    return feed


def _build_cve_feed(
    settings: AppSettings,
    http_fetcher: HttpFetcher,
    generated_at: datetime,
) -> PublicSecurityCveFeed:
    keyword_terms = settings.public_security_cve_keyword_terms or ("python",)
    max_items = settings.public_security_cve_max_items
    aggregated: dict[str, PublicSecurityCveItem] = {}

    for term in keyword_terms:
        params = {
            "keywordSearch": term,
            "resultsPerPage": str(max_items),
        }
        url = f"{NVD_CVE_API_URL}?{urlencode(params)}"
        payload = http_fetcher(url, {"Accept": "application/json"}, _REQUEST_TIMEOUT_SECONDS)
        for item in _parse_nvd_vulnerabilities(payload):
            aggregated.setdefault(item.cve_id, item)

    sorted_items = sorted(
        aggregated.values(),
        key=lambda item: item.published_utc or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )[:max_items]

    return PublicSecurityCveFeed(
        collection_mode=CVE_COLLECTION_MODE,
        generated_at_utc=generated_at,
        items=tuple(sorted_items),
        keyword_terms=tuple(keyword_terms),
        source=NVD_CVE_API_URL,
        total_count=len(sorted_items),
    )


def _build_msrc_feed(
    settings: AppSettings,
    http_fetcher: HttpFetcher,
    generated_at: datetime,
) -> PublicSecurityMsrcFeed:
    payload = http_fetcher(
        MSRC_CVRF_API_URL,
        {"Accept": "application/json"},
        _REQUEST_TIMEOUT_SECONDS,
    )
    items = _parse_msrc_releases(payload, settings.public_security_msrc_max_items)

    return PublicSecurityMsrcFeed(
        collection_mode=MSRC_COLLECTION_MODE,
        generated_at_utc=generated_at,
        items=items,
        source=MSRC_CVRF_API_URL,
        total_count=len(items),
    )


def _parse_nvd_vulnerabilities(payload: Mapping[str, Any]) -> list[PublicSecurityCveItem]:
    raw_items = payload.get("vulnerabilities")
    if not isinstance(raw_items, list):
        return []

    parsed_items: list[PublicSecurityCveItem] = []
    for raw_entry in raw_items:
        cve_block = _as_mapping(raw_entry.get("cve") if isinstance(raw_entry, Mapping) else None)
        if cve_block is None:
            continue
        cve_id = _normalize_text(cve_block.get("id"))
        if cve_id is None:
            continue
        descriptions = cve_block.get("descriptions")
        summary = _extract_english_description(descriptions) or "Description unavailable."
        score, severity = _extract_cvss(cve_block.get("metrics"))
        reference_url = _extract_first_reference(cve_block.get("references"))

        parsed_items.append(
            PublicSecurityCveItem(
                cve_id=cve_id,
                cvss_score=score,
                last_modified_utc=_parse_iso_timestamp(cve_block.get("lastModified")),
                published_utc=_parse_iso_timestamp(cve_block.get("published")),
                reference_url=reference_url,
                severity=severity,
                summary=summary[:600],
            )
        )

    return parsed_items


def _parse_msrc_releases(
    payload: Mapping[str, Any],
    max_items: int,
) -> tuple[PublicSecurityMsrcItem, ...]:
    raw_items = payload.get("value")
    if not isinstance(raw_items, list):
        return ()

    parsed_items: list[PublicSecurityMsrcItem] = []
    for raw_entry in raw_items:
        if not isinstance(raw_entry, Mapping):
            continue
        msrc_id = _normalize_text(raw_entry.get("ID"))
        if msrc_id is None:
            continue
        parsed_items.append(
            PublicSecurityMsrcItem(
                alias=_normalize_text(raw_entry.get("Alias")),
                cvrf_url=_normalize_text(raw_entry.get("CvrfUrl")),
                document_title=_normalize_text(raw_entry.get("DocumentTitle")),
                initial_release_utc=_parse_iso_timestamp(raw_entry.get("InitialReleaseDate")),
                msrc_id=msrc_id,
            )
        )

    parsed_items.sort(
        key=lambda item: item.initial_release_utc or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return tuple(parsed_items[:max_items])


def _extract_english_description(descriptions: Any) -> str | None:
    if not isinstance(descriptions, list):
        return None
    for entry in descriptions:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("lang") == "en":
            text = _normalize_text(entry.get("value"))
            if text:
                return text
    return None


def _extract_cvss(metrics: Any) -> tuple[float | None, str | None]:
    metrics_block = _as_mapping(metrics)
    if metrics_block is None:
        return None, None
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics_block.get(key)
        if not isinstance(entries, list) or not entries:
            continue
        primary = _as_mapping(entries[0])
        if primary is None:
            continue
        cvss_data = _as_mapping(primary.get("cvssData"))
        if cvss_data is None:
            continue
        score = _coerce_float(cvss_data.get("baseScore"))
        severity = _normalize_text(
            cvss_data.get("baseSeverity") or primary.get("baseSeverity")
        )
        return score, severity
    return None, None


def _extract_first_reference(references: Any) -> str | None:
    if not isinstance(references, list):
        return None
    for entry in references:
        if not isinstance(entry, Mapping):
            continue
        url = _normalize_text(entry.get("url"))
        if url:
            return url[:400]
    return None


def _read_cached_feed(
    settings: AppSettings,
    blob_name: str,
    *,
    ttl_seconds: int,
    model_cls: type[BaseModel],
    now_utc: datetime,
) -> Any:
    connection_string = settings.storage_connection_string
    if not connection_string:
        return None
    try:
        with BlobServiceClient.from_connection_string(connection_string) as service_client:
            container_client = service_client.get_container_client(
                PUBLIC_SECURITY_FEEDS_CONTAINER,
            )
            blob_client = container_client.get_blob_client(blob_name)
            try:
                payload_bytes = blob_client.download_blob().readall()
            except ResourceNotFoundError:
                return None
    except Exception as error:  # noqa: BLE001 - cache must never block the route
        logging.warning("Public security feed cache read failed (%s): %s", blob_name, error)
        return None

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
        feed = model_cls.model_validate(payload)
    except (ValidationError, ValueError, UnicodeDecodeError) as error:
        logging.warning("Public security feed cache parse failed (%s): %s", blob_name, error)
        return None

    cached_at = getattr(feed, "generated_at_utc", None)
    if cached_at is None or now_utc - cached_at > timedelta(seconds=ttl_seconds):
        return None
    return feed


def _write_cached_feed(
    settings: AppSettings,
    blob_name: str,
    feed: BaseModel,
) -> None:
    connection_string = settings.storage_connection_string
    if not connection_string:
        return
    try:
        payload_text = feed.model_dump_json(indent=2)
        with BlobServiceClient.from_connection_string(connection_string) as service_client:
            container_client = service_client.get_container_client(
                PUBLIC_SECURITY_FEEDS_CONTAINER,
            )
            try:
                container_client.create_container()
            except ResourceExistsError:
                pass
            container_client.upload_blob(blob_name, payload_text, overwrite=True)
    except Exception as error:  # noqa: BLE001 - cache write is best-effort
        logging.warning("Public security feed cache write failed (%s): %s", blob_name, error)


def _empty_cve_feed(settings: AppSettings, generated_at: datetime) -> PublicSecurityCveFeed:
    return PublicSecurityCveFeed(
        collection_mode=CVE_COLLECTION_MODE,
        generated_at_utc=generated_at,
        items=(),
        keyword_terms=tuple(settings.public_security_cve_keyword_terms),
        source=NVD_CVE_API_URL,
        total_count=0,
    )


def _empty_msrc_feed(settings: AppSettings, generated_at: datetime) -> PublicSecurityMsrcFeed:
    del settings
    return PublicSecurityMsrcFeed(
        collection_mode=MSRC_COLLECTION_MODE,
        generated_at_utc=generated_at,
        items=(),
        source=MSRC_CVRF_API_URL,
        total_count=0,
    )


def _fetch_json(url: str, headers: Mapping[str, str], timeout_seconds: float) -> dict[str, Any]:
    request_headers = {"User-Agent": _USER_AGENT, **dict(headers)}
    request = Request(url, headers=request_headers)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - URLs are constants
            payload_bytes = response.read()
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError(f"GET {url} failed: {error}") from error

    payload = json.loads(payload_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"GET {url} returned non-object payload")
    return payload


def _normalize_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _as_mapping(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _parse_iso_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
