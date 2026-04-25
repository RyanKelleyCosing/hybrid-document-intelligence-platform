"""Packet-level review workspace helpers for the protected operator shell."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from document_intelligence.models import (
    AccountMatchRunRecord,
    AuditEventRecord,
    ExtractionFieldChangeRecord,
    ExtractionFieldEditInput,
    ExtractionResultRecord,
    OperatorNoteRecord,
    PacketReviewAssignmentRequest,
    PacketReviewAssignmentResponse,
    PacketReviewDecisionRequest,
    PacketReviewDecisionResponse,
    PacketReviewExtractionEditRequest,
    PacketReviewExtractionEditResponse,
    PacketReviewNoteRequest,
    PacketReviewNoteResponse,
    PacketReviewTaskCreateRequest,
    PacketReviewTaskCreateResponse,
    PacketDocumentRecord,
    PacketStatus,
    PacketWorkspaceSnapshot,
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStageName,
    ReviewDecisionRecord,
    ReviewStatus,
    ReviewTaskPriority,
    ReviewTaskRecord,
)
from document_intelligence.operator_state import SqlOperatorStateRepository
from document_intelligence.safety import (
    attach_content_controls,
    mask_history_payload,
    mask_sensitive_text,
)
from document_intelligence.settings import AppSettings
from document_intelligence.utils.sql import open_sql_connection


class PacketReviewConfigurationError(RuntimeError):
    """Raised when packet review decisions cannot run."""


class PacketReviewConflictError(RuntimeError):
    """Raised when a review task changed before a decision was saved."""


@dataclass(frozen=True)
class _ReviewDecisionPlan:
    """Resolved persistence plan for one SQL-backed review decision."""

    decision_record: ReviewDecisionRecord
    document_status: PacketStatus
    note_record: OperatorNoteRecord | None
    packet_status: PacketStatus
    queued_recommendation_job_id: str | None
    review_task: ReviewTaskRecord
    review_task_status: PacketStatus
    selected_account_id: str | None


@dataclass(frozen=True)
class _ExtractionEditPlan:
    """Resolved persistence plan for one SQL-backed extraction edit save."""

    audit_event: AuditEventRecord
    changed_fields: tuple[ExtractionFieldChangeRecord, ...]
    extraction_result: ExtractionResultRecord
    review_task: ReviewTaskRecord


def _normalize_optional_text(value: str | None) -> str | None:
    """Return a stripped string value when one is present."""

    if value is None:
        return None

    normalized_value = value.strip()
    return normalized_value or None


def _normalize_field_key(value: str) -> str:
    """Return a normalized lookup key for extracted field names."""

    return value.strip().casefold()


def _decode_expected_row_version(row_version: str) -> bytes:
    """Decode one review-task row-version token from the client."""

    normalized_row_version = row_version.strip().removeprefix("0x")
    if not normalized_row_version:
        raise ValueError("expected_row_version is required")

    if len(normalized_row_version) % 2 != 0:
        raise ValueError(
            "expected_row_version must contain an even number of hex characters"
        )

    try:
        return bytes.fromhex(normalized_row_version)
    except ValueError as error:
        raise ValueError(
            "expected_row_version must be a valid hex row-version token"
        ) from error


def _assert_review_task_is_current(
    request: (
        PacketReviewAssignmentRequest
        | PacketReviewDecisionRequest
        | PacketReviewExtractionEditRequest
        | PacketReviewNoteRequest
    ),
    review_task: ReviewTaskRecord,
) -> bytes:
    """Ensure the client is acting on the latest persisted review-task version."""

    expected_row_version = _decode_expected_row_version(request.expected_row_version)
    current_row_version = review_task.row_version
    if current_row_version is None:
        raise PacketReviewConflictError(
            f"Review task '{review_task.review_task_id}' is missing a row-version token. Refresh the workspace and try again."
        )

    if expected_row_version.hex() != current_row_version.lower():
        raise PacketReviewConflictError(
            f"Review task '{review_task.review_task_id}' changed after it was loaded. Refresh the workspace and try again."
        )

    return expected_row_version


def _assert_review_task_actor_owns_task(
    review_task: ReviewTaskRecord,
    *,
    actor_email: str | None,
) -> None:
    """Reject mutations from operators who do not own the review task."""

    assigned_user_email = _normalize_optional_text(review_task.assigned_user_email)
    if assigned_user_email is None:
        return

    normalized_actor_email = _normalize_optional_text(actor_email)
    if normalized_actor_email is None:
        raise PacketReviewConflictError(
            f"Review task '{review_task.review_task_id}' is assigned to {assigned_user_email}. Refresh the workspace before acting on it."
        )

    if normalized_actor_email.casefold() != assigned_user_email.casefold():
        raise PacketReviewConflictError(
            f"Review task '{review_task.review_task_id}' is assigned to {assigned_user_email}, not {normalized_actor_email}. Refresh the workspace before acting on it."
        )


def _assert_reviewer_owns_task(
    request: PacketReviewDecisionRequest,
    review_task: ReviewTaskRecord,
) -> None:
    """Reject decisions from operators who do not own the review task."""

    _assert_review_task_actor_owns_task(
        review_task,
        actor_email=request.decided_by_email,
    )


def _select_latest_account_match_runs_by_document(
    account_match_runs: tuple[AccountMatchRunRecord, ...],
) -> dict[str, AccountMatchRunRecord]:
    """Return the latest persisted account-match run for each document."""

    latest_runs: dict[str, AccountMatchRunRecord] = {}
    for run in account_match_runs:
        current_run = latest_runs.get(run.document_id)
        if current_run is None or run.created_at_utc >= current_run.created_at_utc:
            latest_runs[run.document_id] = run

    return latest_runs


def _select_latest_extraction_results_by_document(
    extraction_results: tuple[ExtractionResultRecord, ...],
) -> dict[str, ExtractionResultRecord]:
    """Return the latest extraction result for each document."""

    latest_results: dict[str, ExtractionResultRecord] = {}
    for result in extraction_results:
        current_result = latest_results.get(result.document_id)
        if (
            current_result is None
            or result.created_at_utc >= current_result.created_at_utc
        ):
            latest_results[result.document_id] = result

    return latest_results


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


def _resolve_review_task(
    snapshot: PacketWorkspaceSnapshot,
    review_task_id: str,
) -> ReviewTaskRecord:
    """Return the requested review task from the packet workspace snapshot."""

    for review_task in snapshot.review_tasks:
        if review_task.review_task_id == review_task_id:
            return review_task

    raise RuntimeError(f"Review task '{review_task_id}' could not be loaded.")


def _resolve_packet_document(
    snapshot: PacketWorkspaceSnapshot,
    document_id: str,
) -> PacketDocumentRecord:
    """Return one packet document from the loaded packet workspace snapshot."""

    for document in snapshot.documents:
        if document.document_id == document_id:
            return document

    raise RuntimeError(f"Document '{document_id}' could not be loaded.")


def _document_has_review_task(
    snapshot: PacketWorkspaceSnapshot,
    document_id: str,
) -> bool:
    """Return whether a packet document already has a persisted review task."""

    return any(
        review_task.document_id == document_id
        for review_task in snapshot.review_tasks
    )


def _review_task_has_decision(
    snapshot: PacketWorkspaceSnapshot,
    review_task_id: str,
) -> bool:
    """Return whether a review task already has a persisted decision."""

    return any(
        review_decision.review_task_id == review_task_id
        for review_decision in snapshot.review_decisions
    )


def _resolve_packet_status_after_task_create(
    snapshot: PacketWorkspaceSnapshot,
) -> PacketStatus:
    """Return the packet status after creating one review task from the workspace."""

    if snapshot.packet.status in {PacketStatus.BLOCKED, PacketStatus.AWAITING_REVIEW}:
        return snapshot.packet.status

    return PacketStatus.AWAITING_REVIEW


def _resolve_latest_extraction_result(
    review_task: ReviewTaskRecord,
    snapshot: PacketWorkspaceSnapshot,
) -> ExtractionResultRecord:
    """Return the latest extraction result available for one review task."""

    latest_extraction_results = _select_latest_extraction_results_by_document(
        snapshot.extraction_results
    )
    extraction_result = latest_extraction_results.get(review_task.document_id)
    if extraction_result is None:
        raise RuntimeError(
            "Only documents with a stored extraction result can accept inline "
            "extraction edits from the review workspace."
        )

    return extraction_result


def create_packet_review_task(
    packet_id: str,
    document_id: str,
    request: PacketReviewTaskCreateRequest,
    settings: AppSettings,
) -> PacketReviewTaskCreateResponse:
    """Persist one new review task for a packet document from the workspace."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        raise PacketReviewConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    snapshot = repository.get_packet_workspace_snapshot(packet_id)
    document = _resolve_packet_document(snapshot, document_id)
    if document.packet_id != packet_id:
        raise RuntimeError(
            f"Document '{document_id}' does not belong to packet '{packet_id}'."
        )

    if _document_has_review_task(snapshot, document_id):
        raise PacketReviewConflictError(
            f"Document '{document_id}' already has a persisted review task."
        )

    review_task_id = f"task_{uuid4().hex}"
    assigned_user_email = _normalize_optional_text(request.assigned_user_email)
    assigned_user_id = _normalize_optional_text(request.assigned_user_id)
    notes_summary = _normalize_optional_text(request.notes_summary)
    selected_account_id = _normalize_optional_text(request.selected_account_id)
    packet_status = _resolve_packet_status_after_task_create(snapshot)
    review_task_payload = {
        "assignedUserEmail": assigned_user_email,
        "assignedUserId": assigned_user_id,
        "documentId": document.document_id,
        "notesSummary": notes_summary,
        "priority": request.priority.value,
        "reasonCodes": [],
        "reviewTaskId": review_task_id,
        "selectedAccountId": selected_account_id,
        "stageName": ProcessingStageName.REVIEW.value,
        "status": PacketStatus.AWAITING_REVIEW.value,
        "summary": notes_summary,
    }
    audit_event = AuditEventRecord(
        actor_email=request.created_by_email,
        actor_user_id=request.created_by_user_id,
        audit_event_id=1,
        created_at_utc=datetime.now(UTC),
        document_id=document_id,
        event_payload=(
            mask_history_payload(
                review_task_payload,
                retention_class="review_history",
            )
            if settings.mask_sensitive_history
            else review_task_payload
        ),
        event_type="review.task.created",
        packet_id=packet_id,
        review_task_id=review_task_id,
    )
    connection_string = settings.sql_connection_string
    if not connection_string:
        raise PacketReviewConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    with open_sql_connection(connection_string, autocommit=False) as connection:
        try:
            with connection.cursor() as cursor:
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
                        %s,
                        %s,
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
                        document_id,
                        assigned_user_id,
                        assigned_user_email,
                        PacketStatus.AWAITING_REVIEW.value,
                        request.priority.value,
                        selected_account_id,
                        json.dumps([]),
                        notes_summary,
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
                    (
                        PacketStatus.AWAITING_REVIEW.value,
                        document_id,
                    ),
                )
                cursor.execute(
                    """
                    UPDATE dbo.Packets
                    SET
                        status = %s,
                        updatedAtUtc = SYSUTCDATETIME()
                    WHERE packetId = %s
                    """,
                    (
                        packet_status.value,
                        packet_id,
                    ),
                )
                _insert_packet_event(
                    cursor,
                    document_id=document_id,
                    event_payload=review_task_payload,
                    event_type="document.review_task.created",
                    packet_id=packet_id,
                )
                _insert_audit_event(cursor, event=audit_event)

            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return PacketReviewTaskCreateResponse(
        document_id=document_id,
        packet_id=packet_id,
        review_task_id=review_task_id,
    )


