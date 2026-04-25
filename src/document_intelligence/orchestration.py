"""Helpers used by the current orchestration scaffold."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from document_intelligence.models import (
    DocumentIngestionRequest,
    ExtractedField,
    ProcessingPreview,
)
from document_intelligence.profiles import select_prompt_profile
from document_intelligence.review_queue import (
    build_review_item,
    should_route_to_manual_review,
)
from document_intelligence.settings import AppSettings


def collapse_extracted_fields(
    fields: Iterable[ExtractedField],
) -> tuple[ExtractedField, ...]:
    """Keep only the highest-confidence value for each logical field name."""
    collapsed_by_name: dict[str, ExtractedField] = {}

    for field in fields:
        normalized_name = field.name.strip().lower()
        candidate = field.model_copy(update={"name": normalized_name})
        current = collapsed_by_name.get(normalized_name)
        if current is None or candidate.confidence > current.confidence:
            collapsed_by_name[normalized_name] = candidate

    return tuple(collapsed_by_name[name] for name in sorted(collapsed_by_name))


def normalize_source_tags(source_tags: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize source tags into stable lowercase values."""
    return tuple(
        sorted(
            {
                tag.strip().lower().replace(" ", "_")
                for tag in source_tags
                if tag.strip()
            }
        )
    )


def normalize_request(request: DocumentIngestionRequest) -> DocumentIngestionRequest:
    """Normalize paths, file names, and extracted fields before routing."""
    normalized_uri = request.source_uri.replace("\\", "/")
    normalized_file_name = request.file_name.replace("\\", "/").rsplit(
        "/",
        maxsplit=1,
    )[-1]
    normalized_tags = normalize_source_tags(request.source_tags)

    return request.model_copy(
        update={
            "source_uri": normalized_uri,
            "issuer_name": request.issuer_name.strip() if request.issuer_name else None,
            "file_name": normalized_file_name,
            "source_summary": (
                request.source_summary.strip() if request.source_summary else None
            ),
            "source_tags": normalized_tags,
            "extracted_fields": collapse_extracted_fields(request.extracted_fields),
        }
    )


def build_processing_preview(
    request: DocumentIngestionRequest,
    settings: AppSettings,
) -> ProcessingPreview:
    """Build the current routing preview for a document request."""
    normalized_request = normalize_request(request)
    prompt_profile = select_prompt_profile(normalized_request)
    decision = should_route_to_manual_review(
        normalized_request,
        settings.required_fields,
        settings.low_confidence_threshold,
    )
    review_item = (
        build_review_item(normalized_request, decision, prompt_profile)
        if decision.requires_manual_review
        else None
    )
    target_status: Literal["pending_review", "ready_for_enrichment"]
    if review_item is None:
        target_status = "ready_for_enrichment"
    else:
        target_status = "pending_review"

    return ProcessingPreview(
        target_status=target_status,
        normalized_request=normalized_request,
        prompt_profile=prompt_profile,
        review_decision=decision,
        review_item=review_item,
    )