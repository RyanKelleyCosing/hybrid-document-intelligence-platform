"""Unit tests for the AWS S3 to Azure Blob bridge helpers."""

from __future__ import annotations

from document_intelligence.aws_bridge import (
    build_blob_name,
    build_blob_target,
    build_document_id,
    build_ingestion_request,
)


def test_build_blob_name_strips_source_prefix() -> None:
    """Bridge blob names should drop the incoming prefix and add the target prefix."""
    blob_name = build_blob_name(
        "incoming/case-2001/maricopa-court-filing-summary.xlsx"
    )

    assert blob_name == "aws-s3/case-2001/maricopa-court-filing-summary.xlsx"


def test_build_blob_target_uses_az_uri() -> None:
    """Bridge targets should point at the raw-documents container using az:// syntax."""
    target = build_blob_target(
        container_name="raw-documents",
        source_key="incoming/case-1001/payroll.xlsx",
    )

    assert target.blob_name == "aws-s3/case-1001/payroll.xlsx"
    assert target.source_uri == "az://raw-documents/aws-s3/case-1001/payroll.xlsx"


def test_build_document_id_changes_with_etag() -> None:
    """Different object versions should produce different stable document ids."""
    first = build_document_id("demo-bucket", "incoming/case-1/doc.pdf", e_tag="a")
    second = build_document_id("demo-bucket", "incoming/case-1/doc.pdf", e_tag="b")

    assert first.startswith("aws-")
    assert second.startswith("aws-")
    assert first != second


def test_build_ingestion_request_uses_blob_reference_payload() -> None:
    """Bridge ingestion payloads should reference the uploaded Azure blob."""
    payload = build_ingestion_request(
        bucket_name="demo-bucket",
        source_key="incoming/case-2001/maricopa-court-filing-summary.xlsx",
        container_name="raw-documents",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        e_tag="etag-1",
    )

    assert payload["source"] == "aws_s3"
    assert payload["file_name"] == "maricopa-court-filing-summary.xlsx"
    assert payload["source_uri"] == (
        "az://raw-documents/aws-s3/case-2001/maricopa-court-filing-summary.xlsx"
    )
    assert payload["source_summary"] == (
        "Copied from s3://demo-bucket/incoming/case-2001/maricopa-court-filing-summary.xlsx"
    )