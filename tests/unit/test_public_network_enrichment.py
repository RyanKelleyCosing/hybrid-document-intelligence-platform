"""Unit tests for provider-backed public network enrichment."""

from __future__ import annotations

import document_intelligence.public_network_enrichment as public_network_enrichment_module

from document_intelligence.public_network_enrichment import (
    IpApiIsPublicNetworkEnrichmentProvider,
    IpQualityScorePublicNetworkEnrichmentProvider,
    build_public_network_enrichment_provider,
)
from document_intelligence.settings import AppSettings


def test_build_public_network_enrichment_provider_returns_none_by_default() -> None:
    """Network enrichment should stay disabled until a real provider is configured."""

    settings = AppSettings.model_validate({"environment_name": "test"})

    provider = build_public_network_enrichment_provider(settings)

    assert provider is None


def test_ipqualityscore_provider_maps_public_safe_signals(monkeypatch) -> None:
    """IPQualityScore responses should map into bounded public-safe enrichment fields."""

    monkeypatch.setattr(
        public_network_enrichment_module,
        "_fetch_json_payload",
        lambda request_url, timeout_seconds: {
            "ASN": 8075,
            "ISP": "Microsoft",
            "active_vpn": False,
            "bot_status": False,
            "connection_type": "Data Center/Web Hosting/Transit",
            "fraud_score": 12,
            "organization": "Azure Front Door",
            "proxy": False,
            "recent_abuse": False,
            "success": True,
            "tor": False,
            "vpn": False,
        },
    )
    provider = IpQualityScorePublicNetworkEnrichmentProvider("demo-key")

    enrichment = provider.enrich("203.0.113.77")

    assert enrichment is not None
    assert enrichment.network_asn == "AS8075"
    assert enrichment.network_owner == "Azure Front Door"
    assert enrichment.hosting_provider == "Azure Front Door"
    assert enrichment.vpn_proxy_status == (
        "Data Center/Web Hosting/Transit path observed by IPQualityScore."
    )
    assert enrichment.reputation_summary == (
        "Low observed abuse risk · fraud score 12/100"
    )


def test_build_public_network_enrichment_provider_creates_ipqualityscore_adapter() -> None:
    """Configured provider settings should produce the matching adapter."""

    settings = AppSettings.model_validate(
        {
            "environment_name": "test",
            "public_network_enrichment_api_key": "demo-key",
            "public_network_enrichment_provider": "ipqualityscore",
        }
    )

    provider = build_public_network_enrichment_provider(settings)

    assert isinstance(provider, IpQualityScorePublicNetworkEnrichmentProvider)


def test_ipapiis_provider_maps_public_safe_signals(monkeypatch) -> None:
    """ipapi.is responses should map into bounded public-safe enrichment fields."""

    monkeypatch.setattr(
        public_network_enrichment_module,
        "_fetch_json_payload",
        lambda request_url, timeout_seconds: {
            "asn": {
                "abuser_score": "0.0001 (Very Low)",
                "asn": 6167,
                "org": "Verizon Business",
            },
            "company": {
                "abuser_score": "0 (Very Low)",
                "name": "Verizon Business",
            },
            "is_abuser": False,
            "is_datacenter": False,
            "is_proxy": False,
            "is_tor": False,
            "is_vpn": False,
            "location": {
                "country_code": "US",
                "state": "Ohio",
            },
        },
    )
    provider = IpApiIsPublicNetworkEnrichmentProvider()

    enrichment = provider.enrich("203.0.113.77")

    assert enrichment is not None
    assert enrichment.approximate_location == "US / Ohio"
    assert enrichment.network_asn == "AS6167"
    assert enrichment.network_owner == "Verizon Business"
    assert enrichment.hosting_provider is None
    assert enrichment.vpn_proxy_status is None
    assert enrichment.reputation_summary == (
        "Provider-backed abuse exposure 0 (Very Low) according to ipapi.is."
    )


def test_build_public_network_enrichment_provider_creates_ipapiis_adapter_without_key() -> None:
    """ipapi.is should be constructible without a provider key for low-volume use."""

    settings = AppSettings.model_validate(
        {
            "environment_name": "test",
            "public_network_enrichment_provider": "ipapi.is",
        }
    )

    provider = build_public_network_enrichment_provider(settings)

    assert isinstance(provider, IpApiIsPublicNetworkEnrichmentProvider)


def test_build_public_network_enrichment_provider_honors_feature_flag() -> None:
    """The enrichment feature flag should disable provider construction."""

    settings = AppSettings.model_validate(
        {
            "environment_name": "test",
            "public_network_enrichment_api_key": "demo-key",
            "public_network_enrichment_enabled": False,
            "public_network_enrichment_provider": "ipqualityscore",
        }
    )

    provider = build_public_network_enrichment_provider(settings)

    assert provider is None