def _resolve_field_confidence(value: object) -> float | None:
    """Return one optional extracted-field confidence value."""

    if isinstance(value, (float, int)):
        return float(value)

    return None


def _build_updated_extraction_payload(
    extraction_result: ExtractionResultRecord,
    field_edits: tuple[ExtractionFieldEditInput, ...],
) -> tuple[dict[str, Any], tuple[ExtractionFieldChangeRecord, ...]]:
    """Apply requested field edits onto the latest extraction payload."""

    result_payload = deepcopy(extraction_result.result_payload)
    raw_fields = result_payload.get("extractedFields")
    if not isinstance(raw_fields, list) or len(raw_fields) == 0:
        raise RuntimeError(
            "The latest extraction result does not expose editable extracted "
            "fields for this review task."
        )

    normalized_field_edits: dict[str, ExtractionFieldEditInput] = {}
    for field_edit in field_edits:
        normalized_field_name = _normalize_field_key(field_edit.field_name)
        if not normalized_field_name:
            raise ValueError("field_name is required for every extraction edit")

        if normalized_field_name in normalized_field_edits:
            raise ValueError(
                f"Duplicate extraction edit submitted for field '{field_edit.field_name}'."
            )

        normalized_field_edits[normalized_field_name] = field_edit

    matched_field_names: set[str] = set()
    changed_fields: list[ExtractionFieldChangeRecord] = []
    updated_fields: list[object] = []
    for raw_field in raw_fields:
        if not isinstance(raw_field, dict):
            updated_fields.append(raw_field)
            continue

        field_name = raw_field.get("name")
        field_value = raw_field.get("value")
        if not isinstance(field_name, str) or not isinstance(field_value, str):
            updated_fields.append(raw_field)
            continue

        matching_edit = normalized_field_edits.get(_normalize_field_key(field_name))
        if matching_edit is None:
            updated_fields.append(raw_field)
            continue

        matched_field_names.add(_normalize_field_key(field_name))
        updated_value = matching_edit.value
        if updated_value == field_value:
            updated_fields.append(raw_field)
            continue

        updated_field = dict(raw_field)
        updated_field["value"] = updated_value
        updated_fields.append(updated_field)
        changed_fields.append(
            ExtractionFieldChangeRecord(
                confidence=_resolve_field_confidence(raw_field.get("confidence")),
                current_value=updated_value,
                field_name=field_name,
                original_value=field_value,
            )
        )

    unmatched_field_names = [
        field_edit.field_name
        for normalized_field_name, field_edit in normalized_field_edits.items()
        if normalized_field_name not in matched_field_names
    ]
    if unmatched_field_names:
        raise RuntimeError(
            "The latest extraction result does not contain the requested field "
            f"edit target(s): {', '.join(unmatched_field_names)}."
        )

    if len(changed_fields) == 0:
        raise ValueError("At least one extraction field change is required.")

    result_payload["extractedFields"] = updated_fields
    return result_payload, tuple(changed_fields)


