"""Post-scenario inspection helpers for review data and KQL results."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Any
from urllib.parse import urlparse

from document_intelligence.aws_bridge import (
    DEFAULT_SOURCE_PREFIX,
    DEFAULT_TARGET_PREFIX,
    build_blob_target,
    build_document_id,
)

DEFAULT_BLOB_CONTAINER_NAME = "raw-documents"

DEFAULT_HIGH_SEVERITY_QUERY = """
let lookback = 24h;
union isfuzzy=true withsource=SourceTable AppExceptions, AppTraces, AzureDiagnostics
| where TimeGenerated >= ago(lookback)
| extend SeverityValue = coalesce(
    tolong(column_ifexists('SeverityLevel', 0)),
    tolong(column_ifexists('Level', 0)),
    0
)
| extend Message = coalesce(
    tostring(column_ifexists('OuterMessage', '')),
    tostring(column_ifexists('Message', '')),
    tostring(column_ifexists('RenderedDescription', '')),
    tostring(column_ifexists('ResultDescription', ''))
)
| where SeverityValue >= 3
    or Message has_any ('critical', 'fatal', 'panic', 'sev0', 'sev1', 'high priority')
| summarize EventCount = count(), LatestEvent = max(TimeGenerated)
    by SourceTable, bin(TimeGenerated, 15m)
| order by TimeGenerated asc
""".strip()


@dataclass(frozen=True)
class S3DocumentReference:
    """Resolved bridge identifiers for an S3-backed document."""

    blob_name: str
    bucket_name: str
    document_id: str
    e_tag: str | None
    source_key: str
    source_uri: str
    version_id: str | None


def load_local_values(local_settings_file: Path) -> dict[str, str]:
    """Load the Values section from a local.settings.json file."""
    if not local_settings_file.exists():
        return {}

    payload = json.loads(local_settings_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}

    values = payload.get("Values")
    if not isinstance(values, dict):
        return {}

    return {
        str(key): str(value)
        for key, value in values.items()
        if value is not None
    }


def is_placeholder_value(value: str | None) -> bool:
    """Return whether a value is blank or still carries placeholder text."""
    if value is None:
        return True

    normalized_value = value.strip()
    return not normalized_value or normalized_value.startswith("__REPLACE_")


def build_review_items_query(
    limit: int,
    *,
    status: str | None = None,
    document_id: str | None = None,
    file_name: str | None = None,
    source: str | None = None,
) -> tuple[str, list[dict[str, object]]]:
    """Build a Cosmos SQL query for review item inspection."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    clauses: list[str] = []
    parameters: list[dict[str, object]] = []
    for field_name, parameter_name, value in (
        ("status", "@status", status),
        ("document_id", "@document_id", document_id),
        ("file_name", "@file_name", file_name),
        ("source", "@source", source),
    ):
        if value is None or not value.strip():
            continue

        clauses.append(f"c.{field_name} = {parameter_name}")
        parameters.append({"name": parameter_name, "value": value.strip()})

    filter_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    query = (
        f"SELECT TOP {limit} * FROM c{filter_clause} "
        "ORDER BY c.updated_at_utc DESC"
    )
    return query, parameters


def load_query_text(query_text: str | None, query_file: Path | None) -> str:
    """Resolve KQL from inline text, a file, or the default query."""
    if query_text is not None and query_text.strip():
        return query_text.strip()

    if query_file is None:
        return DEFAULT_HIGH_SEVERITY_QUERY

    resolved_query = query_file.read_text(encoding="utf-8").strip()
    if not resolved_query:
        raise ValueError(f"Query file '{query_file}' is empty.")

    return resolved_query


def extract_account_name_from_endpoint(endpoint: str | None) -> str | None:
    """Extract a Cosmos account name from a document endpoint URL."""
    if endpoint is None or not endpoint.strip():
        return None

    parsed_endpoint = urlparse(endpoint)
    host_name = parsed_endpoint.netloc.strip()
    if not host_name:
        return None

    return host_name.split(".", maxsplit=1)[0] or None


def parse_blob_source_uri(source_uri: str) -> tuple[str, str] | None:
    """Extract a container and blob path from an Azure blob-style source URI."""
    if source_uri.startswith("az://"):
        container_and_blob = source_uri.removeprefix("az://")
        container, _, blob_name = container_and_blob.partition("/")
        if container and blob_name:
            return container, blob_name

    parsed_uri = urlparse(source_uri)
    if parsed_uri.scheme not in {"http", "https"}:
        return None
    if ".blob.core." not in parsed_uri.netloc and ".dfs.core." not in parsed_uri.netloc:
        return None

    path = parsed_uri.path.lstrip("/")
    container, _, blob_name = path.partition("/")
    if container and blob_name:
        return container, blob_name

    return None


