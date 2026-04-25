"""Operator pipeline retry actions for packet-stage intervention."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from document_intelligence.models import (
    PacketClassificationExecutionResponse,
    PacketExtractionExecutionResponse,
    PacketOcrExecutionResponse,
    PacketRecommendationExecutionResponse,
    PacketStageRetryResponse,
    PacketStatus,
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStageName,
)
from document_intelligence.operator_state import SqlOperatorStateRepository
from document_intelligence.persistence import open_sql_connection
from document_intelligence.settings import AppSettings


class PacketPipelineActionConfigurationError(RuntimeError):
    """Raised when packet pipeline actions cannot run due to configuration."""


def _get_stage_retry_status(stage_name: ProcessingStageName) -> PacketStatus:
    """Return the packet-document status required to retry one processing stage."""

    if stage_name == ProcessingStageName.CLASSIFICATION:
        return PacketStatus.CLASSIFYING
    if stage_name == ProcessingStageName.OCR:
        return PacketStatus.OCR_RUNNING
    if stage_name == ProcessingStageName.EXTRACTION:
        return PacketStatus.EXTRACTING
    if stage_name == ProcessingStageName.RECOMMENDATION:
        return PacketStatus.READY_FOR_RECOMMENDATION
    raise ValueError(f"'{stage_name.value}' is not a supported retry stage.")


def _build_retry_event_type(stage_name: ProcessingStageName, *, packet_scope: bool) -> str:
    """Return the event type emitted when retry work is queued."""

    scope = "packet" if packet_scope else "document"
    return f"{scope}.{stage_name.value}.retry_queued"


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


def _is_retryable_job(
    job: ProcessingJobRecord,
    *,
    stale_before_utc: datetime,
) -> tuple[bool, str | None]:
    """Return whether one processing job should be requeued for retry."""

    if job.status == ProcessingJobStatus.FAILED:
        return True, "failed"

    if job.status == ProcessingJobStatus.RUNNING and job.updated_at_utc <= stale_before_utc:
        return True, "stale_running"

    return False, None


def _queue_retry_jobs(
    packet_id: str,
    stage_name: ProcessingStageName,
    settings: AppSettings,
    *,
    stale_after_minutes: int,
) -> tuple[int, int, int, tuple[str, ...], PacketStatus]:
    """Queue fresh retry jobs for the latest failed or stale stage attempts."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured() or not settings.sql_connection_string:
        raise PacketPipelineActionConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    target_status = _get_stage_retry_status(stage_name)
    snapshot = repository.get_packet_workspace_snapshot(packet_id)
    documents_by_id = {
        document.document_id: document
        for document in snapshot.documents
    }
    latest_jobs = _select_latest_jobs_by_document(snapshot.processing_jobs)
    stale_before_utc = datetime.now(UTC) - timedelta(minutes=stale_after_minutes)
    requeued_document_count = 0
    failed_job_count = 0
    stale_running_job_count = 0
    skipped_document_ids: list[str] = []

    with open_sql_connection(settings.sql_connection_string, autocommit=False) as connection:
        try:
            with connection.cursor() as cursor:
                for document_id, latest_job in latest_jobs.items():
                    if latest_job.stage_name != stage_name:
                        continue

                    document = documents_by_id.get(document_id)
                    if document is None or document.status == PacketStatus.QUARANTINED:
                        skipped_document_ids.append(document_id)
                        continue

                    should_retry, retry_reason = _is_retryable_job(
                        latest_job,
                        stale_before_utc=stale_before_utc,
                    )
                    if not should_retry or retry_reason is None:
                        skipped_document_ids.append(document_id)
                        continue

                    retry_job_id = f"job_{uuid4().hex}"
                    cursor.execute(
                        """
                        INSERT INTO dbo.ProcessingJobs (
                            jobId,
                            packetId,
                            documentId,
                            stageName,
                            status,
                            attemptNumber,
                            queuedAtUtc,
                            startedAtUtc,
                            completedAtUtc,
                            errorCode,
                            errorMessage,
                            createdAtUtc,
                            updatedAtUtc
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            SYSUTCDATETIME(),
                            NULL,
                            NULL,
                            NULL,
                            NULL,
                            SYSUTCDATETIME(),
                            SYSUTCDATETIME()
                        )
                        """,
                        (
                            retry_job_id,
                            packet_id,
                            document_id,
                            stage_name.value,
                            ProcessingJobStatus.QUEUED.value,
                            latest_job.attempt_number + 1,
                        ),
                    )
                    cursor.execute(
                        """
                        UPDATE dbo.PacketDocuments
                        SET
                            status = %s,
                            updatedAtUtc = SYSUTCDATETIME()
                        WHERE documentId = %s
                        """,
                        (target_status.value, document_id),
                    )
                    cursor.execute(
                        """
                        INSERT INTO dbo.PacketEvents (
                            packetId,
                            documentId,
                            eventType,
                            eventPayloadJson,
                            createdAtUtc
                        )
                        VALUES (%s, %s, %s, %s, SYSUTCDATETIME())
                        """,
                        (
                            packet_id,
                            document_id,
                            _build_retry_event_type(stage_name, packet_scope=False),
                            json.dumps(
                                {
                                    "attemptNumber": latest_job.attempt_number + 1,
                                    "previousJobId": latest_job.job_id,
                                    "previousStatus": latest_job.status.value,
                                    "retryJobId": retry_job_id,
                                    "retryReason": retry_reason,
                                    "stageName": stage_name.value,
                                }
                            ),
                        ),
                    )
                    requeued_document_count += 1
                    if retry_reason == "failed":
                        failed_job_count += 1
                    else:
                        stale_running_job_count += 1

                if requeued_document_count > 0:
                    cursor.execute(
                        """
                        UPDATE dbo.Packets
                        SET
                            status = %s,
                            updatedAtUtc = SYSUTCDATETIME()
                        WHERE packetId = %s
                        """,
                        (target_status.value, packet_id),
                    )
                    cursor.execute(
                        """
                        INSERT INTO dbo.PacketEvents (
                            packetId,
                            documentId,
                            eventType,
                            eventPayloadJson,
                            createdAtUtc
                        )
                        VALUES (%s, NULL, %s, %s, SYSUTCDATETIME())
                        """,
                        (
                            packet_id,
                            _build_retry_event_type(stage_name, packet_scope=True),
                            json.dumps(
                                {
                                    "failedJobCount": failed_job_count,
                                    "requeuedDocumentCount": requeued_document_count,
                                    "stageName": stage_name.value,
                                    "staleRunningJobCount": stale_running_job_count,
                                }
                            ),
                        ),
                    )

                connection.commit()
        except Exception:
            connection.rollback()
            raise

    return (
        requeued_document_count,
        failed_job_count,
        stale_running_job_count,
        tuple(skipped_document_ids),
        target_status if requeued_document_count > 0 else snapshot.packet.status,
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
    """Execute one supported packet stage after retry jobs are queued."""

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
    raise ValueError(f"'{stage_name.value}' is not a supported retry stage.")


def retry_packet_stage(
    packet_id: str,
    stage_name: str,
    settings: AppSettings,
    *,
    stale_after_minutes: int = 30,
) -> PacketStageRetryResponse:
    """Requeue failed or stale work for one packet stage and execute it."""

    parsed_stage_name = ProcessingStageName(stage_name)
    requeued_count, failed_count, stale_count, skipped_document_ids, packet_status = (
        _queue_retry_jobs(
            packet_id,
            parsed_stage_name,
            settings,
            stale_after_minutes=stale_after_minutes,
        )
    )

    if requeued_count == 0:
        return PacketStageRetryResponse(
            packet_id=packet_id,
            stage_name=parsed_stage_name,
            status=packet_status,
            failed_job_count=failed_count,
            requeued_document_count=0,
            skipped_document_ids=skipped_document_ids,
            stale_running_job_count=stale_count,
        )

    execution_response = _execute_stage(packet_id, parsed_stage_name, settings)
    return PacketStageRetryResponse(
        packet_id=packet_id,
        stage_name=parsed_stage_name,
        status=execution_response.status,
        executed_document_count=execution_response.executed_document_count,
        failed_job_count=failed_count,
        next_stage=execution_response.next_stage,
        requeued_document_count=requeued_count,
        skipped_document_ids=execution_response.skipped_document_ids,
        stale_running_job_count=stale_count,
    )