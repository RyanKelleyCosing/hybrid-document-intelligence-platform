"""Unit tests for the canonical packet-processing taxonomy."""

from __future__ import annotations

from document_intelligence.models import PacketStatus, ProcessingStageName
from document_intelligence.processing_taxonomy import (
    get_processing_taxonomy,
    get_stage_name_for_status,
    get_statuses_for_stage,
)


def test_processing_taxonomy_covers_supported_packet_statuses() -> None:
    """The taxonomy should expose every packet status planned for the operator flow."""

    response = get_processing_taxonomy()
    supported_statuses = {status.status for status in response.statuses}

    assert supported_statuses == {
        PacketStatus.RECEIVED,
        PacketStatus.ARCHIVE_EXPANDING,
        PacketStatus.CLASSIFYING,
        PacketStatus.OCR_RUNNING,
        PacketStatus.EXTRACTING,
        PacketStatus.MATCHING,
        PacketStatus.AWAITING_REVIEW,
        PacketStatus.READY_FOR_RECOMMENDATION,
        PacketStatus.COMPLETED,
        PacketStatus.BLOCKED,
        PacketStatus.FAILED,
        PacketStatus.QUARANTINED,
    }


def test_processing_taxonomy_exposes_stage_coverage() -> None:
    """The taxonomy should group the statuses under the expected stage names."""

    response = get_processing_taxonomy()
    supported_stages = {stage.stage_name for stage in response.stages}

    assert supported_stages == {
        ProcessingStageName.INTAKE,
        ProcessingStageName.ARCHIVE_EXPANSION,
        ProcessingStageName.CLASSIFICATION,
        ProcessingStageName.OCR,
        ProcessingStageName.EXTRACTION,
        ProcessingStageName.MATCHING,
        ProcessingStageName.REVIEW,
        ProcessingStageName.RECOMMENDATION,
        ProcessingStageName.QUARANTINE,
    }


def test_processing_taxonomy_helpers_map_statuses_and_stages() -> None:
    """Status-to-stage helpers should stay aligned with the taxonomy contract."""

    assert get_stage_name_for_status(PacketStatus.AWAITING_REVIEW) == (
        ProcessingStageName.REVIEW
    )
    assert get_statuses_for_stage(ProcessingStageName.REVIEW) == (
        PacketStatus.AWAITING_REVIEW,
        PacketStatus.BLOCKED,
        PacketStatus.FAILED,
    )