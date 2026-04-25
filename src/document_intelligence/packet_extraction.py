"""Packet-level extraction execution, matching, and review handoff helpers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from document_intelligence.account_matching import match_document_to_account
from document_intelligence.extraction import (
    apply_extraction_strategy,
    build_match_request,
    extract_document_from_ocr,
    select_extraction_strategy,
)
from document_intelligence.models import (
    AccountMatchResult,
    ClassificationResultRecord,
    DocumentAnalysisResult,
    DocumentAssetRecord,
    DocumentIngestionRequest,
    ExtractionStrategySelection,
    IssuerCategory,
    ManagedDocumentTypeDefinitionRecord,
    OcrResultRecord,
    PacketDocumentRecord,
    PacketEventRecord,
    PacketExtractionExecutionDocumentResult,
    PacketExtractionExecutionResponse,
    PacketStatus,
    PacketWorkspaceSnapshot,
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStageName,
    PromptProfileId,
    ReviewDecision,
    ReviewTaskPriority,
)
from document_intelligence.operator_state import SqlOperatorStateRepository
from document_intelligence.orchestration import normalize_request
from document_intelligence.review_queue import should_route_to_manual_review
from document_intelligence.safety import attach_content_controls
from document_intelligence.settings import AppSettings
from document_intelligence.utils.blob_storage import download_blob_text
from document_intelligence.utils.sql import open_sql_connection


class PacketExtractionConfigurationError(RuntimeError):
    """Raised when packet extraction execution cannot run."""


@dataclass(frozen=True)
class _ResolvedExtractionOutcome:
    """Resolved extraction, matching, and review data for one document."""

    account_match: AccountMatchResult
    analysis_result: DocumentAnalysisResult
    review_decision: ReviewDecision
    review_task_id: str | None
    status: PacketStatus


@dataclass(frozen=True)
class _PendingExtractionExecution:
    """One queued extraction job ready for persistence."""

    classification_result: ClassificationResultRecord | None
    document: PacketDocumentRecord
    extraction_job_id: str
    extraction_result_id: str
    extraction_strategy: ExtractionStrategySelection
    match_run_id: str
    ocr_result: OcrResultRecord
    recommendation_job_id: str | None
    resolved_outcome: _ResolvedExtractionOutcome


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


def _select_latest_ocr_results_by_document(
    ocr_results: tuple[OcrResultRecord, ...],
) -> dict[str, OcrResultRecord]:
    """Return the latest persisted OCR result for each document."""

    latest_results: dict[str, OcrResultRecord] = {}
    for result in ocr_results:
        current_result = latest_results.get(result.document_id)
        if (
            current_result is None
            or result.created_at_utc >= current_result.created_at_utc
        ):
            latest_results[result.document_id] = result

    return latest_results


def _select_latest_extraction_queue_events_by_document(
    packet_events: tuple[PacketEventRecord, ...],
) -> dict[str, PacketEventRecord]:
    """Return the latest extraction-queue event for each document."""

    latest_events: dict[str, PacketEventRecord] = {}
    for event in packet_events:
        if (
            event.document_id is None
            or event.event_type != "document.extraction.queued"
        ):
            continue

        current_event = latest_events.get(event.document_id)
        if (
            current_event is None
            or event.created_at_utc >= current_event.created_at_utc
        ):
            latest_events[event.document_id] = event

    return latest_events


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


def _resolve_persisted_extraction_strategy(
    queued_event: PacketEventRecord | None,
) -> ExtractionStrategySelection | None:
    """Return the persisted extraction strategy embedded in the queue event."""

    if queued_event is None or queued_event.event_payload is None:
        return None

    raw_strategy = queued_event.event_payload.get("strategy")
    if not isinstance(raw_strategy, dict):
        return None

    return ExtractionStrategySelection.model_validate(raw_strategy)


def _resolve_extraction_strategy(
    *,
    classification_result: ClassificationResultRecord | None,
    document_type_definitions: tuple[ManagedDocumentTypeDefinitionRecord, ...],
    queued_event: PacketEventRecord | None,
    request: DocumentIngestionRequest,
    settings: AppSettings,
) -> ExtractionStrategySelection:
    """Resolve the persisted extraction strategy for one queued document."""

    persisted_strategy = _resolve_persisted_extraction_strategy(queued_event)
    if persisted_strategy is not None:
        return persisted_strategy

    return select_extraction_strategy(
        classification_result=classification_result,
        document_type_definitions=document_type_definitions,
        request=request,
        settings=settings,
    )


def _resolve_ocr_text(
    *,
    document_text: str | None,
    ocr_result: OcrResultRecord,
    settings: AppSettings,
) -> str:
    """Resolve the best available OCR text for downstream extraction."""

    if ocr_result.text_storage_uri and settings.storage_connection_string:
        try:
            return download_blob_text(
                source_uri=ocr_result.text_storage_uri,
                storage_connection_string=settings.storage_connection_string,
            )
        except Exception as error:
            logging.warning(
                "Falling back from persisted OCR text for %s: %s",
                ocr_result.ocr_result_id,
                error,
            )

    if document_text:
        return document_text

    return ocr_result.text_excerpt or ""


def _enrich_request_for_review(
    request: DocumentIngestionRequest,
    *,
    account_match: AccountMatchResult,
    analysis_result: DocumentAnalysisResult,
) -> DocumentIngestionRequest:
    """Project extracted fields and the resolved account state onto the request."""

    issuer_category = request.issuer_category
    if issuer_category == IssuerCategory.UNKNOWN:
        issuer_category = analysis_result.prompt_profile.issuer_category

    extraction_request = request.model_copy(
        update={
            "extracted_fields": analysis_result.extracted_fields,
            "issuer_category": issuer_category,
        }
    )
    return build_match_request(extraction_request, account_match)


def _resolve_review_notes_summary(review_decision: ReviewDecision) -> str:
    """Build the review-task summary for manual-review routing."""

    reason_codes = ", ".join(reason.value for reason in review_decision.reasons)
    return f"Extraction flagged the document for manual review: {reason_codes}."


def _resolve_target_status(review_decision: ReviewDecision) -> PacketStatus:
    """Return the document status implied by the review decision."""

    if review_decision.requires_manual_review:
        return PacketStatus.AWAITING_REVIEW

    return PacketStatus.READY_FOR_RECOMMENDATION


def _resolve_extraction_outcome(
    *,
    document: PacketDocumentRecord,
    ocr_result: OcrResultRecord,
    request: DocumentIngestionRequest,
    strategy: ExtractionStrategySelection,
    settings: AppSettings,
) -> _ResolvedExtractionOutcome:
    """Resolve extraction, matching, and review routing for one document."""

    applied_request = apply_extraction_strategy(request, strategy)
    ocr_text = _resolve_ocr_text(
        document_text=document.document_text,
        ocr_result=ocr_result,
        settings=settings,
    )
    required_fields = strategy.required_fields or settings.required_fields
    analysis_result = extract_document_from_ocr(
        applied_request,
        settings,
        ocr_confidence=ocr_result.ocr_confidence,
        ocr_provider=ocr_result.provider,
        ocr_text=ocr_text,
        page_count=ocr_result.page_count,
        required_fields=required_fields,
    )
    account_match = match_document_to_account(
        applied_request,
        analysis_result,
        settings,
        matching_path=strategy.matching_path,
    )
    review_request = _enrich_request_for_review(
        applied_request,
        account_match=account_match,
        analysis_result=analysis_result,
    )
    review_decision = should_route_to_manual_review(
        review_request,
        required_fields,
        settings.low_confidence_threshold,
    )
    review_task_id = None
    if review_decision.requires_manual_review:
        review_task_id = f"task_{uuid4().hex}"

    return _ResolvedExtractionOutcome(
        account_match=account_match,
        analysis_result=analysis_result,
        review_decision=review_decision,
        review_task_id=review_task_id,
        status=_resolve_target_status(review_decision),
    )


def _build_pending_extraction_execution(
    *,
    asset_by_document_id: dict[str, DocumentAssetRecord],
    classification_result: ClassificationResultRecord | None,
    document: PacketDocumentRecord,
    document_type_definitions: tuple[ManagedDocumentTypeDefinitionRecord, ...],
    ocr_result: OcrResultRecord,
    packet_source_uri: str,
    queued_event: PacketEventRecord | None,
    latest_job: ProcessingJobRecord,
    settings: AppSettings,
) -> _PendingExtractionExecution:
    """Resolve one queued extraction execution before persistence."""

    request = _build_document_request(
        asset_by_document_id=asset_by_document_id,
        document=document,
        packet_source_uri=packet_source_uri,
    )
    strategy = _resolve_extraction_strategy(
        classification_result=classification_result,
        document_type_definitions=document_type_definitions,
        queued_event=queued_event,
        request=request,
        settings=settings,
    )
    resolved_outcome = _resolve_extraction_outcome(
        document=document,
        ocr_result=ocr_result,
        request=request,
        strategy=strategy,
        settings=settings,
    )
    return _PendingExtractionExecution(
        classification_result=classification_result,
        document=document,
        extraction_job_id=latest_job.job_id,
        extraction_result_id=f"ext_{uuid4().hex}",
        extraction_strategy=strategy,
        match_run_id=f"match_{uuid4().hex}",
        ocr_result=ocr_result,
        recommendation_job_id=(
            f"job_{uuid4().hex}"
            if resolved_outcome.status == PacketStatus.READY_FOR_RECOMMENDATION
            else None
        ),
        resolved_outcome=resolved_outcome,
    )


def _resolve_packet_handoff(
    *,
    processed_statuses: dict[str, PacketStatus],
    snapshot: PacketWorkspaceSnapshot,
) -> tuple[PacketStatus, ProcessingStageName]:
    """Return the packet status after extraction has completed."""

    latest_jobs = _select_latest_jobs_by_document(snapshot.processing_jobs)
    effective_statuses = {
        document.document_id: document.status for document in snapshot.documents
    }
    effective_statuses.update(processed_statuses)

    if any(
        status == PacketStatus.QUARANTINED
        for status in effective_statuses.values()
    ):
        return PacketStatus.QUARANTINED, ProcessingStageName.QUARANTINE

    if any(
        latest_jobs.get(document.document_id) is not None
        and latest_jobs[document.document_id].stage_name
        == ProcessingStageName.EXTRACTION
        and latest_jobs[document.document_id].status != ProcessingJobStatus.SUCCEEDED
        and document.document_id not in processed_statuses
        for document in snapshot.documents
    ):
        return snapshot.packet.status, ProcessingStageName.EXTRACTION

    if any(
        status == PacketStatus.AWAITING_REVIEW
        for status in effective_statuses.values()
    ):
        return PacketStatus.AWAITING_REVIEW, ProcessingStageName.REVIEW

    if processed_statuses:
        return PacketStatus.READY_FOR_RECOMMENDATION, ProcessingStageName.RECOMMENDATION

    return snapshot.packet.status, ProcessingStageName.RECOMMENDATION


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


def _update_document_state(
    cursor: Any,
    execution: _PendingExtractionExecution,
) -> None:
    """Persist the latest packet-document state after extraction finishes."""

    prompt_profile_id = (
        execution.resolved_outcome.analysis_result.prompt_profile.primary_profile_id
    )
    account_candidates = tuple(
        candidate.account_id
        for candidate in execution.resolved_outcome.account_match.candidates
    )
    if execution.resolved_outcome.account_match.selected_account_id is not None:
        account_candidates = (
            execution.resolved_outcome.account_match.selected_account_id,
        )

    cursor.execute(
        """
        UPDATE dbo.PacketDocuments
        SET
            status = %s,
            requestedPromptProfileId = %s,
            accountCandidatesJson = %s,
            issuerCategory = %s,
            updatedAtUtc = SYSUTCDATETIME()
        WHERE documentId = %s
        """,
        (
            execution.resolved_outcome.status.value,
            _serialize_prompt_profile_id(prompt_profile_id),
            json.dumps(list(account_candidates)),
            execution.resolved_outcome.analysis_result.prompt_profile.issuer_category.value,
            execution.document.document_id,
        ),
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


def _build_extraction_result_payload(
    execution: _PendingExtractionExecution,
) -> dict[str, Any]:
    """Build the structured extraction payload persisted to SQL."""

    return attach_content_controls(
        {
            "accountMatch": execution.resolved_outcome.account_match.model_dump(
                mode="json"
            ),
            "classificationResultId": (
                execution.classification_result.classification_result_id
                if execution.classification_result is not None
                else None
            ),
            "matchRunId": execution.match_run_id,
            "ocrResultId": execution.ocr_result.ocr_result_id,
            "promptProfile": (
                execution.resolved_outcome.analysis_result.prompt_profile.model_dump(
                    mode="json"
                )
            ),
            "reviewDecision": execution.resolved_outcome.review_decision.model_dump(
                mode="json"
            ),
            "reviewTaskId": execution.resolved_outcome.review_task_id,
            "strategy": execution.extraction_strategy.model_dump(mode="json"),
            "warnings": list(execution.resolved_outcome.analysis_result.warnings),
            "extractedFields": [
                field.model_dump(mode="json")
                for field in execution.resolved_outcome.analysis_result.extracted_fields
            ],
        },
        retention_class="extracted_content",
        contains_sensitive_content=True,
    )


def _insert_extraction_result(
    cursor: Any,
    *,
    execution: _PendingExtractionExecution,
    packet_id: str,
) -> None:
    """Persist one extraction result row."""

    cursor.execute(
        """
        INSERT INTO dbo.ExtractionResults (
            extractionResultId,
            packetId,
            documentId,
            provider,
            modelName,
            documentType,
            promptProfileId,
            summary,
            resultJson,
            createdAtUtc
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, SYSUTCDATETIME())
        """,
        (
            execution.extraction_result_id,
            packet_id,
            execution.document.document_id,
            execution.resolved_outcome.analysis_result.provider,
            execution.resolved_outcome.analysis_result.model_name,
            execution.resolved_outcome.analysis_result.document_type,
            _serialize_prompt_profile_id(
                execution.resolved_outcome.analysis_result.prompt_profile.primary_profile_id
            ),
            execution.resolved_outcome.analysis_result.summary,
            json.dumps(_build_extraction_result_payload(execution)),
        ),
    )


def _insert_account_match_run(
    cursor: Any,
    *,
    execution: _PendingExtractionExecution,
    packet_id: str,
) -> None:
    """Persist one account-match run and its ranked candidates."""

    account_match = execution.resolved_outcome.account_match
    cursor.execute(
        """
        INSERT INTO dbo.AccountMatchRuns (
            matchRunId,
            packetId,
            documentId,
            status,
            selectedAccountId,
            rationale,
            createdAtUtc
        )
        VALUES (%s, %s, %s, %s, %s, %s, SYSUTCDATETIME())
        """,
        (
            execution.match_run_id,
            packet_id,
            execution.document.document_id,
            account_match.status.value,
            account_match.selected_account_id,
            account_match.rationale,
        ),
    )
    for rank_order, candidate in enumerate(account_match.candidates, start=1):
        cursor.execute(
            """
            INSERT INTO dbo.AccountMatchCandidates (
                matchCandidateId,
                matchRunId,
                accountId,
                accountNumber,
                debtorName,
                issuerName,
                matchedOnJson,
                score,
                rankOrder,
                createdAtUtc
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, SYSUTCDATETIME())
            """,
            (
                f"cand_{uuid4().hex}",
                execution.match_run_id,
                candidate.account_id,
                candidate.account_number,
                candidate.debtor_name,
                candidate.issuer_name,
                json.dumps(list(candidate.matched_on)),
                candidate.score,
                rank_order,
            ),
        )


def _insert_review_task(
    cursor: Any,
    execution: _PendingExtractionExecution,
    packet_id: str,
) -> None:
    """Persist one extraction-driven review task when required."""

    review_task_id = execution.resolved_outcome.review_task_id
    if review_task_id is None:
        return

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
            %s,
            %s,
            %s,
            NULL,
            SYSUTCDATETIME(),
            SYSUTCDATETIME()
        )
        """,
        (
            review_task_id,
            packet_id,
            execution.document.document_id,
            PacketStatus.AWAITING_REVIEW.value,
            ReviewTaskPriority.NORMAL.value,
            execution.resolved_outcome.account_match.selected_account_id,
            json.dumps(
                [
                    reason.value
                    for reason in execution.resolved_outcome.review_decision.reasons
                ]
            ),
            _resolve_review_notes_summary(
                execution.resolved_outcome.review_decision
            ),
        ),
    )


