"""Helpers for verifying the private live admin deployment."""

from __future__ import annotations

import json
import socket
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from document_intelligence.utils.public_simulation_verifier import (
    resolve_azure_cli_executable,
    run_azure_cli_text,
)

REVIEW_API_ADMIN_KEY_HEADER = "x-docint-admin-key"
_EXPECTED_EXCLUDED_PATHS = frozenset({"/favicon.ico", "/favicon.svg"})
_MICROSOFT_LOGIN_HOST = "login.microsoftonline.com"


@dataclass(frozen=True)
class FunctionProxyTargetCheck:
    """Availability summary for the protected Functions API target."""

    content_type: str
    endpoint: str
    ok: bool
    status_code: int


@dataclass(frozen=True)
class PrivateLiveAppSettingsSummary:
    """Status summary for the private live site application settings."""

    allowed_reviewer_emails: tuple[str, ...]
    expected_allowed_user_present: bool
    function_api_base_url: str | None
    has_allowed_reviewer_email: bool
    has_function_api_base_url: bool
    has_review_api_admin_key: bool
    proxy_ready: bool


@dataclass(frozen=True)
class PrivateLiveAuthSettingsSummary:
    """Status summary for the private live App Service auth settings."""

    auth_ok: bool
    excluded_paths: tuple[str, ...]
    https_required: bool
    microsoft_provider_enabled: bool
    missing_expectations: tuple[str, ...]
    require_authentication: bool
    token_store_enabled: bool
    unauthenticated_client_action: str


@dataclass(frozen=True)
class PrivateLiveHostnameBindingSummary:
    """Binding summary for one custom hostname on the private live site."""

    binding_present: bool
    custom_domain_hostname: str
    host_name_type: str | None
    ssl_state: str | None
    thumbprint_present: bool


@dataclass(frozen=True)
class PrivateLiveSiteCheck:
    """Availability summary for one private live site URL."""

    auth_challenge: bool
    auth_redirect: bool
    content_type: str
    final_url: str
    is_reachable: bool
    status_code: int
    url: str


def _get_nested_mapping(
    payload: Mapping[str, Any],
    key: str,
) -> Mapping[str, Any]:
    candidate = payload.get(key)
    if isinstance(candidate, Mapping):
        return candidate
    return {}


def _normalize_optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        normalized_value = value.strip()
        if normalized_value:
            return normalized_value
    return None


