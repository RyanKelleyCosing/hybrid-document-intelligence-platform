"""Unit tests for the operator contracts service."""

from __future__ import annotations

import pytest
from pytest import MonkeyPatch

from document_intelligence import operator_contracts
from document_intelligence.models import PacketStatus
from document_intelligence.processing_taxonomy import get_processing_taxonomy
from document_intelligence.settings import AppSettings


def build_settings(**overrides: object) -> AppSettings:
    """Build app settings for operator contract tests."""

    values: dict[str, object] = {
        "sql_connection_string": "Server=tcp:test.database.windows.net;",
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def test_get_repository_raises_when_sql_is_unconfigured(
    monkeypatch: MonkeyPatch,
) -> None:
    """Operator contracts should fail fast when SQL-backed storage is unavailable."""

    class FakeRepository:
        """Repository stub that simulates an unconfigured SQL environment."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return False

    monkeypatch.setattr(
        operator_contracts,
        "SqlOperatorStateRepository",
        FakeRepository,
    )

    with pytest.raises(
        operator_contracts.OperatorContractsConfigurationError,
        match="Azure SQL operator-state contract storage is not configured",
    ):
        operator_contracts._get_repository(build_settings())


def test_get_operator_contracts_returns_sql_and_taxonomy_contracts(
    monkeypatch: MonkeyPatch,
) -> None:
    """The operator contracts service should compose SQL definitions and taxonomy."""

    class FakeRepository:
        """Repository stub that returns empty but valid operator definitions."""

        def list_classification_definitions(self) -> tuple[object, ...]:
            return ()

        def list_document_type_definitions(self) -> tuple[object, ...]:
            return ()

        def list_prompt_profile_versions(self) -> tuple[object, ...]:
            return ()

        def list_prompt_profiles(self) -> tuple[object, ...]:
            return ()

    monkeypatch.setattr(
        operator_contracts,
        "_get_repository",
        lambda settings: FakeRepository(),
    )

    response = operator_contracts.get_operator_contracts(build_settings())

    assert response.classification_definitions == ()
    assert response.document_type_definitions == ()
    assert response.prompt_profile_versions == ()
    assert response.prompt_profiles == ()
    assert response.processing_taxonomy == get_processing_taxonomy()
    assert response.recommendation_contract.required_packet_status == (
        PacketStatus.READY_FOR_RECOMMENDATION
    )
    assert "recommendation_guardrail" in (
        response.recommendation_contract.guardrail_reason_codes
    )