def _build_extraction_edit_plan(
    request: PacketReviewExtractionEditRequest,
    *,
    review_task: ReviewTaskRecord,
    snapshot: PacketWorkspaceSnapshot,
    settings: AppSettings,
) -> _ExtractionEditPlan:
    """Build the SQL persistence plan for one extraction edit save."""

    source_extraction_result = _resolve_latest_extraction_result(review_task, snapshot)
    changed_at_utc = datetime.now(UTC)
    result_payload, changed_fields = _build_updated_extraction_payload(
        source_extraction_result,
        request.field_edits,
    )
    result_payload["reviewEdits"] = {
        "changeCount": len(changed_fields),
        "changedFieldNames": [field_change.field_name for field_change in changed_fields],
        "editedAtUtc": changed_at_utc.isoformat(),
        "reviewTaskId": review_task.review_task_id,
        "sourceExtractionResultId": source_extraction_result.extraction_result_id,
    }
    extraction_result = ExtractionResultRecord(
        extraction_result_id=f"ext_{uuid4().hex}",
        packet_id=source_extraction_result.packet_id,
        document_id=source_extraction_result.document_id,
        provider=source_extraction_result.provider,
        model_name=source_extraction_result.model_name,
        document_type=source_extraction_result.document_type,
        prompt_profile_id=source_extraction_result.prompt_profile_id,
        summary=source_extraction_result.summary,
        result_payload=attach_content_controls(
            result_payload,
            retention_class="extracted_content",
            contains_sensitive_content=True,
        ),
        created_at_utc=changed_at_utc,
    )
    audit_event_payload: dict[str, Any] = {
        "changedFields": [
            field_change.model_dump(mode="json") for field_change in changed_fields
        ],
        "newExtractionResultId": extraction_result.extraction_result_id,
        "sourceExtractionResultId": source_extraction_result.extraction_result_id,
    }
    audit_event = AuditEventRecord(
        audit_event_id=1,
        actor_user_id=request.edited_by_user_id,
        actor_email=request.edited_by_email,
        packet_id=review_task.packet_id,
        document_id=review_task.document_id,
        review_task_id=review_task.review_task_id,
        event_type="review.extraction.fields.updated",
        event_payload=(
            mask_history_payload(
                audit_event_payload,
                retention_class="review_history",
            )
            if settings.mask_sensitive_history
            else audit_event_payload
        ),
        created_at_utc=changed_at_utc,
    )

    return _ExtractionEditPlan(
        audit_event=audit_event,
        changed_fields=changed_fields,
        extraction_result=extraction_result,
        review_task=review_task,
    )


