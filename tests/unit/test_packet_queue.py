"""Unit tests for the SQL-backed packet queue service."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pytest import MonkeyPatch

from document_intelligence import packet_queue
from document_intelligence.models import (
    DocumentSource,
    PacketQueueItem,
    PacketQueueListRequest,
    PacketQueueListResponse,
    PacketStatus,
    ProcessingStageName,
)
from document_intelligence.processing_taxonomy import get_statuses_for_stage
from document_intelligence.settings import AppSettings


def build_settings(**overrides: object) -> AppSettings:
    """Build app settings for packet queue tests."""

    values: dict[str, object] = {
        "sql_connection_string": "Server=tcp:test.database.windows.net;",
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def test_list_packet_queue_raises_when_sql_is_unconfigured(
    monkeypatch: MonkeyPatch,
) -> None:
    """The queue service should fail fast when SQL operator state is unavailable."""

    class FakeRepository:
        """Repository stub that simulates an unconfigured SQL environment."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return False

    monkeypatch.setattr(packet_queue, "SqlOperatorStateRepository", FakeRepository)

    with pytest.raises(
        packet_queue.PacketQueueConfigurationError,
        match="Azure SQL operator-state storage is not configured",
    ):
        packet_queue.list_packet_queue(PacketQueueListRequest(), build_settings())


def test_list_packet_queue_passes_stage_statuses_to_repository(
    monkeypatch: MonkeyPatch,
) -> None:
    """Stage filters should expand into the taxonomy-backed status tuple."""

    captured: dict[str, object] = {}

    class FakeRepository:
        """Repository stub that records the queue request and stage statuses."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def list_packet_queue(
            self,
            request: PacketQueueListRequest,
            stage_statuses: tuple[PacketStatus, ...],
        ) -> PacketQueueListResponse:
            captured["request"] = request
            captured["stage_statuses"] = stage_statuses
            return PacketQueueListResponse(
                items=(
                    PacketQueueItem(
                        audit_event_count=3,
                        awaiting_review_document_count=1,
                        completed_document_count=0,
                        document_count=2,
                        operator_note_count=1,
                        packet_id="pkt_demo_001",
                        packet_name="demo packet",
                        queue_age_hours=12.5,
                        received_at_utc=datetime(2026, 4, 15, 8, 0, tzinfo=UTC),
                        review_task_count=1,
                        source=DocumentSource.SCANNED_UPLOAD,
                        source_uri="manual://packets/pkt_demo_001",
                        stage_name=ProcessingStageName.REVIEW,
                        status=PacketStatus.AWAITING_REVIEW,
                        updated_at_utc=datetime(2026, 4, 15, 8, 5, tzinfo=UTC),
                    ),
                ),
                page=request.page,
                page_size=request.page_size,
                total_count=1,
            )

    monkeypatch.setattr(packet_queue, "SqlOperatorStateRepository", FakeRepository)

    request = PacketQueueListRequest(
        page=2,
        page_size=10,
        source=DocumentSource.SCANNED_UPLOAD,
        stage_name=ProcessingStageName.REVIEW,
    )

    response = packet_queue.list_packet_queue(request, build_settings())

    assert response.page == 2
    assert response.page_size == 10
    assert response.total_count == 1
    assert response.items[0].packet_id == "pkt_demo_001"
    assert captured["request"] == request
    assert captured["stage_statuses"] == get_statuses_for_stage(
        ProcessingStageName.REVIEW
    )