def _parse_csv_tuple(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(
        item.strip().lower()
        for item in value.split(",")
        if item.strip()
    )


def normalize_private_live_site_url(private_site_url: str) -> str:
    """Return a normalized private live site URL with an explicit scheme."""
    normalized_url = private_site_url.strip().rstrip("/")
    if not normalized_url:
        raise ValueError("private_site_url is required")
    if not normalized_url.startswith(("http://", "https://")):
        raise ValueError("private_site_url must start with http:// or https://")
    return normalized_url


def is_auth_redirect(start_url: str, final_url: str) -> bool:
    """Return whether the final URL looks like an Easy Auth login redirect."""
    normalized_start_url = normalize_private_live_site_url(start_url)
    normalized_final_url = normalize_private_live_site_url(final_url)
    parsed_final_url = urlparse(normalized_final_url)

    if parsed_final_url.netloc.lower().endswith(_MICROSOFT_LOGIN_HOST):
        return True

    if "/.auth/login/" in parsed_final_url.path.lower():
        return True

    return (
        normalized_start_url != normalized_final_url
        and parsed_final_url.path.lower().startswith("/.auth/")
    )


def fetch_private_live_site_check(private_site_url: str) -> PrivateLiveSiteCheck:
    """Fetch the private live site and return its basic availability details."""
    normalized_url = normalize_private_live_site_url(private_site_url)
    request = Request(
        normalized_url,
        headers={"Accept": "text/html,application/xhtml+xml"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            final_url = response.geturl()
            auth_redirect = is_auth_redirect(normalized_url, final_url)
            return PrivateLiveSiteCheck(
                auth_challenge=auth_redirect,
                auth_redirect=auth_redirect,
                content_type=response.headers.get_content_type(),
                final_url=final_url,
                is_reachable=response.status == 200,
                status_code=response.status,
                url=normalized_url,
            )
    except HTTPError as error:
        if error.code not in {401, 403}:
            raise

        final_url = error.geturl() or normalized_url
        content_type = error.headers.get_content_type() if error.headers else "unknown"
        return PrivateLiveSiteCheck(
            auth_challenge=True,
            auth_redirect=is_auth_redirect(normalized_url, final_url),
            content_type=content_type,
            final_url=final_url,
            is_reachable=True,
            status_code=error.code,
            url=normalized_url,
        )


def resolve_hostname_addresses(host_name: str) -> tuple[str, ...]:
    """Resolve a hostname into one or more IP addresses."""
    normalized_host_name = host_name.strip()
    if not normalized_host_name:
        raise RuntimeError("host_name is required")

    try:
        address_info = socket.getaddrinfo(
            normalized_host_name,
            443,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as error:
        raise RuntimeError(str(error)) from error

    resolved_addresses = sorted(
        {
            address[0]
            for *_, sockaddr in address_info
            for address in [sockaddr]
            if isinstance(address, tuple) and address
        }
    )
    if not resolved_addresses:
        raise RuntimeError(f"Could not resolve hostname: {normalized_host_name}")

    return tuple(resolved_addresses)


def run_azure_cli_json(az_executable: str, args: list[str]) -> Any:
    """Run an Azure CLI command and return parsed JSON output."""
    output_text = run_azure_cli_text(az_executable, [*args, "--output", "json"])
    if not output_text:
        raise RuntimeError("Expected Azure CLI to return JSON output.")
    return json.loads(output_text)


def get_azure_cli_executable() -> str:
    """Return the Azure CLI executable path."""
    return resolve_azure_cli_executable()


def load_azure_webapp_summary(
    az_executable: str,
    resource_group_name: str,
    webapp_name: str,
) -> dict[str, Any]:
    """Load the private live App Service summary."""
    payload = run_azure_cli_json(
        az_executable,
        [
            "webapp",
            "show",
            "--resource-group",
            resource_group_name,
            "--name",
            webapp_name,
        ],
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Expected Azure webapp summary output to be a JSON object.")
    return payload


def load_azure_webapp_auth_settings(
    az_executable: str,
    resource_group_name: str,
    webapp_name: str,
) -> dict[str, Any]:
    """Load the private live App Service auth settings."""
    payload = run_azure_cli_json(
        az_executable,
        [
            "webapp",
            "auth",
            "show",
            "--resource-group",
            resource_group_name,
            "--name",
            webapp_name,
        ],
    )
    if not isinstance(payload, dict):
        raise RuntimeError(
            "Expected Azure webapp auth settings output to be a JSON object."
        )
    return payload


def load_azure_webapp_app_settings(
    az_executable: str,
    resource_group_name: str,
    webapp_name: str,
) -> dict[str, str]:
    """Load the private live App Service app settings."""
    payload = run_azure_cli_json(
        az_executable,
        [
            "webapp",
            "config",
            "appsettings",
            "list",
            "--resource-group",
            resource_group_name,
            "--name",
            webapp_name,
        ],
    )
    if not isinstance(payload, list):
        raise RuntimeError(
            "Expected Azure webapp app settings output to be a JSON list."
        )

    settings: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if isinstance(name, str) and value is not None:
            settings[name] = str(value)

    return settings


def load_azure_webapp_hostname_bindings(
    az_executable: str,
    resource_group_name: str,
    webapp_name: str,
) -> list[dict[str, Any]]:
    """Load the hostname bindings configured on the private live App Service."""
    payload = run_azure_cli_json(
        az_executable,
        [
            "webapp",
            "config",
            "hostname",
            "list",
            "--resource-group",
            resource_group_name,
            "--webapp-name",
            webapp_name,
        ],
    )
    if not isinstance(payload, list):
        raise RuntimeError(
            "Expected Azure webapp hostname binding output to be a JSON list."
        )

    return [item for item in payload if isinstance(item, dict)]


def summarize_private_live_auth_settings(
    auth_settings: Mapping[str, Any],
) -> PrivateLiveAuthSettingsSummary:
    """Summarize whether the private live auth settings match expectations."""
    properties = _get_nested_mapping(auth_settings, "properties")
    global_validation = _get_nested_mapping(properties, "globalValidation")
    http_settings = _get_nested_mapping(properties, "httpSettings")
    login_settings = _get_nested_mapping(properties, "login")
    identity_providers = _get_nested_mapping(properties, "identityProviders")
    azure_active_directory = _get_nested_mapping(
        identity_providers,
        "azureActiveDirectory",
    )

    excluded_paths = tuple(
        path
        for path in global_validation.get("excludedPaths", [])
        if isinstance(path, str) and path.strip()
        for path in [path.strip()]
    )
    require_authentication = bool(global_validation.get("requireAuthentication"))
    unauthenticated_client_action = (
        _normalize_optional_string(global_validation.get("unauthenticatedClientAction"))
        or "Unknown"
    )
    https_required = bool(http_settings.get("requireHttps"))
    token_store_enabled = bool(
        _get_nested_mapping(login_settings, "tokenStore").get("enabled")
    )
    microsoft_provider_enabled = bool(azure_active_directory.get("enabled"))

    missing_expectations: list[str] = []
    if not require_authentication:
        missing_expectations.append("require_authentication")
    if unauthenticated_client_action != "RedirectToLoginPage":
        missing_expectations.append("redirect_to_login")
    if not https_required:
        missing_expectations.append("require_https")
    if not token_store_enabled:
        missing_expectations.append("token_store")
    if not microsoft_provider_enabled:
        missing_expectations.append("microsoft_provider")

    missing_excluded_paths = sorted(_EXPECTED_EXCLUDED_PATHS.difference(excluded_paths))
    for missing_path in missing_excluded_paths:
        missing_expectations.append(f"excluded_path:{missing_path}")

    return PrivateLiveAuthSettingsSummary(
        auth_ok=not missing_expectations,
        excluded_paths=excluded_paths,
        https_required=https_required,
        microsoft_provider_enabled=microsoft_provider_enabled,
        missing_expectations=tuple(missing_expectations),
        require_authentication=require_authentication,
        token_store_enabled=token_store_enabled,
        unauthenticated_client_action=unauthenticated_client_action,
    )


def summarize_private_live_app_settings(
    values: Mapping[str, str],
    expected_allowed_user_email: str,
) -> PrivateLiveAppSettingsSummary:
    """Summarize whether the private live site app settings are ready."""
    allowed_reviewer_emails = _parse_csv_tuple(
        values.get("DOCINT_ALLOWED_REVIEWER_EMAILS")
    )
    function_api_base_url = _normalize_optional_string(
        values.get("DOCINT_FUNCTION_API_BASE_URL")
    )
    review_api_admin_key = _normalize_optional_string(
        values.get("DOCINT_REVIEW_API_ADMIN_KEY")
    )
    normalized_expected_allowed_user_email = expected_allowed_user_email.strip().lower()

    return PrivateLiveAppSettingsSummary(
        allowed_reviewer_emails=allowed_reviewer_emails,
        expected_allowed_user_present=(
            normalized_expected_allowed_user_email in allowed_reviewer_emails
            if normalized_expected_allowed_user_email
            else bool(allowed_reviewer_emails)
        ),
        function_api_base_url=function_api_base_url,
        has_allowed_reviewer_email=bool(allowed_reviewer_emails),
        has_function_api_base_url=function_api_base_url is not None,
        has_review_api_admin_key=review_api_admin_key is not None,
        proxy_ready=(
            function_api_base_url is not None and review_api_admin_key is not None
        ),
    )


def summarize_private_live_hostname_binding(
    hostname_bindings: Sequence[Mapping[str, Any]],
    custom_domain_hostname: str,
) -> PrivateLiveHostnameBindingSummary:
    """Summarize the configured binding for a requested custom domain."""
    normalized_custom_domain_hostname = custom_domain_hostname.strip().lower()
    for binding in hostname_bindings:
        binding_name = _normalize_optional_string(binding.get("name"))
        if (
            binding_name is None
            or binding_name.lower() != normalized_custom_domain_hostname
        ):
            continue

        ssl_state = _normalize_optional_string(binding.get("sslState"))
        host_name_type = _normalize_optional_string(binding.get("hostNameType"))
        thumbprint = _normalize_optional_string(binding.get("thumbprint"))
        return PrivateLiveHostnameBindingSummary(
            binding_present=True,
            custom_domain_hostname=normalized_custom_domain_hostname,
            host_name_type=host_name_type,
            ssl_state=ssl_state,
            thumbprint_present=thumbprint is not None,
        )

    return PrivateLiveHostnameBindingSummary(
        binding_present=False,
        custom_domain_hostname=normalized_custom_domain_hostname,
        host_name_type=None,
        ssl_state=None,
        thumbprint_present=False,
    )


def fetch_function_proxy_target_check(
    function_api_base_url: str,
    review_api_admin_key: str,
    *,
    path: str = "processing-taxonomy",
) -> FunctionProxyTargetCheck:
    """Fetch a protected Functions API route with the review admin key."""
    normalized_base_url = normalize_private_live_site_url(function_api_base_url)
    normalized_path = path.strip().lstrip("/")
    endpoint = (
        normalized_base_url
        if not normalized_path
        else f"{normalized_base_url.rstrip('/')}/{normalized_path}"
    )
    request = Request(
        endpoint,
        headers={
            "Accept": "application/json",
            REVIEW_API_ADMIN_KEY_HEADER: review_api_admin_key,
        },
        method="GET",
    )
    with urlopen(request, timeout=30) as response:
        return FunctionProxyTargetCheck(
            content_type=response.headers.get_content_type(),
            endpoint=endpoint,
            ok=response.status == 200,
            status_code=response.status,
        )


__all__ = [
    "FunctionProxyTargetCheck",
    "PrivateLiveAppSettingsSummary",
    "PrivateLiveAuthSettingsSummary",
    "PrivateLiveHostnameBindingSummary",
    "PrivateLiveSiteCheck",
    "REVIEW_API_ADMIN_KEY_HEADER",
    "fetch_function_proxy_target_check",
    "fetch_private_live_site_check",
    "get_azure_cli_executable",
    "is_auth_redirect",
    "load_azure_webapp_app_settings",
    "load_azure_webapp_auth_settings",
    "load_azure_webapp_hostname_bindings",
    "load_azure_webapp_summary",
    "normalize_private_live_site_url",
    "resolve_hostname_addresses",
    "summarize_private_live_app_settings",
    "summarize_private_live_auth_settings",
    "summarize_private_live_hostname_binding",
]