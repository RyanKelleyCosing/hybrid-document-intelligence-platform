"""Unit tests for post-scenario inspection helpers."""

from __future__ import annotations

import json
from pathlib import Path

from document_intelligence.inspection import (
    DEFAULT_HIGH_SEVERITY_QUERY,
    build_review_items_query,
    build_s3_document_reference,
    extract_account_name_from_endpoint,
    is_placeholder_value,
    load_local_values,
    load_query_text,
    normalize_e_tag,
    parse_blob_source_uri,
    tables_to_records,
)


def test_load_local_values_reads_values_section(tmp_path: Path) -> None:
    """local.settings.json values should load as strings."""
    local_settings_path = tmp_path / "local.settings.json"
    local_settings_path.write_text(
        json.dumps(
            {
                "Values": {
                    "DOCINT_COSMOS_DATABASE_NAME": "docintel",
                    "DOCINT_REVIEW_QUEUE_NAME": "manual-review",
                }
            }
        ),
        encoding="utf-8",
    )

    values = load_local_values(local_settings_path)

    assert values == {
        "DOCINT_COSMOS_DATABASE_NAME": "docintel",
        "DOCINT_REVIEW_QUEUE_NAME": "manual-review",
    }


def test_is_placeholder_value_identifies_blank_and_placeholder_text() -> None:
    """Blank and placeholder secrets should be treated as unresolved."""
    assert is_placeholder_value(None)
    assert is_placeholder_value("")
    assert is_placeholder_value("__REPLACE_WITH_COSMOS_KEY__")
    assert not is_placeholder_value("live-secret-value")


def test_build_review_items_query_adds_requested_filters() -> None:
    """Review item queries should include the supplied filters and parameters."""
    query, parameters = build_review_items_query(
        10,
        status="pending_review",
        document_id="aws-123",
        file_name="court.xlsx",
        source="aws_s3",
    )

    assert "SELECT TOP 10 * FROM c WHERE" in query
    assert "c.status = @status" in query
    assert "c.document_id = @document_id" in query
    assert "c.file_name = @file_name" in query
    assert "c.source = @source" in query
    assert parameters == [
        {"name": "@status", "value": "pending_review"},
        {"name": "@document_id", "value": "aws-123"},
        {"name": "@file_name", "value": "court.xlsx"},
        {"name": "@source", "value": "aws_s3"},
    ]


def test_load_query_text_defaults_to_builtin_query() -> None:
    """The built-in high-severity KQL should be used when no query is provided."""
    assert load_query_text(None, None) == DEFAULT_HIGH_SEVERITY_QUERY


def test_extract_account_name_from_endpoint_parses_cosmos_host() -> None:
    """Cosmos document endpoints should resolve to their account name."""
    assert (
        extract_account_name_from_endpoint(
            "https://cosdoctestnwigok.documents.azure.com:443/"
        )
        == "cosdoctestnwigok"
    )


def test_normalize_e_tag_strips_quotes() -> None:
    """Quoted S3 ETags should normalize to their stable raw value."""
    assert normalize_e_tag('"etag-123"') == 'etag-123'


def test_build_s3_document_reference_resolves_blob_and_document_id() -> None:
    """S3 object metadata should resolve to the bridge blob and document id."""
    reference = build_s3_document_reference(
        'demo-bucket',
        'incoming/case-2001/maricopa-court-filing-summary.xlsx',
        e_tag='"etag-1"',
        version_id='version-2',
    )

    assert reference.blob_name == 'aws-s3/case-2001/maricopa-court-filing-summary.xlsx'
    assert reference.source_uri == (
        'az://raw-documents/aws-s3/case-2001/maricopa-court-filing-summary.xlsx'
    )
    assert reference.document_id.startswith('aws-')
    assert reference.e_tag == 'etag-1'
    assert reference.version_id == 'version-2'


def test_parse_blob_source_uri_handles_az_scheme() -> None:
    """Azure blob shorthand URIs should resolve to container and blob name."""
    assert parse_blob_source_uri(
        'az://raw-documents/aws-s3/case-2001/maricopa-court-filing-summary.xlsx'
    ) == (
        'raw-documents',
        'aws-s3/case-2001/maricopa-court-filing-summary.xlsx',
    )


def test_tables_to_records_flattens_log_analytics_tables() -> None:
    """Log Analytics table payloads should flatten into row dictionaries."""
    payload = {
        "tables": [
            {
                "columns": [
                    {"name": "Message"},
                    {"name": "Severity"},
                ],
                "rows": [["Failure detected", 4]],
            }
        ]
    }

    records = tables_to_records(payload)

    assert records == [{"Message": "Failure detected", "Severity": 4}]