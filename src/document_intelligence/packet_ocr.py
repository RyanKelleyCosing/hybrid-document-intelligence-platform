"""Packet-level OCR execution and extraction handoff helpers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from document_intelligence.extraction import (
    OCR_QUALITY_WARNING_PREFIX,
    extract_ocr_text,
    select_extraction_strategy,
)
from document_intelligence.models import (
    ClassificationResultRecord,
    DocumentAssetRecord,
    DocumentIngestionRequest,
    ExtractionStrategySelection,
    ManagedDocumentTypeDefinitionRecord,
    PacketDocumentRecord,
    PacketOcrExecutionDocumentResult,
    PacketOcrExecutionResponse,
    PacketStatus,
    PacketWorkspaceSnapshot,
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStageName,
    PromptProfileId,
    ReviewReason,
    ReviewTaskPriority,
    SafetyIssue,
    SafetyIssueSeverity,
)
from document_intelligence.operator_state import SqlOperatorStateRepository
from document_intelligence.orchestration import normalize_request
from document_intelligence.safety import serialize_safety_issues
from document_intelligence.settings import AppSettings
from document_intelligence.utils.blob_storage import (
    BlobAsset,
    delete_blob_asset,
    upload_blob_bytes,
)
from document_intelligence.utils.sql import open_sql_connection

OCR_TEXT_EXCERPT_CHARS = 600


class PacketOcrConfigurationError(RuntimeError):
    """Raised when packet OCR execution cannot run."""


@dataclass(frozen=True)
class _ResolvedOcrResult:
    """Resolved OCR output before SQL persistence."""

    model_name: str | None
    ocr_confidence: float
    page_count: int
    provider: str
    safety_issues: tuple[SafetyIssue, ...]
    stored_text_asset: BlobAsset | None
    text_excerpt: str | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _PendingOcrExecution:
    """One queued OCR job ready for persistence."""

    classification_result: ClassificationResultRecord | None
    document: PacketDocumentRecord
    extraction_job_id: str | None
    extraction_strategy: ExtractionStrategySelection
    ocr_job_id: str
    ocr_result: _ResolvedOcrResult
    ocr_result_id: str
    review_task_id: str | None
    status: PacketStatus


def _build_ocr_quality_safety_issue(message: str) -> SafetyIssue:
    """Return one OCR quality issue that requires operator review."""

    return SafetyIssue(
        code=ReviewReason.OCR_QUALITY_WARNING.value,
        message=message,
        severity=SafetyIssueSeverity.WARNING,
        stage_name=ProcessingStageName.OCR,
    )


def _resolve_ocr_safety_issues(warnings: tuple[str, ...]) -> tuple[SafetyIssue, ...]:
    """Return OCR safety issues surfaced through standardized warning text."""

    issues_by_message: dict[str, SafetyIssue] = {}
    for warning in warnings:
        if not warning.startswith(OCR_QUALITY_WARNING_PREFIX):
            continue

        message = warning.removeprefix(OCR_QUALITY_WARNING_PREFIX).strip()
        if not message:
            continue

        issues_by_message[message] = _build_ocr_quality_safety_issue(message)

    return tuple(issues_by_message.values())


def _build_extraction_handoff_execution(
    *,
    classification_result: ClassificationResultRecord | None,
    document: PacketDocumentRecord,
    extraction_strategy: ExtractionStrategySelection,
    ocr_job_id: str,
    ocr_result: _ResolvedOcrResult,
    ocr_result_id: str,
) -> _PendingOcrExecution:
    """Build one OCR execution that can queue extraction immediately."""

    return _PendingOcrExecution(
        classification_result=classification_result,
        document=document,
        extraction_job_id=f"job_{uuid4().hex}",
        extraction_strategy=extraction_strategy,
        ocr_job_id=ocr_job_id,
        ocr_result=ocr_result,
        ocr_result_id=ocr_result_id,
        review_task_id=None,
        status=PacketStatus.EXTRACTING,
    )


def _build_review_required_execution(
    *,
    classification_result: ClassificationResultRecord | None,
    document: PacketDocumentRecord,
    extraction_strategy: ExtractionStrategySelection,
    ocr_job_id: str,
    ocr_result: _ResolvedOcrResult,
    ocr_result_id: str,
) -> _PendingOcrExecution:
    """Build one OCR execution that pauses for operator review."""

    return _PendingOcrExecution(
        classification_result=classification_result,
        document=document,
        extraction_job_id=None,
        extraction_strategy=extraction_strategy,
        ocr_job_id=ocr_job_id,
        ocr_result=ocr_result,
        ocr_result_id=ocr_result_id,
        review_task_id=f"task_{uuid4().hex}",
        status=PacketStatus.AWAITING_REVIEW,
    )


def _serialize_prompt_profile_id(
    prompt_profile_id: PromptProfileId | None,
) -> str | None:
    """Return the prompt-profile id when one is available."""

    return prompt_profile_id.value if prompt_profile_id is not None else None


def _select_latest_jobs_by_document(
    processing_jobs: tuple[ProcessingJobRecord, ...],
) -> dict[str, ProcessingJobRecord]:
    """Return the latest processing job for each document in one packet."""

    latest_jobs: dict[str, ProcessingJobRecord] = {}
    for job in processing_jobs:
        if job.document_id is None:
            continue

        current_job = latest_jobs.get(job.document_id)
        if current_job is None or job.created_at_utc >= current_job.created_at_utc:
            latest_jobs[job.document_id] = job

    return latest_jobs


def _select_primary_asset_by_document(
    document_assets: tuple[DocumentAssetRecord, ...],
) -> dict[str, DocumentAssetRecord]:
    """Return the preferred persisted asset for each document."""

    asset_priority = {"original_upload": 0, "archive_extracted_member": 1}
    selected_assets: dict[str, DocumentAssetRecord] = {}
    for asset in document_assets:
        current_asset = selected_assets.get(asset.document_id)
        if current_asset is None:
            selected_assets[asset.document_id] = asset
            continue

        current_priority = asset_priority.get(current_asset.asset_role, 99)
        candidate_priority = asset_priority.get(asset.asset_role, 99)
        if candidate_priority < current_priority:
            selected_assets[asset.document_id] = asset

    return selected_assets


def _select_latest_classification_results_by_document(
    classification_results: tuple[ClassificationResultRecord, ...],
) -> dict[str, ClassificationResultRecord]:
    """Return the latest persisted classification result for each document."""

    latest_results: dict[str, ClassificationResultRecord] = {}
    for result in classification_results:
        current_result = latest_results.get(result.document_id)
        if (
            current_result is None
            or result.created_at_utc >= current_result.created_at_utc
        ):
            latest_results[result.document_id] = result

    return latest_results


def _build_document_request(
    *,
    asset_by_document_id: dict[str, DocumentAssetRecord],
    document: PacketDocumentRecord,
    packet_source_uri: str,
) -> DocumentIngestionRequest:
    """Build a normalized document request from the packet workspace state."""

    asset = asset_by_document_id.get(document.document_id)
    source_uri = document.source_uri or packet_source_uri
    if asset is not None:
        source_uri = asset.storage_uri

    return normalize_request(
        DocumentIngestionRequest(
            account_candidates=document.account_candidates,
            content_type=document.content_type,
            document_id=document.document_id,
            document_text=document.document_text,
            file_name=document.file_name,
            issuer_category=document.issuer_category,
            issuer_name=document.issuer_name,
            received_at_utc=document.received_at_utc,
            requested_prompt_profile_id=document.requested_prompt_profile_id,
            source=document.source,
            source_summary=document.source_summary,
            source_tags=document.source_tags,
            source_uri=source_uri,
        )
    )


def _build_ocr_text_excerpt(ocr_text: str) -> str | None:
    """Return the excerpt persisted with an OCR result row."""

    normalized_text = ocr_text.strip()
    if not normalized_text:
        return None

    return normalized_text[:OCR_TEXT_EXCERPT_CHARS]


def _build_ocr_text_blob_name(
    packet_id: str,
    document_id: str,
    ocr_result_id: str,
) -> str:
    """Return the processed-container blob name for OCR text output."""

    return f"packet-ocr/{packet_id}/{document_id}/{ocr_result_id}.txt"


def _store_ocr_text_asset(
    *,
    document_id: str,
    ocr_result_id: str,
    ocr_text: str,
    packet_id: str,
    settings: AppSettings,
) -> BlobAsset | None:
    """Persist OCR text to Blob storage when content and config are available."""

    normalized_text = ocr_text.strip()
    if not normalized_text or not settings.storage_connection_string:
        return None

    return upload_blob_bytes(
        blob_name=_build_ocr_text_blob_name(packet_id, document_id, ocr_result_id),
        container_name=settings.processed_container_name,
        content_type="text/plain; charset=utf-8",
        data=normalized_text.encode("utf-8"),
        storage_connection_string=settings.storage_connection_string,
    )


def _resolve_ocr_result(
    *,
    document_id: str,
    ocr_result_id: str,
    packet_id: str,
    request: DocumentIngestionRequest,
    settings: AppSettings,
) -> _ResolvedOcrResult:
    """Resolve OCR output and the optional stored text asset for one document."""

    ocr_text, ocr_confidence, page_count, warnings, provider = extract_ocr_text(
        request,
        settings,
    )
    stored_text_asset = _store_ocr_text_asset(
        document_id=document_id,
        ocr_result_id=ocr_result_id,
        ocr_text=ocr_text,
        packet_id=packet_id,
        settings=settings,
    )
    model_name = (
        settings.document_intelligence_model_id
        if provider == "azure_document_intelligence"
        else None
    )
    safety_issues = _resolve_ocr_safety_issues(warnings)
    return _ResolvedOcrResult(
        model_name=model_name,
        ocr_confidence=ocr_confidence,
        page_count=page_count,
        provider=provider,
        safety_issues=safety_issues,
        stored_text_asset=stored_text_asset,
        text_excerpt=_build_ocr_text_excerpt(ocr_text),
        warnings=warnings,
    )


def _build_pending_ocr_execution(
    *,
    asset_by_document_id: dict[str, DocumentAssetRecord],
    classification_result: ClassificationResultRecord | None,
    document: PacketDocumentRecord,
    document_type_definitions: tuple[ManagedDocumentTypeDefinitionRecord, ...],
    latest_job: ProcessingJobRecord,
    packet_source_uri: str,
    settings: AppSettings,
) -> _PendingOcrExecution:
    """Resolve one queued OCR execution before persistence."""

    ocr_result_id = f"ocr_{uuid4().hex}"
    request = _build_document_request(
        asset_by_document_id=asset_by_document_id,
        document=document,
        packet_source_uri=packet_source_uri,
    )
    extraction_strategy = select_extraction_strategy(
        classification_result=classification_result,
        document_type_definitions=document_type_definitions,
        request=request,
        settings=settings,
    )
    ocr_result = _resolve_ocr_result(
        document_id=document.document_id,
        ocr_result_id=ocr_result_id,
        packet_id=document.packet_id,
        request=request,
        settings=settings,
    )
    if ocr_result.safety_issues:
        return _build_review_required_execution(
            classification_result=classification_result,
            document=document,
            extraction_strategy=extraction_strategy,
            ocr_job_id=latest_job.job_id,
            ocr_result=ocr_result,
            ocr_result_id=ocr_result_id,
        )

    return _build_extraction_handoff_execution(
        classification_result=classification_result,
        document=document,
        extraction_strategy=extraction_strategy,
        ocr_job_id=latest_job.job_id,
        ocr_result=ocr_result,
        ocr_result_id=ocr_result_id,
    )


def _resolve_packet_handoff(
    *,
    processed_statuses: dict[str, PacketStatus],
    snapshot: PacketWorkspaceSnapshot,
) -> tuple[PacketStatus, ProcessingStageName]:
    """Return the packet status after OCR has queued extraction work."""

    latest_jobs = _select_latest_jobs_by_document(snapshot.processing_jobs)
    effective_statuses = {
        document.document_id: document.status for document in snapshot.documents
    }
    effective_statuses.update(processed_statuses)

    if any(
        status == PacketStatus.QUARANTINED for status in effective_statuses.values()
    ):
        return PacketStatus.QUARANTINED, ProcessingStageName.QUARANTINE

    if any(
        status == PacketStatus.AWAITING_REVIEW
        for status in effective_statuses.values()
    ):
        return PacketStatus.AWAITING_REVIEW, ProcessingStageName.REVIEW

    if any(status == PacketStatus.EXTRACTING for status in processed_statuses.values()):
        return PacketStatus.EXTRACTING, ProcessingStageName.EXTRACTION

    if any(
        latest_jobs.get(document.document_id) is not None
        and latest_jobs[document.document_id].stage_name == ProcessingStageName.OCR
        and latest_jobs[document.document_id].status != ProcessingJobStatus.SUCCEEDED
        and document.document_id not in processed_statuses
        for document in snapshot.documents
    ):
        return snapshot.packet.status, ProcessingStageName.OCR

    return snapshot.packet.status, ProcessingStageName.EXTRACTION


def _set_job_running(cursor: Any, job_id: str) -> None:
    """Mark one processing job as running."""

    cursor.execute(
        """
        UPDATE dbo.ProcessingJobs
        SET
            status = %s,
            startedAtUtc = COALESCE(startedAtUtc, SYSUTCDATETIME()),
            updatedAtUtc = SYSUTCDATETIME()
        WHERE jobId = %s
        """,
        (ProcessingJobStatus.RUNNING.value, job_id),
    )


def _set_job_succeeded(cursor: Any, job_id: str) -> None:
    """Mark one processing job as completed successfully."""

    cursor.execute(
        """
        UPDATE dbo.ProcessingJobs
        SET
            status = %s,
            completedAtUtc = SYSUTCDATETIME(),
            updatedAtUtc = SYSUTCDATETIME()
        WHERE jobId = %s
        """,
        (ProcessingJobStatus.SUCCEEDED.value, job_id),
    )


def _update_document_status(
    cursor: Any,
    document_id: str,
    status: PacketStatus,
) -> None:
    """Persist the latest packet-document status."""

    cursor.execute(
        """
        UPDATE dbo.PacketDocuments
        SET
            status = %s,
            updatedAtUtc = SYSUTCDATETIME()
        WHERE documentId = %s
        """,
        (status.value, document_id),
    )


def _insert_packet_event(
    cursor: Any,
    *,
    document_id: str | None,
    event_payload: dict[str, Any],
    event_type: str,
    packet_id: str,
) -> None:
    """Append one packet event row."""

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
        (packet_id, document_id, event_type, json.dumps(event_payload)),
    )


def _insert_ocr_result(
    cursor: Any,
    *,
    execution: _PendingOcrExecution,
    packet_id: str,
) -> None:
    """Persist one OCR result row."""

    cursor.execute(
        """
        INSERT INTO dbo.OcrResults (
            ocrResultId,
            packetId,
            documentId,
            provider,
            modelName,
            pageCount,
            ocrConfidence,
            textStorageUri,
            textExcerpt,
            createdAtUtc
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, SYSUTCDATETIME())
        """,
        (
            execution.ocr_result_id,
            packet_id,
            execution.document.document_id,
            execution.ocr_result.provider,
            execution.ocr_result.model_name,
            execution.ocr_result.page_count,
            execution.ocr_result.ocr_confidence,
            (
                execution.ocr_result.stored_text_asset.storage_uri
                if execution.ocr_result.stored_text_asset is not None
                else None
            ),
            execution.ocr_result.text_excerpt,
        ),
    )


def _queue_extraction_job(
    cursor: Any,
    *,
    execution: _PendingOcrExecution,
    packet_id: str,
) -> None:
    """Queue one extraction job after OCR completes."""

    if execution.extraction_job_id is None:
        raise RuntimeError("Extraction job id is required to queue extraction work.")

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
            1,
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
            execution.extraction_job_id,
            packet_id,
            execution.document.document_id,
            ProcessingStageName.EXTRACTION.value,
            ProcessingJobStatus.QUEUED.value,
        ),
    )


def _build_ocr_started_event_payload(
    execution: _PendingOcrExecution,
) -> dict[str, Any]:
    """Return the event payload for a started OCR job."""

    return {
        "classificationResultId": (
            execution.classification_result.classification_result_id
            if execution.classification_result is not None
            else None
        ),
        "ocrJobId": execution.ocr_job_id,
        "stageName": ProcessingStageName.OCR.value,
        "status": ProcessingJobStatus.RUNNING.value,
    }


def _build_ocr_completed_event_payload(
    execution: _PendingOcrExecution,
) -> dict[str, Any]:
    """Return the event payload for a completed OCR job."""

    return {
        "classificationResultId": (
            execution.classification_result.classification_result_id
            if execution.classification_result is not None
            else None
        ),
        "modelName": execution.ocr_result.model_name,
        "ocrConfidence": execution.ocr_result.ocr_confidence,
        "ocrJobId": execution.ocr_job_id,
        "ocrResultId": execution.ocr_result_id,
        "pageCount": execution.ocr_result.page_count,
        "provider": execution.ocr_result.provider,
        "reviewTaskId": execution.review_task_id,
        "safetyIssues": serialize_safety_issues(execution.ocr_result.safety_issues),
        "status": execution.status.value,
        "textExcerpt": execution.ocr_result.text_excerpt,
        "textStorageUri": (
            execution.ocr_result.stored_text_asset.storage_uri
            if execution.ocr_result.stored_text_asset is not None
            else None
        ),
        "warnings": list(execution.ocr_result.warnings),
    }


def _build_extraction_queued_event_payload(
    execution: _PendingOcrExecution,
) -> dict[str, Any]:
    """Return the event payload for an extraction handoff."""

    if execution.extraction_job_id is None:
        raise RuntimeError("Extraction job id is required for extraction handoff.")

    return {
        "classificationResultId": (
            execution.classification_result.classification_result_id
            if execution.classification_result is not None
            else None
        ),
        "extractionJobId": execution.extraction_job_id,
        "ocrJobId": execution.ocr_job_id,
        "ocrResultId": execution.ocr_result_id,
        "stageName": ProcessingStageName.EXTRACTION.value,
        "status": ProcessingJobStatus.QUEUED.value,
        "strategy": execution.extraction_strategy.model_dump(mode="json"),
    }


def _build_ocr_review_required_event_payload(
    execution: _PendingOcrExecution,
) -> dict[str, Any]:
    """Return the event payload for OCR work that paused for review."""

    return {
        **_build_ocr_completed_event_payload(execution),
        "reasonCodes": list(
            dict.fromkeys(
                issue.code for issue in execution.ocr_result.safety_issues
            )
        ),
        "stageName": ProcessingStageName.REVIEW.value,
        "summary": " ".join(
            issue.message for issue in execution.ocr_result.safety_issues
        ),
    }


def _build_review_task_created_event_payload(
    execution: _PendingOcrExecution,
) -> dict[str, Any]:
    """Return the event payload for an OCR-driven review task."""

    return {
        "priority": ReviewTaskPriority.HIGH.value,
        "reasonCodes": list(
            dict.fromkeys(
                issue.code for issue in execution.ocr_result.safety_issues
            )
        ),
        "reviewTaskId": execution.review_task_id,
        "safetyIssues": serialize_safety_issues(execution.ocr_result.safety_issues),
        "stageName": ProcessingStageName.REVIEW.value,
        "status": PacketStatus.AWAITING_REVIEW.value,
        "summary": " ".join(
            issue.message for issue in execution.ocr_result.safety_issues
        ),
    }


def _insert_review_task(
    cursor: Any,
    *,
    execution: _PendingOcrExecution,
    packet_id: str,
) -> None:
    """Persist one OCR-driven review task when quality warnings trigger."""

    if execution.review_task_id is None:
        return

    reason_codes = tuple(
        dict.fromkeys(issue.code for issue in execution.ocr_result.safety_issues)
    )
    cursor.execute(
        """
        INSERT INTO dbo.ReviewTasks (
            reviewTaskId,
            packetId,
            documentId,
            assignedUserId,
            assignedUserEmail,
            status,
            priority,
            selectedAccountId,
            reasonCodesJson,
            notesSummary,
            dueAtUtc,
            createdAtUtc,
            updatedAtUtc
        )
        VALUES (
            %s,
            %s,
            %s,
            NULL,
            NULL,
            %s,
            %s,
            NULL,
            %s,
            %s,
            NULL,
            SYSUTCDATETIME(),
            SYSUTCDATETIME()
        )
        """,
        (
            execution.review_task_id,
            packet_id,
            execution.document.document_id,
            PacketStatus.AWAITING_REVIEW.value,
            ReviewTaskPriority.HIGH.value,
            json.dumps(list(reason_codes)),
            " ".join(issue.message for issue in execution.ocr_result.safety_issues),
        ),
    )


def _persist_document_ocr_handoff(
    cursor: Any,
    *,
    execution: _PendingOcrExecution,
    packet_id: str,
) -> None:
    """Persist OCR completion and the extraction handoff for one document."""

    _set_job_running(cursor, execution.ocr_job_id)
    _insert_packet_event(
        cursor,
        document_id=execution.document.document_id,
        event_payload=_build_ocr_started_event_payload(execution),
        event_type="document.ocr.started",
        packet_id=packet_id,
    )
    _insert_ocr_result(cursor, execution=execution, packet_id=packet_id)
    _set_job_succeeded(cursor, execution.ocr_job_id)
    if execution.review_task_id is not None:
        _update_document_status(
            cursor,
            execution.document.document_id,
            PacketStatus.AWAITING_REVIEW,
        )
        _insert_review_task(cursor, execution=execution, packet_id=packet_id)
        _insert_packet_event(
            cursor,
            document_id=execution.document.document_id,
            event_payload=_build_ocr_review_required_event_payload(execution),
            event_type="document.ocr.review_required",
            packet_id=packet_id,
        )
        _insert_packet_event(
            cursor,
            document_id=execution.document.document_id,
            event_payload=_build_review_task_created_event_payload(execution),
            event_type="document.review_task.created",
            packet_id=packet_id,
        )
        return

    _update_document_status(
        cursor,
        execution.document.document_id,
        PacketStatus.EXTRACTING,
    )
    _queue_extraction_job(cursor, execution=execution, packet_id=packet_id)
    _insert_packet_event(
        cursor,
        document_id=execution.document.document_id,
        event_payload=_build_ocr_completed_event_payload(execution),
        event_type="document.ocr.completed",
        packet_id=packet_id,
    )
    _insert_packet_event(
        cursor,
        document_id=execution.document.document_id,
        event_payload=_build_extraction_queued_event_payload(execution),
        event_type="document.extraction.queued",
        packet_id=packet_id,
    )


def _persist_ocr_handoff(
    *,
    packet_id: str,
    packet_status: PacketStatus,
    pending_executions: tuple[_PendingOcrExecution, ...],
    settings: AppSettings,
) -> None:
    """Persist OCR completion and queue extraction for the packet."""

    if not pending_executions:
        return

    first_packet_id = pending_executions[0].document.packet_id
    if packet_id != first_packet_id:
        raise RuntimeError(
            "Pending execution packet ids do not match the target packet."
        )

    connection_string = settings.sql_connection_string
    if not connection_string:
        raise PacketOcrConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    with open_sql_connection(connection_string, autocommit=False) as connection:
        try:
            with connection.cursor() as cursor:
                for execution in pending_executions:
                    _persist_document_ocr_handoff(
                        cursor,
                        execution=execution,
                        packet_id=packet_id,
                    )

                cursor.execute(
                    """
                    UPDATE dbo.Packets
                    SET
                        status = %s,
                        updatedAtUtc = SYSUTCDATETIME()
                    WHERE packetId = %s
                    """,
                    (packet_status.value, packet_id),
                )
                _insert_packet_event(
                    cursor,
                    document_id=None,
                    event_payload={
                        "executedDocumentCount": len(pending_executions),
                        "nextStage": (
                            ProcessingStageName.REVIEW.value
                            if packet_status == PacketStatus.AWAITING_REVIEW
                            else ProcessingStageName.EXTRACTION.value
                        ),
                        "status": packet_status.value,
                    },
                    event_type="packet.ocr.executed",
                    packet_id=packet_id,
                )

            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _cleanup_uploaded_assets(
    uploaded_assets: tuple[BlobAsset, ...],
    settings: AppSettings,
) -> None:
    """Best-effort rollback for OCR text blobs uploaded before SQL persistence."""

    if not uploaded_assets or not settings.storage_connection_string:
        return

    for asset in uploaded_assets:
        try:
            delete_blob_asset(
                blob_name=asset.blob_name,
                container_name=asset.container_name,
                storage_connection_string=settings.storage_connection_string,
            )
        except Exception as error:  # pragma: no cover - cleanup only
            logging.warning(
                "Failed to roll back OCR text blob %s: %s",
                asset.storage_uri,
                error,
            )


def execute_packet_ocr_stage(
    packet_id: str,
    settings: AppSettings,
) -> PacketOcrExecutionResponse:
    """Execute queued packet OCR work and queue extraction handoff."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        raise PacketOcrConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    snapshot = repository.get_packet_workspace_snapshot(packet_id)
    document_type_definitions = repository.list_document_type_definitions()
    latest_jobs = _select_latest_jobs_by_document(snapshot.processing_jobs)
    asset_by_document_id = _select_primary_asset_by_document(snapshot.document_assets)
    classification_results_by_document = (
        _select_latest_classification_results_by_document(
            snapshot.classification_results
        )
    )
    pending_executions: list[_PendingOcrExecution] = []
    skipped_document_ids: list[str] = []
    uploaded_assets: list[BlobAsset] = []

    try:
        for document in snapshot.documents:
            latest_job = latest_jobs.get(document.document_id)
            if latest_job is None:
                skipped_document_ids.append(document.document_id)
                continue

            if latest_job.stage_name != ProcessingStageName.OCR:
                skipped_document_ids.append(document.document_id)
                continue

            if latest_job.status != ProcessingJobStatus.QUEUED:
                skipped_document_ids.append(document.document_id)
                continue

            if document.status not in {PacketStatus.OCR_RUNNING, PacketStatus.RECEIVED}:
                skipped_document_ids.append(document.document_id)
                continue

            execution = _build_pending_ocr_execution(
                asset_by_document_id=asset_by_document_id,
                classification_result=classification_results_by_document.get(
                    document.document_id
                ),
                document=document,
                document_type_definitions=document_type_definitions,
                latest_job=latest_job,
                packet_source_uri=(
                    snapshot.packet.source_uri
                    or f"manual://packets/{snapshot.packet.packet_id}"
                ),
                settings=settings,
            )
            pending_executions.append(execution)
            if execution.ocr_result.stored_text_asset is not None:
                uploaded_assets.append(execution.ocr_result.stored_text_asset)

        packet_status, next_stage = _resolve_packet_handoff(
            processed_statuses={
                execution.document.document_id: execution.status
                for execution in pending_executions
            },
            snapshot=snapshot,
        )
        _persist_ocr_handoff(
            packet_id=packet_id,
            packet_status=packet_status,
            pending_executions=tuple(pending_executions),
            settings=settings,
        )
    except Exception:
        _cleanup_uploaded_assets(tuple(uploaded_assets), settings)
        raise

    return PacketOcrExecutionResponse(
        executed_document_count=len(pending_executions),
        next_stage=next_stage,
        packet_id=packet_id,
        processed_documents=tuple(
            PacketOcrExecutionDocumentResult(
                classification_result_id=(
                    execution.classification_result.classification_result_id
                    if execution.classification_result is not None
                    else None
                ),
                document_id=execution.document.document_id,
                extraction_job_id=execution.extraction_job_id,
                extraction_strategy=execution.extraction_strategy,
                ocr_confidence=execution.ocr_result.ocr_confidence,
                ocr_job_id=execution.ocr_job_id,
                ocr_result_id=execution.ocr_result_id,
                packet_id=packet_id,
                page_count=execution.ocr_result.page_count,
                provider=execution.ocr_result.provider,
                review_task_id=execution.review_task_id,
                status=execution.status,
                text_storage_uri=(
                    execution.ocr_result.stored_text_asset.storage_uri
                    if execution.ocr_result.stored_text_asset is not None
                    else None
                ),
            )
            for execution in pending_executions
        ),
        skipped_document_ids=tuple(skipped_document_ids),
        status=packet_status,
    )