def _insert_recommendation_job(
    cursor: Any,
    execution: _PendingExtractionExecution,
    packet_id: str,
) -> None:
    """Queue one recommendation job for a review-ready document."""

    recommendation_job_id = execution.recommendation_job_id
    if recommendation_job_id is None:
        return

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
            recommendation_job_id,
            packet_id,
            execution.document.document_id,
            ProcessingStageName.RECOMMENDATION.value,
            ProcessingJobStatus.QUEUED.value,
        ),
    )


def _build_extraction_started_event_payload(
    execution: _PendingExtractionExecution,
) -> dict[str, Any]:
    """Return the event payload for a started extraction job."""

    return {
        "classificationResultId": (
            execution.classification_result.classification_result_id
            if execution.classification_result is not None
            else None
        ),
        "extractionJobId": execution.extraction_job_id,
        "ocrResultId": execution.ocr_result.ocr_result_id,
        "stageName": ProcessingStageName.EXTRACTION.value,
        "status": ProcessingJobStatus.RUNNING.value,
        "strategy": execution.extraction_strategy.model_dump(mode="json"),
    }


def _build_extraction_completed_event_payload(
    execution: _PendingExtractionExecution,
) -> dict[str, Any]:
    """Return the event payload for a completed extraction job."""

    return {
        "documentType": execution.resolved_outcome.analysis_result.document_type,
        "extractionJobId": execution.extraction_job_id,
        "extractionResultId": execution.extraction_result_id,
        "ocrResultId": execution.ocr_result.ocr_result_id,
        "promptProfileId": _serialize_prompt_profile_id(
            execution.resolved_outcome.analysis_result.prompt_profile.primary_profile_id
        ),
        "provider": execution.resolved_outcome.analysis_result.provider,
        "summary": execution.resolved_outcome.analysis_result.summary,
        "warnings": list(execution.resolved_outcome.analysis_result.warnings),
    }


