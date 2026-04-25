"""Unit tests for workflow fallbacks and status shaping."""

from __future__ import annotations

from datetime import UTC, datetime

from pytest import MonkeyPatch

from document_intelligence import workflow
from document_intelligence.models import (
    AccountMatchCandidate,
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
    ReviewQueueItem,
    ReviewReason,
    ReviewStatus,
)
from document_intelligence.settings import AppSettings


def build_settings(**overrides: object) -> AppSettings:
    """Build app settings for workflow tests."""

    values: dict[str, object] = {}
    values.update(overrides)
    return AppSettings.model_validate(values)


def create_prompt_profile() -> PromptProfileSelection:
    """Build a representative prompt profile for workflow tests."""

    return PromptProfileSelection(
        document_type_hints=("bank_statement",),
        issuer_category=IssuerCategory.BANK,
        primary_profile_id=PromptProfileId.BANK_STATEMENT,
        selection_mode=ProfileSelectionMode.HEURISTIC,
        system_prompt="Extract bank statement data.",
    )


def create_request(
    *,
    account_candidates: tuple[str, ...] = ("acct-1001",),
    document_text: str | None = "OCR text",
    extracted_fields: tuple[ExtractedField, ...] = (),
    issuer_category: IssuerCategory = IssuerCategory.UNKNOWN,
) -> DocumentIngestionRequest:
    """Build a representative request for workflow tests."""

    return DocumentIngestionRequest(
        document_id="doc-4001",
        source=DocumentSource.AZURE_SFTP,
        source_uri="sftp://landing/case-4001\\statement.pdf",
        issuer_category=issuer_category,
        issuer_name="Northwind",
        file_name="landing\\statement.pdf",
        content_type="application/pdf",
        received_at_utc=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        extracted_fields=extracted_fields,
        account_candidates=account_candidates,
        document_text=document_text,
        source_summary="demo summary",
    )


def create_review_item(
    request: DocumentIngestionRequest,
    prompt_profile: PromptProfileSelection,
) -> ReviewQueueItem:
    """Build a minimal review queue item for workflow tests."""

    return ReviewQueueItem(
        document_id=request.document_id,
        file_name=request.file_name,
        source=request.source,
        source_uri=request.source_uri,
        issuer_name=request.issuer_name,
        issuer_category=IssuerCategory.BANK,
        document_type="bank_statement",
        prompt_profile=prompt_profile,
        received_at_utc=request.received_at_utc,
        average_confidence=0.71,
        minimum_confidence=0.71,
    )


def test_build_account_match_fallback_returns_unmatched_without_candidates() -> None:
    """Preview fallback matching should stay unmatched when the request has none."""

    fallback = workflow.build_account_match_fallback(create_request(account_candidates=()))

    assert fallback.status == AccountMatchStatus.UNMATCHED
    assert fallback.selected_account_id is None
    assert fallback.rationale == "No account candidates were provided for the preview."


def test_build_account_match_fallback_marks_multiple_candidates_ambiguous() -> None:
    """Preview fallback matching should flag ambiguous candidate lists."""

    fallback = workflow.build_account_match_fallback(
        create_request(account_candidates=("acct-1001", "acct-2002"))
    )

    assert fallback.status == AccountMatchStatus.AMBIGUOUS
    assert fallback.selected_account_id is None


def test_build_analysis_fallback_preserves_request_context() -> None:
    """Preview fallback extraction should reuse the request payload and profile hints."""

    request = create_request(
        extracted_fields=(
            ExtractedField(name="account_number", value="ACC-101", confidence=0.95),
        )
    )

    fallback = workflow.build_analysis_fallback(request)

    assert fallback.document_type == fallback.prompt_profile.document_type_hints[0]
    assert fallback.extracted_fields == request.extracted_fields
    assert fallback.model_name == "preview"
    assert fallback.provider == "preview"
    assert fallback.ocr_confidence == 1.0
    assert fallback.ocr_text == "OCR text"
    assert fallback.summary == "demo summary"