def resolve_azure_cli_executable() -> str:
    """Return the Azure CLI executable path."""
    for command_name in ("az", "az.cmd"):
        resolved_path = which(command_name)
        if resolved_path:
            return resolved_path

    for candidate_path in (
        Path("C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd"),
        Path("C:/Program Files (x86)/Microsoft SDKs/Azure/CLI2/wbin/az.cmd"),
    ):
        if candidate_path.exists():
            return str(candidate_path)

    raise RuntimeError("Azure CLI is required to resolve live Azure resources.")


def run_azure_cli_text(az_executable: str, args: list[str]) -> str:
    """Run an Azure CLI command and return stripped text output."""
    try:
        result = subprocess.run(
            [az_executable, *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        details = error.stderr.strip() or error.stdout.strip() or str(error)
        raise RuntimeError(details) from error

    return result.stdout.strip()


def resolve_storage_connection_string(
    azure_resource_group_name: str,
    local_values: dict[str, str],
    *,
    storage_account_name: str = "",
    storage_connection_string: str | None = None,
) -> tuple[str, str | None]:
    """Resolve the storage connection string from settings or Azure CLI."""
    resolved_connection_string = (
        storage_connection_string
        or local_values.get("DOCINT_STORAGE_CONNECTION_STRING")
        or local_values.get("AzureWebJobsStorage")
    )
    if resolved_connection_string and not is_placeholder_value(
        resolved_connection_string
    ):
        normalized_account_name = storage_account_name.strip() or None
        return resolved_connection_string.strip(), normalized_account_name

    az_executable = resolve_azure_cli_executable()
    normalized_account_name = storage_account_name.strip()
    if not normalized_account_name:
        normalized_account_name = run_azure_cli_text(
            az_executable,
            [
                "resource",
                "list",
                "--resource-group",
                azure_resource_group_name,
                "--resource-type",
                "Microsoft.Storage/storageAccounts",
                "--query",
                "[0].name",
                "--output",
                "tsv",
            ],
        )

    if not normalized_account_name:
        raise RuntimeError("Could not resolve a storage account name.")

    connection_string = run_azure_cli_text(
        az_executable,
        [
            "storage",
            "account",
            "show-connection-string",
            "--resource-group",
            azure_resource_group_name,
            "--name",
            normalized_account_name,
            "--query",
            "connectionString",
            "--output",
            "tsv",
        ],
    )
    if is_placeholder_value(connection_string):
        raise RuntimeError("Could not resolve a storage account connection string.")

    return connection_string.strip(), normalized_account_name


def normalize_e_tag(e_tag: str | None) -> str | None:
    """Normalize an S3 ETag into a stable unquoted value."""
    if e_tag is None:
        return None

    normalized_e_tag = e_tag.strip().strip('"')
    return normalized_e_tag or None


def normalize_version_id(version_id: str | None) -> str | None:
    """Normalize an optional S3 object version id."""
    if version_id is None:
        return None

    normalized_version_id = version_id.strip()
    return normalized_version_id or None


def build_s3_document_reference(
    bucket_name: str,
    source_key: str,
    *,
    blob_container_name: str = DEFAULT_BLOB_CONTAINER_NAME,
    e_tag: str | None = None,
    source_prefix: str = DEFAULT_SOURCE_PREFIX,
    target_prefix: str = DEFAULT_TARGET_PREFIX,
    version_id: str | None = None,
) -> S3DocumentReference:
    """Build the stable bridge identifiers for an uploaded S3 object."""
    normalized_e_tag = normalize_e_tag(e_tag)
    normalized_version_id = normalize_version_id(version_id)
    blob_target = build_blob_target(
        container_name=blob_container_name,
        source_key=source_key,
        source_prefix=source_prefix,
        target_prefix=target_prefix,
    )
    return S3DocumentReference(
        blob_name=blob_target.blob_name,
        bucket_name=bucket_name,
        document_id=build_document_id(
            bucket_name,
            source_key,
            e_tag=normalized_e_tag,
            version_id=normalized_version_id,
        ),
        e_tag=normalized_e_tag,
        source_key=source_key,
        source_uri=blob_target.source_uri,
        version_id=normalized_version_id,
    )


def tables_to_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a Log Analytics tables payload into row dictionaries."""
    tables = payload.get("tables")
    if not isinstance(tables, list):
        return []

    include_table_name = len(tables) > 1
    records: list[dict[str, Any]] = []
    for table in tables:
        if not isinstance(table, dict):
            continue

        columns = table.get("columns")
        rows = table.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            continue

        column_names = [
            _get_column_name(column, index)
            for index, column in enumerate(columns)
        ]
        table_name = table.get("name")
        normalized_table_name = (
            table_name.strip() if isinstance(table_name, str) else ""
        )
        for row in rows:
            if not isinstance(row, list):
                continue

            record: dict[str, Any] = {}
            for index, column_name in enumerate(column_names):
                record[column_name] = row[index] if index < len(row) else None

            if include_table_name and normalized_table_name:
                record["_table"] = normalized_table_name
            records.append(record)

    return records


def _get_column_name(column: Any, index: int) -> str:
    """Return a stable column name for a Log Analytics result table."""
    if isinstance(column, dict):
        name = column.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()

    return f"column_{index}"