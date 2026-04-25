"""Unit tests for routing and normalization helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from document_intelligence.models import (
    DocumentIngestionRequest,
    DocumentSource,
    ExtractedField,
    IssuerCategory,
    PromptProfileId,
)
from document_intelligence.orchestration import (
    build_processing_preview,
    normalize_request,
)
from document_intelligence.settings import AppSettings


def create_request(
    extracted_fields: tuple[ExtractedField, ...],
    account_candidates: tuple[str, ...] = ("acct-1001",),
    issuer_category: IssuerCategory = IssuerCategory.UNKNOWN,
    issuer_name: str | None = None,
    source_tags: tuple[str, ...] = (),
) -> DocumentIngestionRequest:
    """Build a representative synthetic request for tests."""
    return DocumentIngestionRequest(
        document_id="doc-1001",
        source=DocumentSource.AZURE_SFTP,
        source_uri="sftp://landing/case-1001\\statement.pdf",
        issuer_category=issuer_category,
        issuer_name=issuer_name,
        file_name="landing\\statement.pdf",
        content_type="application/pdf",
        received_at_utc=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        source_tags=source_tags,
        extracted_fields=extracted_fields,
        account_candidates=account_candidates,
    )


def test_normalize_request_keeps_highest_confidence_field_value() -> None:
    """Normalization should collapse duplicate fields by best confidence."""
    request = create_request(
        extracted_fields=(
            ExtractedField(name="Account_Number", value="111", confidence=0.62),
            ExtractedField(name="account_number", value="222", confidence=0.94),
        )
    )

    normalized_request = normalize_request(request)

    assert normalized_request.file_name == "statement.pdf"
    assert normalized_request.source_uri == "sftp://landing/case-1001/statement.pdf"
    assert normalized_request.source_tags == ()
    assert normalized_request.extracted_fields == (
        ExtractedField(name="account_number", value="222", confidence=0.94),
    )


def test_build_processing_preview_routes_low_confidence_documents_to_review() -> None:
    """Low confidence and ambiguous matches should trigger manual review."""
    request = create_request(
        extracted_fields=(
            ExtractedField(name="account_number", value="ACC-101", confidence=0.72),
            ExtractedField(name="debtor_name", value="Taylor Reed", confidence=0.88),
        ),
        account_candidates=("acct-1001", "acct-9102"),
    )
    settings = AppSettings(
        low_confidence_threshold=0.8,
        required_fields=("account_number", "statement_date"),
    )

    preview = build_processing_preview(request, settings)

    assert preview.target_status == "pending_review"
    assert preview.review_item is not None
    assert preview.prompt_profile.primary_profile_id == PromptProfileId.BANK_STATEMENT
    assert preview.review_decision.requires_manual_review is True
    assert preview.review_decision.missing_required_fields == ("statement_date",)
    assert preview.review_item.account_candidates == ("acct-1001", "acct-9102")


def test_build_processing_preview_allows_high_confidence_documents_to_continue(
) -> None:
    """Complete, high-confidence payloads should stay out of manual review."""
    request = create_request(
        extracted_fields=(
            ExtractedField(name="account_number", value="ACC-101", confidence=0.97),
            ExtractedField(name="statement_date", value="2026-03-31", confidence=0.96),
            ExtractedField(name="debtor_name", value="Taylor Reed", confidence=0.93),
        )
    )
    settings = AppSettings(
        low_confidence_threshold=0.8,
        required_fields=("account_number", "statement_date"),
    )

    preview = build_processing_preview(request, settings)

    assert preview.target_status == "ready_for_enrichment"
    assert preview.review_item is None
    assert preview.review_decision.requires_manual_review is False


def test_build_processing_preview_respects_explicit_issuer_category() -> None:
    """Explicit issuer categories should force the matching prompt profile."""
    request = create_request(
        extracted_fields=(
            ExtractedField(name="account_number", value="ACC-101", confidence=0.95),
            ExtractedField(name="statement_date", value="2026-03-31", confidence=0.96),
        ),
        issuer_category=IssuerCategory.BANK,
        issuer_name="Northwind Credit Union",
    )
    settings = AppSettings()

    preview = build_processing_preview(request, settings)

    assert preview.prompt_profile.primary_profile_id == PromptProfileId.BANK_STATEMENT
    assert preview.prompt_profile.selection_mode == "explicit"