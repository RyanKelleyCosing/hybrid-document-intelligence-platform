"""Provider-backed public network enrichment for the security posture route."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field

from document_intelligence.settings import AppSettings

_DEFAULT_IPQUALITYSCORE_BASE_URL = "https://www.ipqualityscore.com/api/json/ip"
_DEFAULT_IPAPIIS_BASE_URL = "https://api.ipapi.is"
_IPQUALITYSCORE_QUERY_PARAMS = {
    "allow_public_access_points": "true",
    "fast": "true",
    "strictness": "1",
}


class PublicNetworkEnrichment(BaseModel):
    """Bounded provider-backed network signals that are safe to show publicly."""

    model_config = ConfigDict(str_strip_whitespace=True)

    approximate_location: str | None = Field(default=None, max_length=160)
    hosting_provider: str | None = Field(default=None, max_length=160)
    network_asn: str | None = Field(default=None, max_length=32)
    network_owner: str | None = Field(default=None, max_length=160)
    reputation_summary: str | None = Field(default=None, max_length=200)
    vpn_proxy_status: str | None = Field(default=None, max_length=200)


class PublicNetworkEnrichmentProvider(Protocol):
    """Protocol for provider-backed public network enrichment lookups."""

    provider_name: str

    def enrich(self, client_ip: str) -> PublicNetworkEnrichment | None:
        """Return public-safe network enrichment for a client IP when available."""


def _normalize_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    normalized_value = value.strip()
    return normalized_value or None


def _normalize_asn(value: object) -> str | None:
    if isinstance(value, int):
        return f"AS{value}"

    normalized_value = _normalize_text(value)
    if normalized_value is None:
        return None

    return normalized_value if normalized_value.upper().startswith("AS") else f"AS{normalized_value}"


def _as_mapping(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        stripped_value = value.strip()
        if stripped_value.isdigit():
            return int(stripped_value)

    return None


def _looks_like_hosting_path(connection_type: str | None) -> bool:
    if connection_type is None:
        return False

    normalized_value = connection_type.lower()
    return any(
        token in normalized_value
        for token in ("cloud", "data center", "datacenter", "hosting", "transit")
    )


def _build_vpn_proxy_status(payload: Mapping[str, Any]) -> str | None:
    connection_type = _normalize_text(payload.get("connection_type"))
    if payload.get("active_tor") or payload.get("tor"):
        return "Tor or anonymity network detected by IPQualityScore."

    if payload.get("active_vpn") or payload.get("vpn"):
        return "VPN or tunneling provider detected by IPQualityScore."

    if payload.get("proxy"):
        return "Proxy service detected by IPQualityScore."

    if _looks_like_hosting_path(connection_type):
        return f"{connection_type} path observed by IPQualityScore."

    if connection_type:
        return f"{connection_type} path with no provider-backed VPN or proxy flags."

    return None


def _build_reputation_summary(payload: Mapping[str, Any]) -> str | None:
    fraud_score = _coerce_int(payload.get("fraud_score"))
    signal_labels: list[str] = []
    if payload.get("recent_abuse"):
        signal_labels.append("recent abuse reports")
    if payload.get("bot_status"):
        signal_labels.append("automation flags")

    if fraud_score is not None:
        if fraud_score >= 75:
            risk_prefix = "Elevated abuse risk"
        elif fraud_score >= 40:
            risk_prefix = "Moderate abuse risk"
        else:
            risk_prefix = "Low observed abuse risk"

        if signal_labels:
            return (
                f"{risk_prefix} · fraud score {fraud_score}/100 · {'; '.join(signal_labels)}"
            )

        return f"{risk_prefix} · fraud score {fraud_score}/100"

    if signal_labels:
        return f"Provider-backed reputation flags present · {'; '.join(signal_labels)}"

    return None


def _build_network_enrichment_from_ipqualityscore(
    payload: Mapping[str, Any],
) -> PublicNetworkEnrichment:
    organization = _normalize_text(payload.get("organization"))
    isp_name = _normalize_text(payload.get("ISP") or payload.get("isp"))
    connection_type = _normalize_text(payload.get("connection_type"))

    hosting_provider = None
    if _looks_like_hosting_path(connection_type):
        hosting_provider = organization or isp_name or connection_type

    return PublicNetworkEnrichment(
        hosting_provider=hosting_provider,
        network_asn=_normalize_asn(payload.get("ASN") or payload.get("asn")),
        network_owner=organization or isp_name,
        reputation_summary=_build_reputation_summary(payload),
        vpn_proxy_status=_build_vpn_proxy_status(payload),
    )


def _build_provider_approximate_location(
    country_code: object,
    region_name: object,
) -> str | None:
    country = _normalize_text(country_code)
    region = _normalize_text(region_name)
    location_parts = tuple(
        value
        for value in (country.upper() if country else None, region)
        if value and value.upper() not in {"T1", "XX", "UNKNOWN"}
    )
    if not location_parts:
        return None

    return " / ".join(dict.fromkeys(location_parts))


def _build_ipapiis_vpn_proxy_status(payload: Mapping[str, Any]) -> str | None:
    datacenter = _as_mapping(payload.get("datacenter"))
    vpn = _as_mapping(payload.get("vpn"))

    if payload.get("is_tor"):
        return "Tor exit node detected by ipapi.is."

    if payload.get("is_vpn"):
        vpn_service = _normalize_text(vpn.get("service")) if vpn else None
        if vpn_service:
            return f"VPN exit node detected by ipapi.is ({vpn_service})."

        return "VPN exit node detected by ipapi.is."

    if payload.get("is_proxy"):
        return "Proxy service detected by ipapi.is."

    if payload.get("is_datacenter"):
        datacenter_name = _normalize_text(datacenter.get("datacenter")) if datacenter else None
        if datacenter_name:
            return f"{datacenter_name} hosting path observed by ipapi.is."

        return "Hosting provider path observed by ipapi.is."

    return None


def _build_ipapiis_reputation_summary(payload: Mapping[str, Any]) -> str | None:
    company = _as_mapping(payload.get("company"))
    asn = _as_mapping(payload.get("asn"))
    company_score = _normalize_text(company.get("abuser_score")) if company else None
    asn_score = _normalize_text(asn.get("abuser_score")) if asn else None

    if payload.get("is_abuser"):
        if company_score:
            return f"Elevated abuse exposure according to ipapi.is ({company_score})."
        if asn_score:
            return f"Elevated abuse exposure according to ipapi.is ({asn_score})."

        return "Elevated abuse exposure according to ipapi.is."

    if company_score:
        return f"Provider-backed abuse exposure {company_score} according to ipapi.is."

    if asn_score:
        return f"ASN abuse exposure {asn_score} according to ipapi.is."

    return None


def _build_network_enrichment_from_ipapiis(
    payload: Mapping[str, Any],
) -> PublicNetworkEnrichment:
    asn = _as_mapping(payload.get("asn"))
    company = _as_mapping(payload.get("company"))
    datacenter = _as_mapping(payload.get("datacenter"))
    location = _as_mapping(payload.get("location"))

    hosting_provider = None
    if payload.get("is_datacenter"):
        hosting_provider = (
            (_normalize_text(datacenter.get("datacenter")) if datacenter else None)
            or (_normalize_text(company.get("name")) if company else None)
            or (_normalize_text(asn.get("org")) if asn else None)
        )

    network_owner = (
        (_normalize_text(company.get("name")) if company else None)
        or (_normalize_text(asn.get("org")) if asn else None)
    )

    return PublicNetworkEnrichment(
        approximate_location=_build_provider_approximate_location(
            location.get("country_code") if location else None,
            location.get("state") if location else None,
        ),
        hosting_provider=hosting_provider,
        network_asn=_normalize_asn(asn.get("asn") if asn else None),
        network_owner=network_owner,
        reputation_summary=_build_ipapiis_reputation_summary(payload),
        vpn_proxy_status=_build_ipapiis_vpn_proxy_status(payload),
    )


def _fetch_json_payload(request_url: str, timeout_seconds: float) -> dict[str, Any] | None:
    request = Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "hybrid-document-intelligence-platform/public-security/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        logging.warning("Public network enrichment lookup failed: %s", error)
        return None

    if not isinstance(payload, dict):
        logging.warning("Public network enrichment payload was not a JSON object.")
        return None

    return payload


class IpQualityScorePublicNetworkEnrichmentProvider:
    """Resolve public-safe enrichment fields via IPQualityScore."""

    provider_name = "IPQualityScore"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = _DEFAULT_IPQUALITYSCORE_BASE_URL,
        timeout_seconds: float = 3.0,
    ) -> None:
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def enrich(self, client_ip: str) -> PublicNetworkEnrichment | None:
        """Return bounded IPQualityScore-backed enrichment for a client IP."""

        request_url = (
            f"{self._base_url}/{quote(self._api_key, safe='')}/{quote(client_ip, safe='')}?"
            f"{urlencode(_IPQUALITYSCORE_QUERY_PARAMS)}"
        )
        payload = _fetch_json_payload(request_url, self._timeout_seconds)
        if payload is None:
            return None

        if payload.get("success") is False:
            logging.warning(
                "IPQualityScore enrichment was rejected: %s",
                payload.get("message", "unknown response"),
            )
            return None

        return _build_network_enrichment_from_ipqualityscore(payload)


class IpApiIsPublicNetworkEnrichmentProvider:
    """Resolve public-safe enrichment fields via ipapi.is."""

    provider_name = "ipapi.is"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = _DEFAULT_IPAPIIS_BASE_URL,
        timeout_seconds: float = 3.0,
    ) -> None:
        self._api_key = api_key.strip() if isinstance(api_key, str) else ""
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def enrich(self, client_ip: str) -> PublicNetworkEnrichment | None:
        """Return bounded ipapi.is-backed enrichment for a client IP."""

        request_params = {"q": client_ip}
        if self._api_key:
            request_params["key"] = self._api_key

        request_url = f"{self._base_url}?{urlencode(request_params)}"
        payload = _fetch_json_payload(request_url, self._timeout_seconds)
        if payload is None:
            return None

        error_message = _normalize_text(payload.get("error"))
        if error_message:
            logging.warning("ipapi.is enrichment was rejected: %s", error_message)
            return None

        return _build_network_enrichment_from_ipapiis(payload)


def _resolve_provider_base_url(provider_name: str, configured_base_url: str) -> str:
    normalized_base_url = configured_base_url.strip().rstrip("/")
    if provider_name in {"ipapiis", "ipapi.is"}:
        if normalized_base_url in {"", _DEFAULT_IPQUALITYSCORE_BASE_URL}:
            return _DEFAULT_IPAPIIS_BASE_URL

        return normalized_base_url

    if normalized_base_url in {"", _DEFAULT_IPAPIIS_BASE_URL}:
        return _DEFAULT_IPQUALITYSCORE_BASE_URL

    return normalized_base_url


def build_public_network_enrichment_provider(
    settings: AppSettings,
) -> PublicNetworkEnrichmentProvider | None:
    """Build the configured provider-backed public network enrichment adapter."""

    if not settings.public_network_enrichment_enabled:
        return None

    provider_name = settings.public_network_enrichment_provider.strip().lower()
    if provider_name in {"", "none"}:
        return None

    resolved_base_url = _resolve_provider_base_url(
        provider_name,
        settings.public_network_enrichment_base_url,
    )

    if provider_name in {"ipqualityscore", "ipqs"}:
        if not settings.public_network_enrichment_api_key:
            logging.warning(
                "Public network enrichment provider %s is configured without an API key.",
                provider_name,
            )
            return None

        return IpQualityScorePublicNetworkEnrichmentProvider(
            settings.public_network_enrichment_api_key,
            base_url=resolved_base_url,
            timeout_seconds=settings.public_network_enrichment_timeout_seconds,
        )

    if provider_name in {"ipapiis", "ipapi.is"}:
        return IpApiIsPublicNetworkEnrichmentProvider(
            settings.public_network_enrichment_api_key,
            base_url=resolved_base_url,
            timeout_seconds=settings.public_network_enrichment_timeout_seconds,
        )

    logging.warning(
        "Unknown public network enrichment provider '%s'. Falling back to disabled enrichment.",
        settings.public_network_enrichment_provider,
    )
    return None