def _build_matching_completed_event_payload(
    execution: _PendingExtractionExecution,
) -> dict[str, Any]:
    """Return the event payload for a completed account-match run."""

    account_match = execution.resolved_outcome.account_match
    return {
        "candidateCount": len(account_match.candidates),
        "matchRunId": execution.match_run_id,
        "matchingPath": execution.extraction_strategy.matching_path,
        "rationale": account_match.rationale,
        "selectedAccountId": account_match.selected_account_id,
        "status": account_match.status.value,
    }


def _build_review_created_event_payload(
    execution: _PendingExtractionExecution,
) -> dict[str, Any]:
    """Return the event payload for a newly created review task."""

    return {
        "reasonCodes": [
            reason.value
            for reason in execution.resolved_outcome.review_decision.reasons
        ],
        "reviewTaskId": execution.resolved_outcome.review_task_id,
        "selectedAccountId": (
            execution.resolved_outcome.account_match.selected_account_id
        ),
        "status": PacketStatus.AWAITING_REVIEW.value,
    }


def _build_ready_for_recommendation_event_payload(
    execution: _PendingExtractionExecution,
) -> dict[str, Any]:
    """Return the event payload for a review-ready document."""

    return {
        "matchRunId": execution.match_run_id,
        "recommendationJobId": execution.recommendation_job_id,
        "selectedAccountId": (
            execution.resolved_outcome.account_match.selected_account_id
        ),
        "status": PacketStatus.READY_FOR_RECOMMENDATION.value,
    }


