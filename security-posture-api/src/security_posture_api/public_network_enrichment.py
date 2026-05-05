"""Public-safe provider abstractions for network enrichment."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from security_posture_api.settings import AppSettings


class PublicNetworkEnrichment(BaseModel):
    """Bounded provider-backed network signals safe for public display."""

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
        """Return bounded enrichment details for a client IP when available."""


class IpQualityScorePublicNetworkEnrichmentProvider:
    """Placeholder provider adapter for IPQualityScore integration."""

    provider_name = "IPQualityScore"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def enrich(self, client_ip: str) -> PublicNetworkEnrichment | None:
        del client_ip
        return None


class IpApiIsPublicNetworkEnrichmentProvider:
    """Placeholder provider adapter for ipapi.is integration."""

    provider_name = "ipapi.is"

    def enrich(self, client_ip: str) -> PublicNetworkEnrichment | None:
        del client_ip
        return None


def build_public_network_enrichment_provider(
    settings: AppSettings,
) -> PublicNetworkEnrichmentProvider | None:
    """Build a provider adapter from environment settings."""

    if not settings.public_network_enrichment_enabled:
        return None

    provider_name = settings.public_network_enrichment_provider.strip().lower()
    if provider_name in {"", "none"}:
        return None

    if provider_name in {"ipapiis", "ipapi.is"}:
        return IpApiIsPublicNetworkEnrichmentProvider()

    if provider_name in {"ipqualityscore", "ipqs"}:
        if not settings.public_network_enrichment_api_key:
            return None
        return IpQualityScorePublicNetworkEnrichmentProvider(
            settings.public_network_enrichment_api_key,
        )

    return None
