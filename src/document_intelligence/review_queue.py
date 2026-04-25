"""Decision helpers for the manual review queue."""

from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, datetime
from statistics import fmean

from document_intelligence.models import (
    AccountMatchResult,
    AccountMatchStatus,
    DocumentAnalysisResult,
    DocumentIngestionRequest,
    PromptProfileSelection,
    ReviewDecision,
    ReviewQueueItem,
    ReviewReason,
    ReviewStatus,
)


def should_route_to_manual_review(
    request: DocumentIngestionRequest,
    required_fields: Collection[str],
    low_confidence_threshold: float,
) -> ReviewDecision:
    """Determine whether the document should move into human review."""
    confidences = [field.confidence for field in request.extracted_fields]
    average_confidence = fmean(confidences) if confidences else 0.0
    minimum_confidence = min(confidences, default=0.0)

    normalized_required_fields = {
        field_name.strip().lower()
        for field_name in required_fields
        if field_name.strip()
    }
    present_fields = {field.name.strip().lower() for field in request.extracted_fields}
    missing_required_fields = tuple(sorted(normalized_required_fields - present_fields))

    reasons: list[ReviewReason] = []
    if minimum_confidence < low_confidence_threshold:
        reasons.append(ReviewReason.LOW_CONFIDENCE)
    if missing_required_fields:
        reasons.append(ReviewReason.MISSING_REQUIRED_FIELD)
    if not request.account_candidates:
        reasons.append(ReviewReason.UNMATCHED_ACCOUNT)
    if len(request.account_candidates) > 1:
        reasons.append(ReviewReason.MULTIPLE_ACCOUNT_CANDIDATES)

    return ReviewDecision(
        requires_manual_review=bool(reasons),
        reasons=tuple(reasons),
        average_confidence=average_confidence,
        minimum_confidence=minimum_confidence,
        missing_required_fields=missing_required_fields,
    )


def build_review_item(
    request: DocumentIngestionRequest,
    decision: ReviewDecision,
    prompt_profile: PromptProfileSelection,
    extraction_result: DocumentAnalysisResult | None = None,
    account_match: AccountMatchResult | None = None,
) -> ReviewQueueItem:
    """Serialize a document into the queue contract consumed by the review UI."""
    created_at = datetime.now(UTC)
    effective_extraction = extraction_result or DocumentAnalysisResult(
        document_type=(
            prompt_profile.document_type_hints[0]
            if prompt_profile.document_type_hints
            else "correspondence"
        ),
        extracted_fields=request.extracted_fields,
        model_name="preview",
        ocr_confidence=0.0,
        ocr_text=request.document_text,
        prompt_profile=prompt_profile,
        provider="preview",
        summary=request.source_summary,
    )
    effective_account_match = account_match or AccountMatchResult(
        rationale="Preview mode used request-level account candidates.",
        selected_account_id=(
            request.account_candidates[0]
            if len(request.account_candidates) == 1
            else None
        ),
        status=(
            AccountMatchStatus.MATCHED
            if len(request.account_candidates) == 1
            else AccountMatchStatus.UNMATCHED
            if not request.account_candidates
            else AccountMatchStatus.AMBIGUOUS
        ),
    )
    issuer_category = request.issuer_category
    if issuer_category.value == "unknown":
        issuer_category = prompt_profile.issuer_category

    return ReviewQueueItem(
        status=ReviewStatus.PENDING_REVIEW,
        document_id=request.document_id,
        file_name=request.file_name,
        source=request.source,
        source_uri=request.source_uri,
        issuer_name=request.issuer_name,
        issuer_category=issuer_category,
        document_type=effective_extraction.document_type,
        account_match=effective_account_match,
        selected_account_id=effective_account_match.selected_account_id,
        prompt_profile=prompt_profile,
        received_at_utc=request.received_at_utc,
        created_at_utc=created_at,
        updated_at_utc=created_at,
        ocr_text_excerpt=(
            effective_extraction.ocr_text[:600]
            if effective_extraction.ocr_text
            else None
        ),
        reasons=decision.reasons,
        average_confidence=decision.average_confidence,
        minimum_confidence=decision.minimum_confidence,
        account_candidates=request.account_candidates,
        extracted_fields=effective_extraction.extracted_fields,
    )