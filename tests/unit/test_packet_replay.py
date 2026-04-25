"""Unit tests for packet replay actions."""

from __future__ import annotations

from datetime import UTC, datetime

from pytest import MonkeyPatch, raises

from document_intelligence import packet_replay
from document_intelligence.models import (
    DocumentSource,
    PacketClassificationExecutionResponse,
    PacketDocumentRecord,
    PacketOcrExecutionResponse,
    PacketRecord,
    PacketStageRetryResponse,
    PacketStatus,
    PacketWorkspaceSnapshot,
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStageName,
)
from document_intelligence.settings import AppSettings


def build_settings(**overrides: object) -> AppSettings:
    """Build app settings for packet replay tests."""

    values: dict[str, object] = {
        "sql_connection_string": "Server=tcp:test.database.windows.net;",
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def test_replay_packet_retries_failed_stage(monkeypatch: MonkeyPatch) -> None:
    """Replay should prefer the latest failed packet stage before fresh execution."""

    snapshot = PacketWorkspaceSnapshot(
        packet=PacketRecord(
            packet_id="pkt_demo_001",
            packet_name="demo packet",
            source=DocumentSource.SCANNED_UPLOAD,
            status=PacketStatus.FAILED,
            received_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
            created_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
            updated_at_utc=datetime(2026, 4, 15, 10, 10, tzinfo=UTC),
        ),
        documents=(
            PacketDocumentRecord(
                document_id="doc_demo_001",
                packet_id="pkt_demo_001",
                file_name="statement.pdf",
                content_type="application/pdf",
                source=DocumentSource.SCANNED_UPLOAD,
                status=PacketStatus.EXTRACTING,
                received_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
                created_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
                updated_at_utc=datetime(2026, 4, 15, 10, 10, tzinfo=UTC),
            ),
        ),
        processing_jobs=(
            ProcessingJobRecord(
                attempt_number=1,
                completed_at_utc=datetime(2026, 4, 15, 10, 9, tzinfo=UTC),
                created_at_utc=datetime(2026, 4, 15, 10, 1, tzinfo=UTC),
                document_id="doc_demo_001",
                error_code="extract_failed",
                error_message="Downstream extraction failed.",
                job_id="job_ext_failed_001",
                packet_id="pkt_demo_001",
                queued_at_utc=datetime(2026, 4, 15, 10, 1, tzinfo=UTC),
                stage_name=ProcessingStageName.EXTRACTION,
                started_at_utc=datetime(2026, 4, 15, 10, 2, tzinfo=UTC),
                status=ProcessingJobStatus.FAILED,
                updated_at_utc=datetime(2026, 4, 15, 10, 9, tzinfo=UTC),
            ),
        ),
    )

    class FakeRepository:
        """Repository stub that returns one packet snapshot."""

        def __init__(self, settings: object) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(self, packet_id: str) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_demo_001"
            return snapshot

    monkeypatch.setattr(packet_replay, "SqlOperatorStateRepository", FakeRepository)
    monkeypatch.setattr(
        packet_replay,
        "retry_packet_stage",
        lambda packet_id, stage_name, settings, stale_after_minutes=30: PacketStageRetryResponse(
            executed_document_count=1,
            failed_job_count=1,
            next_stage=ProcessingStageName.RECOMMENDATION,
            packet_id=packet_id,
            requeued_document_count=1,
            skipped_document_ids=(),
            stage_name=ProcessingStageName(stage_name),
            stale_running_job_count=0,
            status=PacketStatus.READY_FOR_RECOMMENDATION,
        ),
    )

    response = packet_replay.replay_packet("pkt_demo_001", build_settings())

    assert response.action == "retry"
    assert response.stage_name == ProcessingStageName.EXTRACTION
    assert response.requeued_document_count == 1
    assert response.failed_job_count == 1


def test_replay_packet_executes_received_packet(monkeypatch: MonkeyPatch) -> None:
    """Replay should execute classification for a newly received packet."""

    snapshot = PacketWorkspaceSnapshot(
        packet=PacketRecord(
            packet_id="pkt_demo_001",
            packet_name="demo packet",
            source=DocumentSource.SCANNED_UPLOAD,
            status=PacketStatus.RECEIVED,
            received_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
            created_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
            updated_at_utc=datetime(2026, 4, 15, 10, 1, tzinfo=UTC),
        ),
        documents=(
            PacketDocumentRecord(
                document_id="doc_demo_001",
                packet_id="pkt_demo_001",
                file_name="statement.pdf",
                content_type="application/pdf",
                source=DocumentSource.SCANNED_UPLOAD,
                status=PacketStatus.RECEIVED,
                received_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
                created_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
                updated_at_utc=datetime(2026, 4, 15, 10, 1, tzinfo=UTC),
            ),
        ),
    )

    class FakeRepository:
        """Repository stub that returns one packet snapshot."""

        def __init__(self, settings: object) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(self, packet_id: str) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_demo_001"
            return snapshot

    monkeypatch.setattr(packet_replay, "SqlOperatorStateRepository", FakeRepository)
    monkeypatch.setattr(
        packet_replay,
        "_execute_stage",
        lambda packet_id, stage_name, settings: PacketClassificationExecutionResponse(
            executed_document_count=1,
            next_stage=ProcessingStageName.OCR,
            packet_id=packet_id,
            processed_documents=(),
            skipped_document_ids=(),
            status=PacketStatus.OCR_RUNNING,
        ),
    )

    response = packet_replay.replay_packet("pkt_demo_001", build_settings())

    assert response.action == "execute"
    assert response.stage_name == ProcessingStageName.CLASSIFICATION
    assert response.executed_document_count == 1
    assert response.status == PacketStatus.OCR_RUNNING


def test_replay_packet_rejects_quarantined_packets(monkeypatch: MonkeyPatch) -> None:
    """Quarantined packets should not be replayed from intake."""

    snapshot = PacketWorkspaceSnapshot(
        packet=PacketRecord(
            packet_id="pkt_demo_001",
            packet_name="demo packet",
            source=DocumentSource.SCANNED_UPLOAD,
            status=PacketStatus.QUARANTINED,
            received_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
            created_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
            updated_at_utc=datetime(2026, 4, 15, 10, 1, tzinfo=UTC),
        ),
    )

    class FakeRepository:
        def __init__(self, settings: object) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(self, packet_id: str) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_demo_001"
            return snapshot

    monkeypatch.setattr(packet_replay, "SqlOperatorStateRepository", FakeRepository)

    with raises(ValueError, match="Quarantined packets"):
        packet_replay.replay_packet("pkt_demo_001", build_settings())


def test_replay_packet_propagates_ocr_review_pause(monkeypatch: MonkeyPatch) -> None:
    """Replay should preserve review-routing when OCR pauses on quality warnings."""

    snapshot = PacketWorkspaceSnapshot(
        packet=PacketRecord(
            packet_id="pkt_demo_ocr_001",
            packet_name="ocr packet",
            source=DocumentSource.SCANNED_UPLOAD,
            status=PacketStatus.OCR_RUNNING,
            received_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
            created_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
            updated_at_utc=datetime(2026, 4, 15, 10, 1, tzinfo=UTC),
        ),
        documents=(
            PacketDocumentRecord(
                document_id="doc_demo_ocr_001",
                packet_id="pkt_demo_ocr_001",
                file_name="scan.pdf",
                content_type="application/pdf",
                source=DocumentSource.SCANNED_UPLOAD,
                status=PacketStatus.OCR_RUNNING,
                received_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
                created_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
                updated_at_utc=datetime(2026, 4, 15, 10, 1, tzinfo=UTC),
            ),
        ),
        processing_jobs=(
            ProcessingJobRecord(
                attempt_number=1,
                created_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
                document_id="doc_demo_ocr_001",
                job_id="job_ocr_001",
                packet_id="pkt_demo_ocr_001",
                queued_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
                stage_name=ProcessingStageName.OCR,
                status=ProcessingJobStatus.QUEUED,
                updated_at_utc=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
            ),
        ),
    )

    class FakeRepository:
        """Repository stub that returns one OCR packet snapshot."""

        def __init__(self, settings: object) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(self, packet_id: str) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_demo_ocr_001"
            return snapshot

    monkeypatch.setattr(packet_replay, "SqlOperatorStateRepository", FakeRepository)
    monkeypatch.setattr(
        packet_replay,
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

    response = packet_replay.replay_packet("pkt_demo_ocr_001", build_settings())

    assert response.action == "execute"
    assert response.stage_name == ProcessingStageName.OCR
    assert response.executed_document_count == 1
    assert response.next_stage == ProcessingStageName.REVIEW
    assert response.status == PacketStatus.AWAITING_REVIEW