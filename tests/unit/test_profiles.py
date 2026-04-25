"""Unit tests for issuer-aware prompt profile selection."""

from __future__ import annotations

from datetime import UTC, datetime

from document_intelligence.models import (
    DocumentIngestionRequest,
    DocumentSource,
    ExtractedField,
    PromptProfileId,
)
from document_intelligence.profiles import select_prompt_profile


def test_select_prompt_profile_prefers_court_profile_from_heuristics() -> None:
    """Court signals should select the court-filing profile heuristically."""
    request = DocumentIngestionRequest(
        document_id="doc-court-1",
        source=DocumentSource.AWS_S3,
        source_uri="s3://hybrid-demo/incoming/court/judgment-notice.pdf",
        issuer_name="Superior Court of Maricopa County",
        file_name="judgment-notice.pdf",
        content_type="application/pdf",
        received_at_utc=datetime(2026, 4, 1, 12, 30, tzinfo=UTC),
        source_tags=("court", "judgment"),
        extracted_fields=(
            ExtractedField(name="case_number", value="CV2026-1042", confidence=0.93),
            ExtractedField(name="judgment_amount", value="$3,850.00", confidence=0.91),
        ),
    )

    selection = select_prompt_profile(request)

    assert selection.primary_profile_id == PromptProfileId.COURT_FILING
    assert selection.selection_mode == "heuristic"
    assert selection.candidate_profiles[0].score > 0


def test_select_prompt_profile_falls_back_to_generic_profile() -> None:
    """Unknown mixed-source documents should use the generic profile."""
    request = DocumentIngestionRequest(
        document_id="doc-generic-1",
        source=DocumentSource.SCANNED_UPLOAD,
        source_uri="scan://box-14/page-0008",
        file_name="page-0008.png",
        content_type="image/png",
        received_at_utc=datetime(2026, 4, 1, 13, 0, tzinfo=UTC),
        extracted_fields=(
            ExtractedField(name="debtor_name", value="Taylor Reed", confidence=0.88),
        ),
    )

    selection = select_prompt_profile(request)

    assert selection.primary_profile_id == PromptProfileId.GENERIC_CORRESPONDENCE
    assert selection.selection_mode == "fallback"