"""Shared models and helpers for the document intelligence platform."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from document_intelligence.settings import AppSettings, get_settings

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "match_document_to_account": (
        "document_intelligence.account_matching",
        "match_document_to_account",
    ),
    "extract_document": ("document_intelligence.extraction", "extract_document"),
    "AccountMatchCandidate": (
        "document_intelligence.models",
        "AccountMatchCandidate",
    ),
    "AccountMatchResult": ("document_intelligence.models", "AccountMatchResult"),
    "AccountMatchStatus": ("document_intelligence.models", "AccountMatchStatus"),
    "DocumentAnalysisResult": (
        "document_intelligence.models",
        "DocumentAnalysisResult",
    ),
    "DocumentIngestionRequest": (
        "document_intelligence.models",
        "DocumentIngestionRequest",
    ),
    "DocumentSource": ("document_intelligence.models", "DocumentSource"),
    "ExtractedField": ("document_intelligence.models", "ExtractedField"),
    "IngestionWorkflowResult": (
        "document_intelligence.models",
        "IngestionWorkflowResult",
    ),
    "IssuerCategory": ("document_intelligence.models", "IssuerCategory"),
    "ProcessingPreview": ("document_intelligence.models", "ProcessingPreview"),
    "ProfileSelectionMode": (
        "document_intelligence.models",
        "ProfileSelectionMode",
    ),
    "PromptProfileCandidate": (
        "document_intelligence.models",
        "PromptProfileCandidate",
    ),
    "PromptProfileId": ("document_intelligence.models", "PromptProfileId"),
    "PromptProfileSelection": (
        "document_intelligence.models",
        "PromptProfileSelection",
    ),
    "ReviewDecision": ("document_intelligence.models", "ReviewDecision"),
    "ReviewDecisionUpdate": (
        "document_intelligence.models",
        "ReviewDecisionUpdate",
    ),
    "ReviewItemListResponse": (
        "document_intelligence.models",
        "ReviewItemListResponse",
    ),
    "ReviewQueueItem": ("document_intelligence.models", "ReviewQueueItem"),
    "ReviewReason": ("document_intelligence.models", "ReviewReason"),
    "ReviewStatus": ("document_intelligence.models", "ReviewStatus"),
    "CosmosReviewRepository": (
        "document_intelligence.persistence",
        "CosmosReviewRepository",
    ),
    "ServiceBusReviewQueuePublisher": (
        "document_intelligence.persistence",
        "ServiceBusReviewQueuePublisher",
    ),
    "select_prompt_profile": (
        "document_intelligence.profiles",
        "select_prompt_profile",
    ),
    "process_document_request": (
        "document_intelligence.workflow",
        "process_document_request",
    ),
}

__all__ = [
    "AppSettings",
    "AccountMatchCandidate",
    "AccountMatchResult",
    "AccountMatchStatus",
    "DocumentIngestionRequest",
    "DocumentAnalysisResult",
    "DocumentSource",
    "ExtractedField",
    "IngestionWorkflowResult",
    "IssuerCategory",
    "ProcessingPreview",
    "ProfileSelectionMode",
    "PromptProfileCandidate",
    "PromptProfileId",
    "PromptProfileSelection",
    "ReviewDecision",
    "ReviewDecisionUpdate",
    "ReviewItemListResponse",
    "ReviewQueueItem",
    "ReviewReason",
    "ReviewStatus",
    "CosmosReviewRepository",
    "ServiceBusReviewQueuePublisher",
    "extract_document",
    "get_settings",
    "match_document_to_account",
    "process_document_request",
    "select_prompt_profile",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve package exports when callers access them from the root."""
    if name in globals():
        return globals()[name]

    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return the package exports for interactive discovery."""
    return sorted(__all__)