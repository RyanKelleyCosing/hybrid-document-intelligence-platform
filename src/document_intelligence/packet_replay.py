"""Packet replay helpers for the Intake workspace."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from document_intelligence.models import (
    PacketClassificationExecutionResponse,
    PacketExtractionExecutionResponse,
    PacketOcrExecutionResponse,
    PacketRecommendationExecutionResponse,
    PacketReplayResponse,
    PacketStatus,
    PacketWorkspaceSnapshot,
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStageName,
)
from document_intelligence.operator_state import SqlOperatorStateRepository
from document_intelligence.packet_pipeline_actions import retry_packet_stage
from document_intelligence.settings import AppSettings


class PacketReplayConfigurationError(RuntimeError):
    """Raised when packet replay cannot run due to missing configuration."""


def _select_latest_jobs_by_document(
    processing_jobs: tuple[ProcessingJobRecord, ...],
) -> dict[str, ProcessingJobRecord]:
    """Return the latest persisted processing job for each document."""

    latest_jobs: dict[str, ProcessingJobRecord] = {}
    for job in processing_jobs:
        if job.document_id is None:
            continue

        current_job = latest_jobs.get(job.document_id)
        if current_job is None or job.created_at_utc >= current_job.created_at_utc:
            latest_jobs[job.document_id] = job

    return latest_jobs


def _resolve_retry_stage(
    snapshot: PacketWorkspaceSnapshot,
    *,
    stale_before_utc: datetime,
) -> ProcessingStageName | None:
    """Return the packet stage that should be retried, when one exists."""

    latest_jobs = _select_latest_jobs_by_document(snapshot.processing_jobs)
    supported_stages = (
        ProcessingStageName.CLASSIFICATION,
        ProcessingStageName.OCR,
        ProcessingStageName.EXTRACTION,
        ProcessingStageName.RECOMMENDATION,
    )

    for stage_name in supported_stages:
        for latest_job in latest_jobs.values():
            if latest_job.stage_name != stage_name:
                continue
            if latest_job.status == ProcessingJobStatus.FAILED:
                return stage_name
            if (
                latest_job.status == ProcessingJobStatus.RUNNING
                and latest_job.updated_at_utc <= stale_before_utc
            ):
                return stage_name

    return None


def _resolve_execute_stage(
    snapshot: PacketWorkspaceSnapshot,
) -> ProcessingStageName:
    """Return the stage that should be executed for queued packet work."""

    document_statuses = {document.status for document in snapshot.documents}
    packet_status = snapshot.packet.status

    if packet_status == PacketStatus.QUARANTINED:
        raise ValueError(
            "Quarantined packets must be re-ingested or manually resolved before replay."
        )
    if packet_status in {PacketStatus.AWAITING_REVIEW, PacketStatus.BLOCKED}:
        raise ValueError(
            "Review-held packets must be handled through review decisions before replay."
        )
    if packet_status == PacketStatus.COMPLETED:
        raise ValueError("Completed packets do not have replayable intake work.")

    if packet_status in {PacketStatus.RECEIVED, PacketStatus.CLASSIFYING} or (
        PacketStatus.RECEIVED in document_statuses
    ):
        return ProcessingStageName.CLASSIFICATION
    if packet_status == PacketStatus.OCR_RUNNING or PacketStatus.OCR_RUNNING in document_statuses:
        return ProcessingStageName.OCR
    if packet_status in {PacketStatus.EXTRACTING, PacketStatus.MATCHING} or (
        PacketStatus.EXTRACTING in document_statuses
        or PacketStatus.MATCHING in document_statuses
    ):
        return ProcessingStageName.EXTRACTION
    if (
        packet_status == PacketStatus.READY_FOR_RECOMMENDATION
        or PacketStatus.READY_FOR_RECOMMENDATION in document_statuses
    ):
        return ProcessingStageName.RECOMMENDATION

    raise ValueError(
        "The selected packet does not have queued or retryable intake work to replay."
    )


def _execute_stage(
    packet_id: str,
    stage_name: ProcessingStageName,
    settings: AppSettings,
) -> (
    PacketClassificationExecutionResponse
    | PacketOcrExecutionResponse
    | PacketExtractionExecutionResponse
    | PacketRecommendationExecutionResponse
):
    """Execute one supported packet stage for replay."""

    if stage_name == ProcessingStageName.CLASSIFICATION:
        from document_intelligence.packet_classification import execute_packet_classification_stage

        return execute_packet_classification_stage(packet_id, settings)
    if stage_name == ProcessingStageName.OCR:
        from document_intelligence.packet_ocr import execute_packet_ocr_stage

        return execute_packet_ocr_stage(packet_id, settings)
    if stage_name == ProcessingStageName.EXTRACTION:
        from document_intelligence.packet_extraction import execute_packet_extraction_stage

        return execute_packet_extraction_stage(packet_id, settings)
    if stage_name == ProcessingStageName.RECOMMENDATION:
        from document_intelligence.packet_recommendation import execute_packet_recommendation_stage

        return execute_packet_recommendation_stage(packet_id, settings)
    raise ValueError(f"'{stage_name.value}' is not a supported replay stage.")


def replay_packet(
    packet_id: str,
    settings: AppSettings,
    *,
    stale_after_minutes: int = 30,
) -> PacketReplayResponse:
    """Replay the next actionable packet stage from the Intake workspace."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        raise PacketReplayConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    snapshot = repository.get_packet_workspace_snapshot(packet_id)
    retry_stage = _resolve_retry_stage(
        snapshot,
        stale_before_utc=datetime.now(UTC) - timedelta(minutes=stale_after_minutes),
    )
    if retry_stage is not None:
        retry_response = retry_packet_stage(
            packet_id,
            retry_stage.value,
            settings,
            stale_after_minutes=stale_after_minutes,
        )
        return PacketReplayResponse(
            action="retry",
            executed_document_count=retry_response.executed_document_count,
            failed_job_count=retry_response.failed_job_count,
            message=(
                f"Retried {retry_stage.value} for {retry_response.requeued_document_count} "
                "document(s)."
            ),
            next_stage=retry_response.next_stage,
            packet_id=packet_id,
            requeued_document_count=retry_response.requeued_document_count,
            skipped_document_ids=retry_response.skipped_document_ids,
            stage_name=retry_response.stage_name,
            stale_running_job_count=retry_response.stale_running_job_count,
            status=retry_response.status,
        )

    execute_stage = _resolve_execute_stage(snapshot)
    execute_response = _execute_stage(packet_id, execute_stage, settings)
    return PacketReplayResponse(
        action="execute",
        executed_document_count=execute_response.executed_document_count,
        failed_job_count=0,
        message=(
            f"Executed queued {execute_stage.value} work for "
            f"{execute_response.executed_document_count} document(s)."
        ),
        next_stage=execute_response.next_stage,
        packet_id=packet_id,
        requeued_document_count=0,
        skipped_document_ids=execute_response.skipped_document_ids,
        stage_name=execute_stage,
        stale_running_job_count=0,
        status=execute_response.status,
    )