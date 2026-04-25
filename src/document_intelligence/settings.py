"""Environment-backed settings for the document intelligence platform."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="DOCINT_",
        case_sensitive=False,
        extra="ignore",
    )

    environment_name: str = "dev"
    raw_container_name: str = "raw-documents"
    processed_container_name: str = "processed-documents"
    quarantine_container_name: str = "quarantine-documents"
    ingestion_queue_name: str = "document-ingestion"
    review_queue_name: str = "manual-review"
    storage_connection_string: str | None = None
    document_intelligence_endpoint: str | None = None
    document_intelligence_key: str | None = None
    document_intelligence_model_id: str = "prebuilt-layout"
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_deployment: str = "gpt4o-deployment"
    azure_openai_api_version: str = "2024-10-21"
    cosmos_endpoint: str | None = None
    cosmos_key: str | None = None
    cosmos_database_name: str = "docintel"
    cosmos_review_container_name: str = "review-items"
    service_bus_connection_string: str | None = None
    sql_connection_string: str | None = None
    sql_account_table_name: str = "dbo.AccountMaster"
    sql_lookup_top_n: int = Field(default=10, ge=1, le=100)
    function_api_base_url: str | None = None
    review_api_admin_key: str | None = None
    review_api_default_limit: int = Field(default=25, ge=1, le=200)
    review_api_proxy_timeout_seconds: int = Field(default=30, ge=1, le=120)
    configured_folder_min_stable_age_seconds: int = Field(default=0, ge=0, le=3600)
    packet_max_total_bytes: int = Field(
        default=50 * 1024 * 1024,
        ge=1,
        le=250 * 1024 * 1024,
    )
    classification_drift_confidence_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
    )
    recommendation_guardrail_confidence_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
    )
    ocr_rotation_angle_warning_degrees: float = Field(default=5.0, ge=0.0, le=90.0)
    ocr_low_resolution_page_pixels: int = Field(default=1000, ge=1, le=10000)
    allow_quarantined_document_previews: bool = False
    mask_sensitive_history: bool = True
    low_confidence_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    public_traffic_alerts_enabled: bool = False
    public_alert_ignored_ip_prefixes: Annotated[tuple[str, ...], NoDecode] = ()
    public_alert_ignored_user_agent_substrings: Annotated[tuple[str, ...], NoDecode] = (
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
    public_alert_allowed_user_agent_substrings: Annotated[tuple[str, ...], NoDecode] = ()
    public_alert_suppress_datacenter_traffic: bool = True
    public_alert_suppress_no_referrer_deep_links: bool = True
    public_alert_landing_routes: Annotated[tuple[str, ...], NoDecode] = (
        "home",
        "/",
        "",
        "index",
        "landing",
    )
    public_health_digest_max_checks: int = Field(default=5, ge=1, le=20)
    public_health_digest_window_days: int = Field(default=7, ge=1, le=30)
    public_alert_recipient_email: str | None = None
    public_cost_history_container_name: str = "cost-optimizer-history"
    public_cost_history_directory: Path = Path("outputs") / "cost-report" / "history"
    public_cost_query_base_delay_seconds: float = Field(
        default=5.0,
        ge=0.0,
        le=120.0,
    )
    public_cost_query_max_attempts: int = Field(default=4, ge=1, le=10)
    public_cost_query_max_delay_seconds: float = Field(
        default=45.0,
        ge=1.0,
        le=300.0,
    )
    public_cost_refresh_enabled: bool = True
    public_cost_subscription_id: str | None = None
    public_network_enrichment_enabled: bool = True
    public_network_enrichment_api_key: str | None = None
    public_network_enrichment_base_url: str = (
        "https://www.ipqualityscore.com/api/json/ip"
    )
    public_network_enrichment_provider: str = "none"
    public_network_enrichment_timeout_seconds: float = Field(
        default=3.0,
        ge=0.5,
        le=30.0,
    )
    public_security_cve_cache_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    public_security_cve_feed_enabled: bool = True
    public_security_cve_keyword_terms: Annotated[tuple[str, ...], NoDecode] = (
        "azure functions",
        "python",
        "react",
    )
    public_security_cve_max_items: int = Field(default=10, ge=1, le=50)
    public_security_globe_enabled: bool = True
    public_security_msrc_cache_ttl_seconds: int = Field(default=21600, ge=300, le=172800)
    public_security_msrc_feed_enabled: bool = True
    public_security_msrc_max_items: int = Field(default=10, ge=1, le=50)
    public_site_url: str | None = None
    public_telemetry_history_container_name: str = "public-site-telemetry"
    public_telemetry_history_directory: Path = Path("outputs") / "public-site-telemetry"
    public_telemetry_retention_days: int = Field(default=60, ge=1, le=365)
    public_traffic_daily_digest_enabled: bool = False
    smtp_host: str | None = None
    smtp_password: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_sender_email: str | None = None
    smtp_use_tls: bool = True
    smtp_username: str | None = None
    allowed_reviewer_emails: Annotated[tuple[str, ...], NoDecode] = ()
    required_fields: Annotated[tuple[str, ...], NoDecode] = (
        "account_number",
        "statement_date",
    )
    review_app_origin: str = "http://localhost:5173"

    @staticmethod
    def _parse_csv_tuple(value: Any) -> Any:
        """Convert a comma-delimited setting into a normalized tuple."""
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("required_fields", mode="before")
    @classmethod
    def parse_required_fields(cls, value: Any) -> Any:
        """Allow required fields to be supplied as a comma-delimited string."""
        return cls._parse_csv_tuple(value)

    @field_validator("allowed_reviewer_emails", mode="before")
    @classmethod
    def parse_allowed_reviewer_emails(cls, value: Any) -> Any:
        """Allow reviewer emails to be supplied as a comma-delimited string."""
        parsed_value = cls._parse_csv_tuple(value)
        if isinstance(parsed_value, tuple):
            return tuple(item.lower() for item in parsed_value)
        return parsed_value

    @field_validator("public_alert_ignored_ip_prefixes", mode="before")
    @classmethod
    def parse_public_alert_ignored_ip_prefixes(cls, value: Any) -> Any:
        """Allow ignored IP prefixes to be supplied as a comma-delimited string."""
        return cls._parse_csv_tuple(value)

    @field_validator("public_alert_ignored_user_agent_substrings", mode="before")
    @classmethod
    def parse_public_alert_ignored_user_agent_substrings(cls, value: Any) -> Any:
        """Allow ignored user-agent substrings to be supplied as a comma-delimited string."""
        parsed_value = cls._parse_csv_tuple(value)
        if isinstance(parsed_value, tuple):
            return tuple(item.lower() for item in parsed_value)
        return parsed_value

    @field_validator("public_alert_allowed_user_agent_substrings", mode="before")
    @classmethod
    def parse_public_alert_allowed_user_agent_substrings(cls, value: Any) -> Any:
        """Allow opt-in user-agent substrings to be supplied as a comma-delimited string."""
        parsed_value = cls._parse_csv_tuple(value)
        if isinstance(parsed_value, tuple):
            return tuple(item.lower() for item in parsed_value)
        return parsed_value

    @field_validator("public_alert_landing_routes", mode="before")
    @classmethod
    def parse_public_alert_landing_routes(cls, value: Any) -> Any:
        """Allow landing-route allow list to be supplied as a comma-delimited string."""
        parsed_value = cls._parse_csv_tuple(value)
        if isinstance(parsed_value, tuple):
            return tuple(item.lower() for item in parsed_value)
        return parsed_value

    @field_validator("public_security_cve_keyword_terms", mode="before")
    @classmethod
    def parse_public_security_cve_keyword_terms(cls, value: Any) -> Any:
        """Allow CVE keyword terms to be supplied as a comma-delimited string."""
        parsed_value = cls._parse_csv_tuple(value)
        if isinstance(parsed_value, tuple):
            return tuple(item.lower() for item in parsed_value)
        return parsed_value


@lru_cache
def get_settings() -> AppSettings:
    """Return the cached application settings instance."""
    return AppSettings()