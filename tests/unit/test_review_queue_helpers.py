"""Unit tests for review queue decision and serialization helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from document_intelligence.models import (
    AccountMatchResult,
    AccountMatchStatus,
    DocumentAnalysisResult,
    DocumentIngestionRequest,
    DocumentSource,
    ExtractedField,
    IssuerCategory,
    ProfileSelectionMode,
    PromptProfileId,
    PromptProfileSelection,
    ReviewDecision,
    ReviewReason,
    ReviewStatus,
)
from document_intelligence.review_queue import (
    build_review_item,
    should_route_to_manual_review,
)


def create_request(
    *,
    account_candidates: tuple[str, ...] = ("acct-1001",),
    document_text: str | None = None,
    extracted_fields: tuple[ExtractedField, ...] = (),
    issuer_category: IssuerCategory = IssuerCategory.UNKNOWN,
) -> DocumentIngestionRequest:
    """Build a representative request for review-queue helper tests."""

    return DocumentIngestionRequest(
        document_id="doc-2001",
        source=DocumentSource.SCANNED_UPLOAD,
        source_uri="manual://packets/doc-2001",
        issuer_category=issuer_category,
        issuer_name="Northwind",
        file_name="statement.pdf",
        content_type="application/pdf",
        received_at_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        extracted_fields=extracted_fields,
        account_candidates=account_candidates,
        document_text=document_text,
        source_summary="demo summary",
    )


def create_prompt_profile() -> PromptProfileSelection:
    """Build a representative prompt profile for review queue tests."""

    return PromptProfileSelection(
        document_type_hints=("bank_statement",),
        issuer_category=IssuerCategory.BANK,
        primary_profile_id=PromptProfileId.BANK_STATEMENT,
        selection_mode=ProfileSelectionMode.HEURISTIC,
        system_prompt="Extract bank statement data.",
    )


def test_should_route_to_manual_review_collects_low_confidence_and_missing_fields(
) -> None:
    """Low-confidence requests with missing fields and no account match should queue."""

    request = create_request(
        account_candidates=(),
        extracted_fields=(
            ExtractedField(name="account_number", value="ACC-101", confidence=0.62),
        ),
    )

    decision = should_route_to_manual_review(
        request,
        required_fields=("account_number", "statement_date"),
        low_confidence_threshold=0.8,
    )

    assert decision.requires_manual_review is True
    assert decision.reasons == (
        ReviewReason.LOW_CONFIDENCE,
        ReviewReason.MISSING_REQUIRED_FIELD,
        ReviewReason.UNMATCHED_ACCOUNT,
    )
    assert decision.average_confidence == 0.62
    assert decision.minimum_confidence == 0.62
    assert decision.missing_required_fields == ("statement_date",)


def test_should_route_to_manual_review_flags_multiple_account_candidates() -> None:
    """Ambiguous account matches should queue even when fields are present."""

    request = create_request(
        account_candidates=("acct-1001", "acct-2002"),
        extracted_fields=(
            ExtractedField(name="account_number", value="ACC-101", confidence=0.94),
            ExtractedField(name="statement_date", value="2026-04-14", confidence=0.97),
        ),
    )

    decision = should_route_to_manual_review(
        request,
        required_fields=("account_number", "statement_date"),
        low_confidence_threshold=0.8,
    )

    assert decision.requires_manual_review is True
    assert decision.reasons == (ReviewReason.MULTIPLE_ACCOUNT_CANDIDATES,)
    assert decision.missing_required_fields == ()
    assert decision.minimum_confidence == 0.94


def test_build_review_item_uses_preview_fallbacks_when_results_are_missing() -> None:
    """Preview-mode review items should derive defaults from the request and profile."""

    request = create_request(
        account_candidates=("acct-1001", "acct-2002"),
        document_text="A" * 700,
        extracted_fields=(
            ExtractedField(name="account_number", value="ACC-101", confidence=0.91),
        ),
    )
    decision = ReviewDecision(
        requires_manual_review=True,
        reasons=(ReviewReason.MULTIPLE_ACCOUNT_CANDIDATES,),
        average_confidence=0.91,
        minimum_confidence=0.91,
        missing_required_fields=(),
    )

    review_item = build_review_item(request, decision, create_prompt_profile())

    assert review_item.status == ReviewStatus.PENDING_REVIEW
    assert review_item.document_type == "bank_statement"
    assert review_item.issuer_category == IssuerCategory.BANK
    assert review_item.account_match is not None
    assert review_item.account_match.status == AccountMatchStatus.AMBIGUOUS
    assert review_item.selected_account_id is None
    assert review_item.account_candidates == ("acct-1001", "acct-2002")
    assert review_item.ocr_text_excerpt == "A" * 600
    assert review_item.extracted_fields == request.extracted_fields


def test_build_review_item_prefers_supplied_results() -> None:
    """Explicit extraction and account-match results should override preview fallbacks."""

    request = create_request(
        extracted_fields=(
            ExtractedField(name="account_number", value="ACC-101", confidence=0.88),
        ),
    )
    decision = ReviewDecision(
        requires_manual_review=True,
        reasons=(ReviewReason.LOW_CONFIDENCE,),
        average_confidence=0.88,
        minimum_confidence=0.88,
        missing_required_fields=(),
    )
    prompt_profile = create_prompt_profile()
    extraction = DocumentAnalysisResult(
        document_type="custom_statement",
        extracted_fields=(
            ExtractedField(name="statement_date", value="2026-04-14", confidence=0.99),
        ),
        model_name="gpt-5.4",
        ocr_confidence=0.99,
        ocr_text="Full OCR text",
        prompt_profile=prompt_profile,
        provider="preview-test",
        summary="Provided by explicit extraction.",
    )
    account_match = AccountMatchResult(
        rationale="Matched by account number.",
        selected_account_id="acct-1001",
        status=AccountMatchStatus.MATCHED,
    )

    review_item = build_review_item(
        request,
        decision,
        prompt_profile,
        extraction_result=extraction,
        account_match=account_match,
    )

    assert review_item.document_type == "custom_statement"
    assert review_item.account_match == account_match
    assert review_item.selected_account_id == "acct-1001"
    assert review_item.extracted_fields == extraction.extracted_fields
    assert review_item.ocr_text_excerpt == "Full OCR text"