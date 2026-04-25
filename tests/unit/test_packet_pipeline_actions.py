"""Unit tests for packet pipeline retry actions."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import TracebackType

from pytest import MonkeyPatch

from document_intelligence import packet_pipeline_actions
from document_intelligence.models import (
    DocumentSource,
    PacketExtractionExecutionResponse,
    PacketDocumentRecord,
    PacketOcrExecutionResponse,
    PacketRecord,
    PacketStatus,
    PacketWorkspaceSnapshot,
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStageName,
)
from document_intelligence.settings import AppSettings


def build_settings(**overrides: object) -> AppSettings:
    """Build app settings for pipeline retry tests."""

    values: dict[str, object] = {
        "sql_connection_string": "Server=tcp:test.database.windows.net;",
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


class FakePipelineCursor:
    """Minimal DB-API cursor stub for packet pipeline retry tests."""

    def __init__(self, connection: FakePipelineConnection) -> None:
        self._connection = connection

    def __enter__(self) -> FakePipelineCursor:
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


class FakePipelineConnection:
    """Minimal DB-API connection stub for packet pipeline retry tests."""

    def __init__(self) -> None:
        self.executed_statements: list[tuple[str, tuple[object, ...] | None]] = []
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> FakePipelineCursor:
        return FakePipelineCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_retry_packet_stage_requeues_failed_work(
    monkeypatch: MonkeyPatch,
) -> None:
    """Retrying a failed packet stage should queue a fresh attempt and execute it."""

    snapshot = PacketWorkspaceSnapshot(
        packet=PacketRecord(
            packet_id="pkt_demo_001",
            packet_name="demo packet",
            source=DocumentSource.SCANNED_UPLOAD,
            status=PacketStatus.FAILED,
            received_at_utc=datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
            created_at_utc=datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
            updated_at_utc=datetime(2026, 4, 12, 12, 10, tzinfo=UTC),
        ),
        documents=(
            PacketDocumentRecord(
                document_id="doc_demo_001",
                packet_id="pkt_demo_001",
                file_name="statement.pdf",
                content_type="application/pdf",
                source=DocumentSource.SCANNED_UPLOAD,
                status=PacketStatus.FAILED,
                received_at_utc=datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
                created_at_utc=datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
                updated_at_utc=datetime(2026, 4, 12, 12, 10, tzinfo=UTC),
            ),
        ),
        processing_jobs=(
            ProcessingJobRecord(
                attempt_number=1,
                completed_at_utc=datetime(2026, 4, 12, 12, 9, tzinfo=UTC),
                created_at_utc=datetime(2026, 4, 12, 12, 1, tzinfo=UTC),
                document_id="doc_demo_001",
                error_code="extract_failed",
                error_message="Downstream extraction failed.",
                job_id="job_ext_failed_001",
                packet_id="pkt_demo_001",
                queued_at_utc=datetime(2026, 4, 12, 12, 1, tzinfo=UTC),
                stage_name=ProcessingStageName.EXTRACTION,
                started_at_utc=datetime(2026, 4, 12, 12, 2, tzinfo=UTC),
                status=ProcessingJobStatus.FAILED,
                updated_at_utc=datetime(2026, 4, 12, 12, 9, tzinfo=UTC),
            ),
        ),
    )
    connection = FakePipelineConnection()

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
    ) -> Iterator[FakePipelineConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_pipeline_actions,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_pipeline_actions,
        "open_sql_connection",
        fake_open_sql_connection,
    )
    monkeypatch.setattr(
        packet_pipeline_actions,
        "_execute_stage",
        lambda packet_id, stage_name, settings: PacketExtractionExecutionResponse(
            executed_document_count=1,
            next_stage=ProcessingStageName.RECOMMENDATION,
            packet_id=packet_id,
            processed_documents=(),
            skipped_document_ids=(),
            status=PacketStatus.READY_FOR_RECOMMENDATION,
        ),
    )

    response = packet_pipeline_actions.retry_packet_stage(
        "pkt_demo_001",
        "extraction",
        build_settings(),
    )

    assert response.packet_id == "pkt_demo_001"
    assert response.stage_name == ProcessingStageName.EXTRACTION
    assert response.requeued_document_count == 1
    assert response.failed_job_count == 1
    assert response.executed_document_count == 1
    assert response.next_stage == ProcessingStageName.RECOMMENDATION
    assert response.status == PacketStatus.READY_FOR_RECOMMENDATION
    assert connection.committed is True
    assert any(
        "INSERT INTO dbo.ProcessingJobs" in statement
        for statement, _ in connection.executed_statements
    )
    assert any(
        "UPDATE dbo.PacketDocuments" in statement
        for statement, _ in connection.executed_statements
    )
    assert any(
        "UPDATE dbo.Packets" in statement
        for statement, _ in connection.executed_statements
    )


def test_retry_packet_stage_propagates_ocr_review_pause(
    monkeypatch: MonkeyPatch,
) -> None:
    """Retrying OCR should preserve a review-required handoff when OCR pauses."""

    snapshot = PacketWorkspaceSnapshot(
        packet=PacketRecord(
            packet_id="pkt_demo_ocr_001",
            packet_name="ocr retry packet",
            source=DocumentSource.SCANNED_UPLOAD,
            status=PacketStatus.FAILED,
            received_at_utc=datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
            created_at_utc=datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
            updated_at_utc=datetime(2026, 4, 12, 12, 10, tzinfo=UTC),
        ),
        documents=(
            PacketDocumentRecord(
                document_id="doc_demo_ocr_001",
                packet_id="pkt_demo_ocr_001",
                file_name="scan.pdf",
                content_type="application/pdf",
                source=DocumentSource.SCANNED_UPLOAD,
                status=PacketStatus.FAILED,
                received_at_utc=datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
                created_at_utc=datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
                updated_at_utc=datetime(2026, 4, 12, 12, 10, tzinfo=UTC),
            ),
        ),
        processing_jobs=(
            ProcessingJobRecord(
                attempt_number=1,
                completed_at_utc=datetime(2026, 4, 12, 12, 9, tzinfo=UTC),
                created_at_utc=datetime(2026, 4, 12, 12, 1, tzinfo=UTC),
                document_id="doc_demo_ocr_001",
                error_code="ocr_failed",
                error_message="OCR failed on the prior attempt.",
                job_id="job_ocr_failed_001",
                packet_id="pkt_demo_ocr_001",
                queued_at_utc=datetime(2026, 4, 12, 12, 1, tzinfo=UTC),
                stage_name=ProcessingStageName.OCR,
                started_at_utc=datetime(2026, 4, 12, 12, 2, tzinfo=UTC),
                status=ProcessingJobStatus.FAILED,
                updated_at_utc=datetime(2026, 4, 12, 12, 9, tzinfo=UTC),
            ),
        ),
    )
    connection = FakePipelineConnection()

    class FakeRepository:
        """Repository stub that returns one OCR packet snapshot."""

        def __init__(self, settings: object) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(self, packet_id: str) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_demo_ocr_001"
            return snapshot

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakePipelineConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_pipeline_actions,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_pipeline_actions,
        "open_sql_connection",
        fake_open_sql_connection,
    )
    monkeypatch.setattr(
        packet_pipeline_actions,
        "_execute_stage",
        lambda packet_id, stage_name, settings: PacketOcrExecutionResponse(
            executed_document_count=1,
            next_stage=ProcessingStageName.REVIEW,
            packet_id=packet_id,
            processed_documents=(),
            skipped_document_ids=(),
            status=PacketStatus.AWAITING_REVIEW,
        ),
    )

    response = packet_pipeline_actions.retry_packet_stage(
        "pkt_demo_ocr_001",
        "ocr",
        build_settings(),
    )

    assert response.packet_id == "pkt_demo_ocr_001"
    assert response.stage_name == ProcessingStageName.OCR
    assert response.requeued_document_count == 1
    assert response.executed_document_count == 1
    assert response.next_stage == ProcessingStageName.REVIEW
    assert response.status == PacketStatus.AWAITING_REVIEW