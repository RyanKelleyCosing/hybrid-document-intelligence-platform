"""End-to-end workflow helpers for document ingestion."""

from __future__ import annotations

from document_intelligence.account_matching import match_document_to_account
from document_intelligence.extraction import build_match_request, extract_document
from document_intelligence.models import (
    AccountMatchResult,
    DocumentAnalysisResult,
    DocumentIngestionRequest,
    IngestionWorkflowResult,
    IssuerCategory,
    ReviewQueueItem,
    ReviewStatus,
)
from document_intelligence.orchestration import normalize_request
from document_intelligence.review_queue import (
    build_review_item,
    should_route_to_manual_review,
)
from document_intelligence.settings import AppSettings


def enrich_request_with_results(
    request: DocumentIngestionRequest,
    extraction: DocumentAnalysisResult,
    account_match: AccountMatchResult,
) -> DocumentIngestionRequest:
    """Project extraction and matching results back onto the request model."""
    issuer_category = request.issuer_category
    if issuer_category == IssuerCategory.UNKNOWN:
        issuer_category = extraction.prompt_profile.issuer_category

    return build_match_request(
        request.model_copy(
        update={
            "extracted_fields": extraction.extracted_fields,
            "issuer_category": issuer_category,
        }
        ),
        account_match,
    )


def build_account_match_fallback(
    request: DocumentIngestionRequest,
) -> AccountMatchResult:
    """Build a lightweight account match for preview-only scenarios."""
    from document_intelligence.models import AccountMatchStatus

    if not request.account_candidates:
        return AccountMatchResult(
            rationale="No account candidates were provided for the preview.",
            status=AccountMatchStatus.UNMATCHED,
        )

    return AccountMatchResult(
        rationale="Preview mode used request-level account candidates.",
        selected_account_id=(
            request.account_candidates[0]
            if len(request.account_candidates) == 1
            else None
        ),
        status=(
            AccountMatchStatus.MATCHED
            if len(request.account_candidates) == 1
            else AccountMatchStatus.AMBIGUOUS
        ),
    )


def build_analysis_fallback(
    request: DocumentIngestionRequest,
) -> DocumentAnalysisResult:
    """Build a lightweight extraction result for preview-only scenarios."""
    from document_intelligence.profiles import select_prompt_profile

    prompt_profile = select_prompt_profile(request)
    default_document_type = (
        prompt_profile.document_type_hints[0]
        if prompt_profile.document_type_hints
        else "correspondence"
    )
    return DocumentAnalysisResult(
        document_type=default_document_type,
        extracted_fields=request.extracted_fields,
        model_name="preview",
        ocr_confidence=1.0 if request.document_text else 0.0,
        ocr_text=request.document_text,
        prompt_profile=prompt_profile,
        provider="preview",
        summary=request.source_summary,
    )


def process_document_request(
    request: DocumentIngestionRequest,
    settings: AppSettings,
) -> IngestionWorkflowResult:
    """Run extraction, account matching, and review routing for a document."""
    normalized_request = normalize_request(request)
    extraction = extract_document(normalized_request, settings)
    account_match = match_document_to_account(normalized_request, extraction, settings)
    enriched_request = enrich_request_with_results(
        normalized_request,
        extraction,
        account_match,
    )
    review_decision = should_route_to_manual_review(
        enriched_request,
        settings.required_fields,
        settings.low_confidence_threshold,
    )
    review_item: ReviewQueueItem | None = None
    if review_decision.requires_manual_review:
        review_item = build_review_item(
            enriched_request,
            review_decision,
            extraction.prompt_profile,
            extraction_result=extraction,
            account_match=account_match,
        )

    target_status = (
        ReviewStatus.PENDING_REVIEW
        if review_item is not None
        else ReviewStatus.READY_FOR_ENRICHMENT
    )
    return IngestionWorkflowResult(
        account_match=account_match,
        document_id=enriched_request.document_id,
        extraction_result=extraction,
        review_decision=review_decision,
        review_item=review_item,
        target_status=target_status,
    )