def _resolve_selected_account_id(
    request: PacketReviewDecisionRequest,
    review_task: ReviewTaskRecord,
    snapshot: PacketWorkspaceSnapshot,
) -> str | None:
    """Return the selected account id for the decision payload."""

    requested_account_id = _normalize_optional_text(request.selected_account_id)
    if requested_account_id is not None:
        return requested_account_id

    if review_task.selected_account_id is not None:
        return review_task.selected_account_id

    latest_match_runs = _select_latest_account_match_runs_by_document(
        snapshot.account_match_runs
    )
    latest_match_run = latest_match_runs.get(review_task.document_id)
    if latest_match_run is not None:
        return latest_match_run.selected_account_id

    return None


def _should_queue_recommendation_job(
    review_task: ReviewTaskRecord,
    snapshot: PacketWorkspaceSnapshot,
) -> bool:
    """Return whether an approved review task should queue recommendation work."""

    latest_extraction_results = _select_latest_extraction_results_by_document(
        snapshot.extraction_results
    )
    if review_task.document_id not in latest_extraction_results:
        return False

    latest_jobs = _select_latest_jobs_by_document(snapshot.processing_jobs)
    latest_job = latest_jobs.get(review_task.document_id)
    if (
        latest_job is not None
        and latest_job.stage_name == ProcessingStageName.RECOMMENDATION
        and latest_job.status
        in {
            ProcessingJobStatus.QUEUED,
            ProcessingJobStatus.RUNNING,
            ProcessingJobStatus.SUCCEEDED,
        }
    ):
        return False

    return not any(
        recommendation_result.document_id == review_task.document_id
        for recommendation_result in snapshot.recommendation_results
    )


def _resolve_document_status(
    request: PacketReviewDecisionRequest,
    review_task: ReviewTaskRecord,
    snapshot: PacketWorkspaceSnapshot,
) -> tuple[PacketStatus, str | None]:
    """Return the document status implied by the review decision."""

    if request.decision_status == ReviewStatus.REJECTED:
        return PacketStatus.BLOCKED, None

    if _should_queue_recommendation_job(review_task, snapshot):
        return PacketStatus.READY_FOR_RECOMMENDATION, f"job_{uuid4().hex}"

    raise RuntimeError(
        "Only extraction-backed review tasks can be approved in the packet "
        "workspace right now."
    )


def _resolve_packet_status(
    *,
    document_status: PacketStatus,
    review_task: ReviewTaskRecord,
    snapshot: PacketWorkspaceSnapshot,
) -> PacketStatus:
    """Return the packet status after one review task decision is applied."""

    if document_status == PacketStatus.BLOCKED:
        return PacketStatus.BLOCKED

    decided_review_task_ids = {
        decision.review_task_id for decision in snapshot.review_decisions
    }
    remaining_review_task_ids = {
        task.review_task_id
        for task in snapshot.review_tasks
        if task.review_task_id != review_task.review_task_id
        and task.review_task_id not in decided_review_task_ids
        and task.status == PacketStatus.AWAITING_REVIEW
    }
    if remaining_review_task_ids:
        return PacketStatus.AWAITING_REVIEW

    effective_document_statuses = {
        document.document_id: document.status for document in snapshot.documents
    }
    effective_document_statuses[review_task.document_id] = document_status
    if any(status == PacketStatus.BLOCKED for status in effective_document_statuses.values()):
        return PacketStatus.BLOCKED

    if any(
        status == PacketStatus.AWAITING_REVIEW
        for document_id, status in effective_document_statuses.items()
        if document_id != review_task.document_id
    ):
        return PacketStatus.AWAITING_REVIEW

    if any(
        status == PacketStatus.READY_FOR_RECOMMENDATION
        for status in effective_document_statuses.values()
    ):
        return PacketStatus.READY_FOR_RECOMMENDATION

    return snapshot.packet.status


def _build_operator_note_record(
    request: PacketReviewDecisionRequest,
    review_task: ReviewTaskRecord,
) -> OperatorNoteRecord | None:
    """Return the optional operator note captured with a review decision."""

    note_text = _normalize_optional_text(request.review_notes)
    if note_text is None:
        return None

    return OperatorNoteRecord(
        note_id=f"note_{uuid4().hex}",
        packet_id=review_task.packet_id,
        document_id=review_task.document_id,
        review_task_id=review_task.review_task_id,
        created_by_user_id=request.decided_by_user_id,
        created_by_email=request.decided_by_email,
        note_text=note_text,
        is_private=False,
        created_at_utc=datetime.now(UTC),
    )


