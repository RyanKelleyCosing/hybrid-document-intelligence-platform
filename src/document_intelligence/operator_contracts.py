"""Services for the remaining Epic 1 operator-state contracts."""

from __future__ import annotations

from document_intelligence.models import (
    OperatorContractsResponse,
    RecommendationContractDefinition,
)
from document_intelligence.operator_state import SqlOperatorStateRepository
from document_intelligence.processing_taxonomy import get_processing_taxonomy
from document_intelligence.settings import AppSettings


class OperatorContractsConfigurationError(RuntimeError):
    """Raised when SQL-backed operator contracts are not configured."""


def _get_repository(settings: AppSettings) -> SqlOperatorStateRepository:
    """Return the configured SQL operator-state repository."""

    repository = SqlOperatorStateRepository(settings)
    if repository.is_configured():
        return repository

    raise OperatorContractsConfigurationError(
        "Azure SQL operator-state contract storage is not configured."
    )


def build_recommendation_contract() -> RecommendationContractDefinition:
    """Return the canonical recommendation contract for operator workflows."""

    return RecommendationContractDefinition()


def get_operator_contracts(settings: AppSettings) -> OperatorContractsResponse:
    """Return the managed operator contracts needed by later UI surfaces."""

    repository = _get_repository(settings)
    return OperatorContractsResponse(
        classification_definitions=repository.list_classification_definitions(),
        document_type_definitions=repository.list_document_type_definitions(),
        processing_taxonomy=get_processing_taxonomy(),
        prompt_profile_versions=repository.list_prompt_profile_versions(),
        prompt_profiles=repository.list_prompt_profiles(),
        recommendation_contract=build_recommendation_contract(),
    )