def _persist_document_extraction_execution(
    cursor: Any,
    *,
    execution: _PendingExtractionExecution,
    packet_id: str,
) -> None:
    """Persist extraction completion, matching, and review routing."""

    _set_job_running(cursor, execution.extraction_job_id)
    _insert_packet_event(
        cursor,
        document_id=execution.document.document_id,
        event_payload=_build_extraction_started_event_payload(execution),
        event_type="document.extraction.started",
        packet_id=packet_id,
    )
    _insert_extraction_result(cursor, execution=execution, packet_id=packet_id)
    _insert_account_match_run(cursor, execution=execution, packet_id=packet_id)
    _insert_review_task(cursor, execution, packet_id)
    _insert_recommendation_job(cursor, execution, packet_id)
    _set_job_succeeded(cursor, execution.extraction_job_id)
    _update_document_state(cursor, execution)
    _insert_packet_event(
        cursor,
        document_id=execution.document.document_id,
        event_payload=_build_extraction_completed_event_payload(execution),
        event_type="document.extraction.completed",
        packet_id=packet_id,
    )
    _insert_packet_event(
        cursor,
        document_id=execution.document.document_id,
        event_payload=_build_matching_completed_event_payload(execution),
        event_type="document.matching.completed",
        packet_id=packet_id,
    )
    if execution.resolved_outcome.review_task_id is not None:
        _insert_packet_event(
            cursor,
            document_id=execution.document.document_id,
            event_payload=_build_review_created_event_payload(execution),
            event_type="document.review_task.created",
            packet_id=packet_id,
        )
        return

    _insert_packet_event(
        cursor,
        document_id=execution.document.document_id,
        event_payload=_build_ready_for_recommendation_event_payload(execution),
        event_type="document.ready_for_recommendation",
        packet_id=packet_id,
    )


