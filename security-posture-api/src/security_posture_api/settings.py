"""Environment-backed settings for the extracted public security API."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Public security API settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="DOCINT_",
        case_sensitive=False,
        extra="ignore",
    )

    environment_name: str = "dev"
    function_api_base_url: str | None = None
    public_alert_allowed_user_agent_substrings: tuple[str, ...] = ()
    public_alert_ignored_ip_prefixes: tuple[str, ...] = ()
    public_alert_ignored_user_agent_substrings: tuple[str, ...] = (
        "googlebot",
        "bingbot",
        "applebot",
        "yandexbot",
        "duckduckbot",
        "baiduspider",
        "ahrefsbot",
        "semrushbot",
        "mj12bot",
        "petalbot",
        "facebookexternalhit",
        "slurp",
    )
    public_alert_landing_routes: tuple[str, ...] = (
        "home",
        "/",
        "",
        "index",
        "landing",
    )
    public_alert_recipient_email: str | None = None
    public_alert_suppress_datacenter_traffic: bool = True
    public_alert_suppress_no_referrer_deep_links: bool = True
    public_health_digest_max_checks: int = Field(default=5, ge=1, le=20)
    public_health_digest_window_days: int = Field(default=7, ge=1, le=30)
    public_network_enrichment_api_key: str = ""
    public_network_enrichment_base_url: str = ""
    public_network_enrichment_enabled: bool = True
    public_network_enrichment_provider: str = "none"
    public_network_enrichment_timeout_seconds: float = Field(default=3.0, ge=0.5, le=30)
    public_site_url: str | None = None
    public_telemetry_history_container_name: str = "public-site-telemetry"
    public_telemetry_history_directory: Path = (
        Path("outputs") / "public-site-telemetry"
    )
    public_telemetry_retention_days: int = Field(default=60, ge=1, le=365)
    public_traffic_alerts_enabled: bool = False
    public_traffic_daily_digest_enabled: bool = False
    smtp_host: str | None = None
    smtp_password: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_sender_email: str | None = None
    smtp_use_tls: bool = True
    smtp_username: str | None = None
    storage_connection_string: str | None = None


@lru_cache
def get_settings() -> AppSettings:
    """Return the cached application settings instance."""

    return AppSettings()