def _build_review_decision_plan(
    request: PacketReviewDecisionRequest,
    *,
    review_task: ReviewTaskRecord,
    snapshot: PacketWorkspaceSnapshot,
) -> _ReviewDecisionPlan:
    """Build the SQL persistence plan for one packet review decision."""

    selected_account_id = _resolve_selected_account_id(request, review_task, snapshot)
    document_status, queued_recommendation_job_id = _resolve_document_status(
        request,
        review_task,
        snapshot,
    )
    decision_record = ReviewDecisionRecord(
        decision_id=f"decision_{uuid4().hex}",
        review_task_id=review_task.review_task_id,
        packet_id=review_task.packet_id,
        document_id=review_task.document_id,
        decision_status=request.decision_status,
        decision_reason_code=_normalize_optional_text(request.decision_reason_code),
        selected_account_id=selected_account_id,
        review_notes=_normalize_optional_text(request.review_notes),
        decided_by_user_id=request.decided_by_user_id,
        decided_by_email=request.decided_by_email,
        decided_at_utc=datetime.now(UTC),
    )
    note_record = _build_operator_note_record(request, review_task)
    review_task_status = document_status
    packet_status = _resolve_packet_status(
        document_status=document_status,
        review_task=review_task,
        snapshot=snapshot,
    )

    return _ReviewDecisionPlan(
        decision_record=decision_record,
        document_status=document_status,
        note_record=note_record,
        packet_status=packet_status,
        queued_recommendation_job_id=queued_recommendation_job_id,
        review_task=review_task,
        review_task_status=review_task_status,
        selected_account_id=selected_account_id,
    )