def _persist_extraction_execution(
    *,
    packet_id: str,
    packet_status: PacketStatus,
    pending_executions: tuple[_PendingExtractionExecution, ...],
    settings: AppSettings,
) -> None:
    """Persist extraction completion for the packet."""

    if not pending_executions:
        return

    first_packet_id = pending_executions[0].document.packet_id
    if packet_id != first_packet_id:
        raise RuntimeError(
            "Pending extraction packet ids do not match the target packet."
        )

    connection_string = settings.sql_connection_string
    if not connection_string:
        raise PacketExtractionConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    with open_sql_connection(connection_string, autocommit=False) as connection:
        try:
            with connection.cursor() as cursor:
                for execution in pending_executions:
                    _persist_document_extraction_execution(
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
                            else ProcessingStageName.RECOMMENDATION.value
                            if packet_status == PacketStatus.READY_FOR_RECOMMENDATION
                            else ProcessingStageName.EXTRACTION.value
                        ),
                        "status": packet_status.value,
                    },
                    event_type="packet.extraction.executed",
                    packet_id=packet_id,
                )

            connection.commit()
        except Exception:
            connection.rollback()
            raise


def execute_packet_extraction_stage(
    packet_id: str,
    settings: AppSettings,
) -> PacketExtractionExecutionResponse:
    """Execute queued packet extraction work and persist matching outcomes."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        raise PacketExtractionConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    snapshot = repository.get_packet_workspace_snapshot(packet_id)
    document_type_definitions = repository.list_document_type_definitions()
    latest_jobs = _select_latest_jobs_by_document(snapshot.processing_jobs)
    latest_ocr_results = _select_latest_ocr_results_by_document(snapshot.ocr_results)
    latest_queue_events = _select_latest_extraction_queue_events_by_document(
        snapshot.packet_events
    )
    asset_by_document_id = _select_primary_asset_by_document(snapshot.document_assets)
    classification_results_by_document = (
        _select_latest_classification_results_by_document(
            snapshot.classification_results
        )
    )
    pending_executions: list[_PendingExtractionExecution] = []
    skipped_document_ids: list[str] = []

    for document in snapshot.documents:
        latest_job = latest_jobs.get(document.document_id)
        ocr_result = latest_ocr_results.get(document.document_id)
        if latest_job is None or ocr_result is None:
            skipped_document_ids.append(document.document_id)
            continue

        if latest_job.stage_name != ProcessingStageName.EXTRACTION:
            skipped_document_ids.append(document.document_id)
            continue

        if latest_job.status != ProcessingJobStatus.QUEUED:
            skipped_document_ids.append(document.document_id)
            continue

        if document.status != PacketStatus.EXTRACTING:
            skipped_document_ids.append(document.document_id)
            continue

        pending_executions.append(
            _build_pending_extraction_execution(
                asset_by_document_id=asset_by_document_id,
                classification_result=classification_results_by_document.get(
                    document.document_id
                ),
                document=document,
                document_type_definitions=document_type_definitions,
                ocr_result=ocr_result,
                packet_source_uri=(
                    snapshot.packet.source_uri
                    or f"manual://packets/{snapshot.packet.packet_id}"
                ),
                queued_event=latest_queue_events.get(document.document_id),
                latest_job=latest_job,
                settings=settings,
            )
        )

    packet_status, next_stage = _resolve_packet_handoff(
        processed_statuses={
            execution.document.document_id: execution.resolved_outcome.status
            for execution in pending_executions
        },
        snapshot=snapshot,
    )
    _persist_extraction_execution(
        packet_id=packet_id,
        packet_status=packet_status,
        pending_executions=tuple(pending_executions),
        settings=settings,
    )

    return PacketExtractionExecutionResponse(
        executed_document_count=len(pending_executions),
        next_stage=next_stage,
        packet_id=packet_id,
        processed_documents=tuple(
            PacketExtractionExecutionDocumentResult(
                account_match=execution.resolved_outcome.account_match,
                classification_result_id=(
                    execution.classification_result.classification_result_id
                    if execution.classification_result is not None
                    else None
                ),
                document_id=execution.document.document_id,
                extraction_job_id=execution.extraction_job_id,
                extraction_result_id=execution.extraction_result_id,
                extraction_strategy=execution.extraction_strategy,
                match_run_id=execution.match_run_id,
                packet_id=packet_id,
                prompt_profile_id=(
                    execution.resolved_outcome.analysis_result.prompt_profile.primary_profile_id
                ),
                recommendation_job_id=execution.recommendation_job_id,
                review_decision=execution.resolved_outcome.review_decision,
                review_task_id=execution.resolved_outcome.review_task_id,
                selected_account_id=(
                    execution.resolved_outcome.account_match.selected_account_id
                ),
                status=execution.resolved_outcome.status,
            )
            for execution in pending_executions
        ),
        skipped_document_ids=tuple(skipped_document_ids),
        status=packet_status,
    )
