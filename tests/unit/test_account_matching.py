"""Unit tests for account matching heuristics."""

from __future__ import annotations

from datetime import UTC, datetime

from document_intelligence.account_matching import build_search_terms, rank_candidates
from document_intelligence.models import (
    DocumentAnalysisResult,
    DocumentIngestionRequest,
    DocumentSource,
    ExtractedField,
    IssuerCategory,
    ProfileSelectionMode,
    PromptProfileId,
    PromptProfileSelection,
)


def create_prompt_profile_selection() -> PromptProfileSelection:
    """Build a stable prompt-profile fixture for unit tests."""
    return PromptProfileSelection(
        issuer_category=IssuerCategory.BANK,
        primary_profile_id=PromptProfileId.BANK_STATEMENT,
        selection_mode=ProfileSelectionMode.EXPLICIT,
        system_prompt="test prompt",
    )


def test_rank_candidates_prefers_exact_account_number() -> None:
    """An exact account-number match should rank first."""
    request = DocumentIngestionRequest(
        document_id="doc-2001",
        source=DocumentSource.AZURE_BLOB,
        source_uri="az://raw-documents/doc-2001.pdf",
        issuer_name="Northwind Credit Union",
        file_name="doc-2001.pdf",
        content_type="application/pdf",
        received_at_utc=datetime(2026, 4, 1, 14, 0, tzinfo=UTC),
    )
    extraction = DocumentAnalysisResult(
        document_type="statement",
        extracted_fields=(
            ExtractedField(name="account_number", value="ACCT-2001", confidence=0.97),
            ExtractedField(name="debtor_name", value="Avery Cole", confidence=0.93),
        ),
        model_name="test-model",
        prompt_profile=create_prompt_profile_selection(),
        provider="test",
    )
    search_terms = build_search_terms(request, extraction)

    ranked = rank_candidates(
        (
            {
                "accountId": "acct-2001",
                "accountNumber": "ACCT-2001",
                "debtorName": "Avery Cole",
                "issuerName": "Northwind Credit Union",
            },
            {
                "accountId": "acct-9000",
                "accountNumber": "ACCT-9000",
                "debtorName": "Avery Collins",
                "issuerName": "Northwind Credit Union",
            },
        ),
        search_terms,
        set(),
    )

    assert ranked[0].account_id == "acct-2001"
    assert ranked[0].score > ranked[1].score


def test_rank_candidates_considers_request_candidate_hints() -> None:
    """Request candidate hints should improve ranking when SQL rows are close."""
    request = DocumentIngestionRequest(
        document_id="doc-2002",
        source=DocumentSource.AZURE_BLOB,
        source_uri="az://raw-documents/doc-2002.pdf",
        issuer_name="Contoso Collections",
        account_candidates=("acct-4002",),
        file_name="doc-2002.pdf",
        content_type="application/pdf",
        received_at_utc=datetime(2026, 4, 1, 14, 5, tzinfo=UTC),
    )
    extraction = DocumentAnalysisResult(
        document_type="collection notice",
        extracted_fields=(
            ExtractedField(name="debtor_name", value="Jordan Patel", confidence=0.91),
        ),
        model_name="test-model",
        prompt_profile=create_prompt_profile_selection(),
        provider="test",
    )
    search_terms = build_search_terms(request, extraction)

    ranked = rank_candidates(
        (
            {
                "accountId": "acct-4001",
                "accountNumber": "ACCT-4001",
                "debtorName": "Jordan Patel",
                "issuerName": "Contoso Collections",
            },
            {
                "accountId": "acct-4002",
                "accountNumber": "ACCT-4002",
                "debtorName": "Jordan Patel",
                "issuerName": "Contoso Collections",
            },
        ),
        search_terms,
        set(request.account_candidates),
    )

    assert ranked[0].account_id == "acct-4002"