"""Unit tests for packet recommendation review actions."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import TracebackType

from pytest import MonkeyPatch

from document_intelligence import packet_recommendation_review
from document_intelligence.models import (
    DocumentSource,
    PacketRecommendationReviewRequest,
    PacketRecord,
    PacketStatus,
    PacketWorkspaceSnapshot,
    RecommendationDisposition,
    RecommendationResultRecord,
)
from document_intelligence.settings import AppSettings


def build_settings(**overrides: object) -> AppSettings:
    """Build app settings for recommendation review tests."""

    values: dict[str, object] = {
        "sql_connection_string": "Server=tcp:test.database.windows.net;",
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


class FakeCursor:
    """Minimal DB-API cursor stub for recommendation review tests."""

    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback

    def execute(
        self,
        statement: str,
        params: tuple[object, ...] | None = None,
    ) -> None:
        normalized_statement = " ".join(statement.split())
        self._connection.executed_statements.append((normalized_statement, params))


class FakeConnection:
    """Minimal DB-API connection stub for recommendation review tests."""

    def __init__(self) -> None:
        self.executed_statements: list[tuple[str, tuple[object, ...] | None]] = []
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_review_packet_recommendation_persists_disposition_and_audit(
    monkeypatch: MonkeyPatch,
) -> None:
    """Reviewing a recommendation should update the result and append audit rows."""

    recommendation_result = RecommendationResultRecord(
        recommendation_result_id="recres_001",
        recommendation_run_id="recrun_001",
        packet_id="pkt_demo_001",
        document_id="doc_demo_001",
        recommendation_kind="settlement_offer",
        summary="Offer a reduced payment plan.",
        rationale_payload={"basis": "income verified"},
        evidence_items=(),
        confidence=0.91,
        advisory_text="Recommend settlement outreach.",
        disposition=RecommendationDisposition.PENDING,
        reviewed_by_user_id=None,
        reviewed_by_email=None,
        reviewed_at_utc=None,
        created_at_utc=datetime(2026, 4, 14, 9, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 4, 14, 9, 0, tzinfo=UTC),
    )
    snapshot = PacketWorkspaceSnapshot(
        packet=PacketRecord(
            packet_id="pkt_demo_001",
            packet_name="demo packet",
            source=DocumentSource.SCANNED_UPLOAD,
            status=PacketStatus.COMPLETED,
            received_at_utc=datetime(2026, 4, 14, 8, 45, tzinfo=UTC),
            created_at_utc=datetime(2026, 4, 14, 8, 45, tzinfo=UTC),
            updated_at_utc=datetime(2026, 4, 14, 9, 0, tzinfo=UTC),
        ),
        recommendation_results=(recommendation_result,),
    )
    connection = FakeConnection()

    class FakeRepository:
        """Repository stub that returns one packet workspace snapshot."""

        def __init__(self, settings: object) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(self, packet_id: str) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_demo_001"
            return snapshot

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_recommendation_review,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_recommendation_review,
        "open_sql_connection",
        fake_open_sql_connection,
    )

    response = packet_recommendation_review.review_packet_recommendation(
        "pkt_demo_001",
        "recres_001",
        PacketRecommendationReviewRequest(
            disposition=RecommendationDisposition.ACCEPTED,
            reviewed_by_email="reviewer@example.com",
        ),
        build_settings(),
    )

    assert response.packet_id == "pkt_demo_001"
    assert response.recommendation_result.disposition == RecommendationDisposition.ACCEPTED
    assert response.recommendation_result.reviewed_by_email == "reviewer@example.com"
    assert response.recommendation_result.reviewed_at_utc is not None
    assert connection.committed is True
    assert any(
        "UPDATE dbo.RecommendationResults" in statement
        for statement, _ in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.PacketEvents" in statement
        for statement, _ in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.AuditEvents" in statement
        for statement, _ in connection.executed_statements
    )
    audit_insert = next(
        params
        for statement, params in connection.executed_statements
        if "INSERT INTO dbo.AuditEvents" in statement
    )
    assert audit_insert is not None
    audit_payload = json.loads(str(audit_insert[6]))
    assert audit_payload["contentControls"]["retentionClass"] == (
        "recommendation_history"
    )
    assert audit_payload["contentControls"]["containsSensitiveContent"] is False
    assert audit_payload["contentControls"]["maskedFields"] == []