def test_process_document_request_returns_pending_review_when_review_is_required(
    monkeypatch: MonkeyPatch,
) -> None:
    """Workflow results should stay in pending review when review routing fires."""

    prompt_profile = create_prompt_profile()
    extraction = DocumentAnalysisResult(
        document_type="bank_statement",
        extracted_fields=(
            ExtractedField(name="account_number", value="ACC-101", confidence=0.71),
        ),
        model_name="gpt-5.4",
        ocr_confidence=0.9,
        ocr_text="Extracted OCR text",
        prompt_profile=prompt_profile,
        provider="preview-test",
        summary="Extracted summary",
    )
    account_match = AccountMatchResult(
        candidates=(
            AccountMatchCandidate(
                account_id="acct-1001",
                account_number="ACC-101",
                score=97,
            ),
        ),
        rationale="Matched by account number.",
        selected_account_id="acct-1001",
        status=AccountMatchStatus.MATCHED,
    )
    decision = ReviewDecision(
        requires_manual_review=True,
        reasons=(ReviewReason.LOW_CONFIDENCE,),
        average_confidence=0.71,
        minimum_confidence=0.71,
        missing_required_fields=(),
    )
    request = create_request(
        account_candidates=(),
        extracted_fields=(
            ExtractedField(name="account_number", value="ACC-101", confidence=0.71),
        ),
    )
    captured: dict[str, object] = {}

    def fake_extract_document(
        normalized_request: DocumentIngestionRequest,
        settings: AppSettings,
    ) -> DocumentAnalysisResult:
        del settings
        captured["extract_request"] = normalized_request
        return extraction

    def fake_match_document_to_account(
        normalized_request: DocumentIngestionRequest,
        extraction_result: DocumentAnalysisResult,
        settings: AppSettings,
    ) -> AccountMatchResult:
        del settings
        captured["match_request"] = normalized_request
        captured["match_extraction"] = extraction_result
        return account_match

    def fake_should_route_to_manual_review(
        enriched_request: DocumentIngestionRequest,
        required_fields: tuple[str, ...],
        low_confidence_threshold: float,
    ) -> ReviewDecision:
        captured["route_request"] = enriched_request
        captured["required_fields"] = required_fields
        captured["low_confidence_threshold"] = low_confidence_threshold
        return decision

    def fake_build_review_item(
        enriched_request: DocumentIngestionRequest,
        review_decision: ReviewDecision,
        selected_prompt_profile: PromptProfileSelection,
        extraction_result: DocumentAnalysisResult | None = None,
        account_match: AccountMatchResult | None = None,
    ) -> ReviewQueueItem:
        assert review_decision == decision
        assert selected_prompt_profile == prompt_profile
        assert extraction_result == extraction
        assert account_match == account_match_result
        return create_review_item(enriched_request, selected_prompt_profile)

    account_match_result = account_match
    monkeypatch.setattr(workflow, "extract_document", fake_extract_document)
    monkeypatch.setattr(workflow, "match_document_to_account", fake_match_document_to_account)
    monkeypatch.setattr(workflow, "should_route_to_manual_review", fake_should_route_to_manual_review)
    monkeypatch.setattr(workflow, "build_review_item", fake_build_review_item)

    result = workflow.process_document_request(request, build_settings())

    extract_request = captured["extract_request"]
    assert isinstance(extract_request, DocumentIngestionRequest)
    assert extract_request.file_name == "statement.pdf"
    assert extract_request.source_uri == "sftp://landing/case-4001/statement.pdf"
    route_request = captured["route_request"]
    assert isinstance(route_request, DocumentIngestionRequest)
    assert route_request.account_candidates == ("acct-1001",)
    assert result.target_status == ReviewStatus.PENDING_REVIEW
    assert result.review_item is not None
    assert result.account_match == account_match
    assert result.extraction_result == extraction


def test_process_document_request_returns_ready_for_enrichment_without_review(
    monkeypatch: MonkeyPatch,
) -> None:
    """Workflow results should skip queue item creation when review is unnecessary."""

    prompt_profile = create_prompt_profile()
    extraction = DocumentAnalysisResult(
        document_type="bank_statement",
        extracted_fields=(
            ExtractedField(name="account_number", value="ACC-101", confidence=0.99),
        ),
        model_name="gpt-5.4",
        ocr_confidence=0.99,
        ocr_text="Extracted OCR text",
        prompt_profile=prompt_profile,
        provider="preview-test",
        summary="Extracted summary",
    )
    account_match = AccountMatchResult(
        candidates=(
            AccountMatchCandidate(
                account_id="acct-1001",
                account_number="ACC-101",
                score=99,
            ),
        ),
        rationale="Matched by account number.",
        selected_account_id="acct-1001",
        status=AccountMatchStatus.MATCHED,
    )
    decision = ReviewDecision(
        requires_manual_review=False,
        reasons=(),
        average_confidence=0.99,
        minimum_confidence=0.99,
        missing_required_fields=(),
    )
    request = create_request(
        extracted_fields=(
            ExtractedField(name="account_number", value="ACC-101", confidence=0.99),
        )
    )

    monkeypatch.setattr(workflow, "extract_document", lambda normalized_request, settings: extraction)
    monkeypatch.setattr(
        workflow,
        "match_document_to_account",
        lambda normalized_request, extraction_result, settings: account_match,
    )
    monkeypatch.setattr(
        workflow,
        "should_route_to_manual_review",
        lambda enriched_request, required_fields, low_confidence_threshold: decision,
    )
    monkeypatch.setattr(
        workflow,
        "build_review_item",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError((args, kwargs))),
    )

    result = workflow.process_document_request(request, build_settings())

    assert result.target_status == ReviewStatus.READY_FOR_ENRICHMENT
    assert result.review_item is None
    assert result.account_match == account_match
    assert result.extraction_result == extraction