def _apply_history_controls_to_plan(
    plan: _ReviewDecisionPlan,
) -> _ReviewDecisionPlan:
    """Mask persisted review notes before they are written to SQL history tables."""

    masked_decision_notes = mask_sensitive_text(plan.decision_record.review_notes)
    masked_note_record = plan.note_record
    if masked_note_record is not None:
        masked_note_record = masked_note_record.model_copy(
            update={
                "note_text": (
                    mask_sensitive_text(masked_note_record.note_text)
                    or masked_note_record.note_text
                )
            }
        )

    return replace(
        plan,
        decision_record=plan.decision_record.model_copy(
            update={"review_notes": masked_decision_notes}
        ),
        note_record=masked_note_record,
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


def _insert_audit_event(cursor: Any, *, event: AuditEventRecord) -> None:
    """Append one audit event row."""

    cursor.execute(
        """
        INSERT INTO dbo.AuditEvents (
            actorUserId,
            actorEmail,
            packetId,
            documentId,
            reviewTaskId,
            eventType,
            eventPayloadJson,
            createdAtUtc
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            event.actor_user_id,
            event.actor_email,
            event.packet_id,
            event.document_id,
            event.review_task_id,
            event.event_type,
            json.dumps(event.event_payload or {}),
            event.created_at_utc,
        ),
    )


def apply_packet_review_decision(
    review_task_id: str,
    request: PacketReviewDecisionRequest,
    settings: AppSettings,
) -> PacketReviewDecisionResponse:
    """Apply a SQL-backed review decision and update packet state."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        raise PacketReviewConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    snapshot = repository.get_packet_workspace_snapshot_for_review_task(review_task_id)
    review_task = _resolve_review_task(snapshot, review_task_id)
    expected_row_version = _assert_review_task_is_current(request, review_task)
    _assert_reviewer_owns_task(request, review_task)
    if _review_task_has_decision(snapshot, review_task_id):
        raise PacketReviewConflictError(
            f"Review task '{review_task_id}' already has a recorded decision."
        )

    audit_review_notes = _normalize_optional_text(request.review_notes)
    plan = _build_review_decision_plan(request, review_task=review_task, snapshot=snapshot)
    if settings.mask_sensitive_history:
        plan = _apply_history_controls_to_plan(plan)

    audit_event = AuditEventRecord(
        audit_event_id=1,
        actor_user_id=plan.decision_record.decided_by_user_id,
        actor_email=plan.decision_record.decided_by_email,
        packet_id=plan.decision_record.packet_id,
        document_id=plan.decision_record.document_id,
        review_task_id=plan.decision_record.review_task_id,
        event_type="review.decision.recorded",
        event_payload=(
            mask_history_payload(
                {
                    "decisionId": plan.decision_record.decision_id,
                    "decisionStatus": plan.decision_record.decision_status.value,
                    "documentStatus": plan.document_status.value,
                    "packetStatus": plan.packet_status.value,
                    "queuedRecommendationJobId": plan.queued_recommendation_job_id,
                    "selectedAccountId": plan.selected_account_id,
                    "reviewNotes": audit_review_notes,
                },
                retention_class="review_history",
            )
            if settings.mask_sensitive_history
            else {
                "decisionId": plan.decision_record.decision_id,
                "decisionStatus": plan.decision_record.decision_status.value,
                "documentStatus": plan.document_status.value,
                "packetStatus": plan.packet_status.value,
                "queuedRecommendationJobId": plan.queued_recommendation_job_id,
                "selectedAccountId": plan.selected_account_id,
                "reviewNotes": plan.decision_record.review_notes,
            }
        ),
        created_at_utc=plan.decision_record.decided_at_utc,
    )
    connection_string = settings.sql_connection_string
    if not connection_string:
        raise PacketReviewConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    with open_sql_connection(connection_string, autocommit=False) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO dbo.ReviewDecisions (
                        decisionId,
                        reviewTaskId,
                        packetId,
                        documentId,
                        decisionStatus,
                        decisionReasonCode,
                        selectedAccountId,
                        reviewNotes,
                        decidedByUserId,
                        decidedByEmail,
                        decidedAtUtc
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        plan.decision_record.decision_id,
                        plan.decision_record.review_task_id,
                        plan.decision_record.packet_id,
                        plan.decision_record.document_id,
                        plan.decision_record.decision_status.value,
                        plan.decision_record.decision_reason_code,
                        plan.decision_record.selected_account_id,
                        plan.decision_record.review_notes,
                        plan.decision_record.decided_by_user_id,
                        plan.decision_record.decided_by_email,
                        plan.decision_record.decided_at_utc,
                    ),
                )
                if plan.note_record is not None:
                    cursor.execute(
                        """
                        INSERT INTO dbo.OperatorNotes (
                            noteId,
                            packetId,
                            documentId,
                            reviewTaskId,
                            createdByUserId,
                            createdByEmail,
                            noteText,
                            isPrivate,
                            createdAtUtc
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            plan.note_record.note_id,
                            plan.note_record.packet_id,
                            plan.note_record.document_id,
                            plan.note_record.review_task_id,
                            plan.note_record.created_by_user_id,
                            plan.note_record.created_by_email,
                            plan.note_record.note_text,
                            plan.note_record.is_private,
                            plan.note_record.created_at_utc,
                        ),
                    )

                cursor.execute(
                    """
                    UPDATE dbo.ReviewTasks
                    SET
                        status = %s,
                        selectedAccountId = %s,
                        notesSummary = %s,
                        updatedAtUtc = SYSUTCDATETIME()
                    WHERE reviewTaskId = %s
                        AND status = %s
                        AND rowVersion = %s
                    """,
                    (
                        plan.review_task_status.value,
                        plan.selected_account_id,
                        (
                            plan.note_record.note_text
                            if plan.note_record is not None
                            else review_task.notes_summary
                        ),
                        plan.review_task.review_task_id,
                        PacketStatus.AWAITING_REVIEW.value,
                        expected_row_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise PacketReviewConflictError(
                        f"Review task '{review_task_id}' changed while this decision was being recorded. Refresh the workspace and try again."
                    )
                cursor.execute(
                    """
                    UPDATE dbo.PacketDocuments
                    SET
                        status = %s,
                        updatedAtUtc = SYSUTCDATETIME()
                    WHERE documentId = %s
                    """,
                    (
                        plan.document_status.value,
                        plan.review_task.document_id,
                    ),
                )
                if plan.queued_recommendation_job_id is not None:
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
                            plan.queued_recommendation_job_id,
                            plan.review_task.packet_id,
                            plan.review_task.document_id,
                            ProcessingStageName.RECOMMENDATION.value,
                            ProcessingJobStatus.QUEUED.value,
                        ),
                    )

                cursor.execute(
                    """
                    UPDATE dbo.Packets
                    SET
                        status = %s,
                        updatedAtUtc = SYSUTCDATETIME()
                    WHERE packetId = %s
                    """,
                    (
                        plan.packet_status.value,
                        plan.review_task.packet_id,
                    ),
                )
                _insert_packet_event(
                    cursor,
                    document_id=plan.review_task.document_id,
                    event_payload={
                        "decisionId": plan.decision_record.decision_id,
                        "decisionStatus": plan.decision_record.decision_status.value,
                        "reviewTaskId": plan.review_task.review_task_id,
                        "selectedAccountId": plan.selected_account_id,
                    },
                    event_type="document.review.decision.recorded",
                    packet_id=plan.review_task.packet_id,
                )
                if plan.queued_recommendation_job_id is not None:
                    _insert_packet_event(
                        cursor,
                        document_id=plan.review_task.document_id,
                        event_payload={
                            "recommendationJobId": plan.queued_recommendation_job_id,
                            "reviewTaskId": plan.review_task.review_task_id,
                            "status": plan.document_status.value,
                        },
                        event_type="document.ready_for_recommendation",
                        packet_id=plan.review_task.packet_id,
                    )
                if plan.document_status == PacketStatus.BLOCKED:
                    _insert_packet_event(
                        cursor,
                        document_id=plan.review_task.document_id,
                        event_payload={
                            "decisionId": plan.decision_record.decision_id,
                            "reviewTaskId": plan.review_task.review_task_id,
                            "status": plan.document_status.value,
                        },
                        event_type="document.blocked",
                        packet_id=plan.review_task.packet_id,
                    )
                _insert_audit_event(cursor, event=audit_event)

            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return PacketReviewDecisionResponse(
        decision=plan.decision_record,
        document_status=plan.document_status,
        operator_note=plan.note_record,
        packet_id=plan.review_task.packet_id,
        packet_status=plan.packet_status,
        queued_recommendation_job_id=plan.queued_recommendation_job_id,
        review_task_id=plan.review_task.review_task_id,
        review_task_status=plan.review_task_status,
    )


def apply_packet_review_assignment(
    review_task_id: str,
    request: PacketReviewAssignmentRequest,
    settings: AppSettings,
) -> PacketReviewAssignmentResponse:
    """Persist one review-task assignment change for the protected workspace."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        raise PacketReviewConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    snapshot = repository.get_packet_workspace_snapshot_for_review_task(review_task_id)
    review_task = _resolve_review_task(snapshot, review_task_id)
    expected_row_version = _assert_review_task_is_current(request, review_task)
    if _review_task_has_decision(snapshot, review_task_id):
        raise PacketReviewConflictError(
            f"Review task '{review_task_id}' already has a recorded decision."
        )

    assigned_user_email = _normalize_optional_text(request.assigned_user_email)
    assigned_user_id = _normalize_optional_text(request.assigned_user_id)
    current_assigned_user_email = _normalize_optional_text(review_task.assigned_user_email)
    current_assigned_user_id = _normalize_optional_text(review_task.assigned_user_id)
    if (
        assigned_user_email == current_assigned_user_email
        and assigned_user_id == current_assigned_user_id
    ):
        raise ValueError("A different review-task assignee is required.")

    assignment_event_payload = {
        "assignedUserEmail": assigned_user_email,
        "assignedUserId": assigned_user_id,
        "previousAssignedUserEmail": review_task.assigned_user_email,
        "previousAssignedUserId": review_task.assigned_user_id,
        "reviewTaskId": review_task.review_task_id,
    }
    audit_event = AuditEventRecord(
        audit_event_id=1,
        actor_user_id=request.assigned_by_user_id,
        actor_email=request.assigned_by_email,
        packet_id=review_task.packet_id,
        document_id=review_task.document_id,
        review_task_id=review_task.review_task_id,
        event_type="review.assignment.updated",
        event_payload=(
            mask_history_payload(
                assignment_event_payload,
                retention_class="review_history",
            )
            if settings.mask_sensitive_history
            else assignment_event_payload
        ),
        created_at_utc=datetime.now(UTC),
    )
    connection_string = settings.sql_connection_string
    if not connection_string:
        raise PacketReviewConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    with open_sql_connection(connection_string, autocommit=False) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE dbo.ReviewTasks
                    SET
                        assignedUserId = %s,
                        assignedUserEmail = %s,
                        updatedAtUtc = SYSUTCDATETIME()
                    WHERE reviewTaskId = %s
                        AND status = %s
                        AND rowVersion = %s
                    """,
                    (
                        assigned_user_id,
                        assigned_user_email,
                        review_task.review_task_id,
                        PacketStatus.AWAITING_REVIEW.value,
                        expected_row_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise PacketReviewConflictError(
                        f"Review task '{review_task_id}' changed while this assignment was being recorded. Refresh the workspace and try again."
                    )

                cursor.execute(
                    """
                    UPDATE dbo.PacketDocuments
                    SET updatedAtUtc = SYSUTCDATETIME()
                    WHERE documentId = %s
                    """,
                    (review_task.document_id,),
                )
                cursor.execute(
                    """
                    UPDATE dbo.Packets
                    SET updatedAtUtc = SYSUTCDATETIME()
                    WHERE packetId = %s
                    """,
                    (review_task.packet_id,),
                )
                _insert_packet_event(
                    cursor,
                    document_id=review_task.document_id,
                    event_payload={
                        "assignmentState": (
                            "assigned" if assigned_user_email is not None else "unassigned"
                        ),
                        "reviewTaskId": review_task.review_task_id,
                    },
                    event_type="document.review.assignment.updated",
                    packet_id=review_task.packet_id,
                )
                _insert_audit_event(cursor, event=audit_event)

            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return PacketReviewAssignmentResponse(
        assigned_user_email=assigned_user_email,
        assigned_user_id=assigned_user_id,
        packet_id=review_task.packet_id,
        review_task_id=review_task.review_task_id,
    )


def apply_packet_review_note(
    review_task_id: str,
    request: PacketReviewNoteRequest,
    settings: AppSettings,
) -> PacketReviewNoteResponse:
    """Persist one SQL-backed operator note for a review task."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        raise PacketReviewConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    snapshot = repository.get_packet_workspace_snapshot_for_review_task(review_task_id)
    review_task = _resolve_review_task(snapshot, review_task_id)
    expected_row_version = _assert_review_task_is_current(request, review_task)
    _assert_review_task_actor_owns_task(
        review_task,
        actor_email=request.created_by_email,
    )
    if _review_task_has_decision(snapshot, review_task_id):
        raise PacketReviewConflictError(
            f"Review task '{review_task_id}' already has a recorded decision."
        )

    normalized_note_text = _normalize_optional_text(request.note_text)
    if normalized_note_text is None:
        raise ValueError("note_text is required")

    persisted_note_text = normalized_note_text
    if settings.mask_sensitive_history:
        persisted_note_text = (
            mask_sensitive_text(normalized_note_text) or normalized_note_text
        )

    operator_note = OperatorNoteRecord(
        note_id=f"note_{uuid4().hex}",
        packet_id=review_task.packet_id,
        document_id=review_task.document_id,
        review_task_id=review_task.review_task_id,
        created_by_user_id=request.created_by_user_id,
        created_by_email=request.created_by_email,
        note_text=persisted_note_text,
        is_private=request.is_private,
        created_at_utc=datetime.now(UTC),
    )
    audit_event = AuditEventRecord(
        audit_event_id=1,
        actor_user_id=operator_note.created_by_user_id,
        actor_email=operator_note.created_by_email,
        packet_id=operator_note.packet_id,
        document_id=operator_note.document_id,
        review_task_id=operator_note.review_task_id,
        event_type="review.note.recorded",
        event_payload=(
            mask_history_payload(
                {
                    "isPrivate": operator_note.is_private,
                    "noteId": operator_note.note_id,
                    "noteText": normalized_note_text,
                    "reviewTaskId": operator_note.review_task_id,
                },
                retention_class="review_history",
            )
            if settings.mask_sensitive_history
            else {
                "isPrivate": operator_note.is_private,
                "noteId": operator_note.note_id,
                "noteText": operator_note.note_text,
                "reviewTaskId": operator_note.review_task_id,
            }
        ),
        created_at_utc=operator_note.created_at_utc,
    )
    connection_string = settings.sql_connection_string
    if not connection_string:
        raise PacketReviewConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    with open_sql_connection(connection_string, autocommit=False) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO dbo.OperatorNotes (
                        noteId,
                        packetId,
                        documentId,
                        reviewTaskId,
                        createdByUserId,
                        createdByEmail,
                        noteText,
                        isPrivate,
                        createdAtUtc
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        operator_note.note_id,
                        operator_note.packet_id,
                        operator_note.document_id,
                        operator_note.review_task_id,
                        operator_note.created_by_user_id,
                        operator_note.created_by_email,
                        operator_note.note_text,
                        operator_note.is_private,
                        operator_note.created_at_utc,
                    ),
                )
                cursor.execute(
                    """
                    UPDATE dbo.ReviewTasks
                    SET
                        notesSummary = %s,
                        updatedAtUtc = SYSUTCDATETIME()
                    WHERE reviewTaskId = %s
                        AND rowVersion = %s
                    """,
                    (
                        operator_note.note_text,
                        review_task.review_task_id,
                        expected_row_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise PacketReviewConflictError(
                        f"Review task '{review_task_id}' changed while this note was being recorded. Refresh the workspace and try again."
                    )

                cursor.execute(
                    """
                    UPDATE dbo.PacketDocuments
                    SET updatedAtUtc = SYSUTCDATETIME()
                    WHERE documentId = %s
                    """,
                    (review_task.document_id,),
                )
                cursor.execute(
                    """
                    UPDATE dbo.Packets
                    SET updatedAtUtc = SYSUTCDATETIME()
                    WHERE packetId = %s
                    """,
                    (review_task.packet_id,),
                )
                _insert_packet_event(
                    cursor,
                    document_id=review_task.document_id,
                    event_payload={
                        "isPrivate": operator_note.is_private,
                        "noteId": operator_note.note_id,
                        "reviewTaskId": review_task.review_task_id,
                    },
                    event_type="document.review.note.recorded",
                    packet_id=review_task.packet_id,
                )
                _insert_audit_event(cursor, event=audit_event)

            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return PacketReviewNoteResponse(
        operator_note=operator_note,
        packet_id=review_task.packet_id,
        review_task_id=review_task.review_task_id,
    )


def apply_packet_review_extraction_edits(
    review_task_id: str,
    request: PacketReviewExtractionEditRequest,
    settings: AppSettings,
) -> PacketReviewExtractionEditResponse:
    """Persist extracted-field edits for one SQL-backed review task."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        raise PacketReviewConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    snapshot = repository.get_packet_workspace_snapshot_for_review_task(review_task_id)
    review_task = _resolve_review_task(snapshot, review_task_id)
    expected_row_version = _assert_review_task_is_current(request, review_task)
    _assert_review_task_actor_owns_task(
        review_task,
        actor_email=request.edited_by_email,
    )
    if _review_task_has_decision(snapshot, review_task_id):
        raise PacketReviewConflictError(
            f"Review task '{review_task_id}' already has a recorded decision."
        )

    plan = _build_extraction_edit_plan(
        request,
        review_task=review_task,
        snapshot=snapshot,
        settings=settings,
    )
    connection_string = settings.sql_connection_string
    if not connection_string:
        raise PacketReviewConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    with open_sql_connection(connection_string, autocommit=False) as connection:
        try:
            with connection.cursor() as cursor:
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        plan.extraction_result.extraction_result_id,
                        plan.extraction_result.packet_id,
                        plan.extraction_result.document_id,
                        plan.extraction_result.provider,
                        plan.extraction_result.model_name,
                        plan.extraction_result.document_type,
                        (
                            plan.extraction_result.prompt_profile_id.value
                            if plan.extraction_result.prompt_profile_id is not None
                            else None
                        ),
                        plan.extraction_result.summary,
                        json.dumps(plan.extraction_result.result_payload),
                        plan.extraction_result.created_at_utc,
                    ),
                )
                cursor.execute(
                    """
                    UPDATE dbo.ReviewTasks
                    SET updatedAtUtc = SYSUTCDATETIME()
                    WHERE reviewTaskId = %s
                        AND rowVersion = %s
                    """,
                    (
                        plan.review_task.review_task_id,
                        expected_row_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise PacketReviewConflictError(
                        f"Review task '{review_task_id}' changed while the extraction edits were being recorded. Refresh the workspace and try again."
                    )

                cursor.execute(
                    """
                    UPDATE dbo.PacketDocuments
                    SET updatedAtUtc = SYSUTCDATETIME()
                    WHERE documentId = %s
                    """,
                    (plan.review_task.document_id,),
                )
                cursor.execute(
                    """
                    UPDATE dbo.Packets
                    SET updatedAtUtc = SYSUTCDATETIME()
                    WHERE packetId = %s
                    """,
                    (plan.review_task.packet_id,),
                )
                _insert_packet_event(
                    cursor,
                    document_id=plan.review_task.document_id,
                    event_payload={
                        "changedFieldCount": len(plan.changed_fields),
                        "changedFieldNames": [
                            field_change.field_name
                            for field_change in plan.changed_fields
                        ],
                        "newExtractionResultId": plan.extraction_result.extraction_result_id,
                        "reviewTaskId": plan.review_task.review_task_id,
                        "sourceExtractionResultId": plan.audit_event.event_payload.get(
                            "sourceExtractionResultId"
                        )
                        if isinstance(plan.audit_event.event_payload, dict)
                        else None,
                    },
                    event_type="document.extraction.fields.updated",
                    packet_id=plan.review_task.packet_id,
                )
                _insert_audit_event(cursor, event=plan.audit_event)

            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return PacketReviewExtractionEditResponse(
        audit_event=plan.audit_event,
        changed_fields=plan.changed_fields,
        document_id=plan.review_task.document_id,
        extraction_result=plan.extraction_result,
        packet_id=plan.review_task.packet_id,
        review_task_id=plan.review_task.review_task_id,
    )