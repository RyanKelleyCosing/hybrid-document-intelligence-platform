"""SQL-backed repositories for the remaining Epic 1 operator-state contracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from document_intelligence.models import (
    AccountMatchCandidate,
    AccountMatchRunCreateRequest,
    AccountMatchRunRecord,
    AccountMatchStatus,
    ArchiveDocumentLineage,
    ArchivePreflightResult,
    AuditEventCreateRequest,
    AuditEventRecord,
    ClassificationPriorCreateRequest,
    ClassificationPriorRecord,
    ClassificationResultCreateRequest,
    ClassificationResultRecord,
    ClassificationResultSource,
    DocumentAssetRecord,
    DocumentSource,
    DuplicateDetectionResult,
    ExtractionResultCreateRequest,
    ExtractionResultRecord,
    IssuerCategory,
    ManagedClassificationDefinitionRecord,
    ManagedDocumentTypeDefinitionRecord,
    ManagedPromptProfileRecord,
    OcrResultCreateRequest,
    OcrResultRecord,
    OperatorNoteCreateRequest,
    OperatorNoteRecord,
    PacketAssignmentState,
    PacketDocumentRecord,
    PacketEventRecord,
    PacketQueueItem,
    PacketQueueListRequest,
    PacketQueueListResponse,
    PacketRecord,
    PacketStatus,
    PacketWorkspaceSnapshot,
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStageName,
    PromptProfileId,
    PromptProfileVersionRecord,
    RecommendationDisposition,
    RecommendationEvidenceItem,
    RecommendationResultCreateRequest,
    RecommendationResultRecord,
    RecommendationRunCreateRequest,
    RecommendationRunRecord,
    RecommendationRunStatus,
    ReviewDecisionCreateRequest,
    ReviewDecisionRecord,
    ReviewStatus,
    ReviewTaskCreateRequest,
    ReviewTaskPriority,
    ReviewTaskRecord,
)
from document_intelligence.processing_taxonomy import get_stage_name_for_status
from document_intelligence.safety import (
    attach_content_controls,
    mask_history_payload,
    mask_sensitive_text,
)
from document_intelligence.settings import AppSettings
from document_intelligence.utils.sql import open_sql_connection


def _as_optional_datetime(value: object) -> datetime | None:
    """Return the datetime value when a row contains one."""

    return value if isinstance(value, datetime) else None


def _as_optional_float(value: object) -> float | None:
    """Return the float value when a row contains one."""

    if value is None:
        return None

    return float(str(value))


def _as_optional_int(value: object) -> int | None:
    """Return the integer value when a row contains one."""

    if value is None:
        return None

    if isinstance(value, int):
        return value

    return int(str(value))


def _as_optional_str(value: object) -> str | None:
    """Return the string value when a row contains one."""

    return str(value) if value is not None else None


def _as_optional_row_version(value: object) -> str | None:
    """Return a lowercase hex row-version token from a SQL row."""

    if value is None:
        return None

    if isinstance(value, memoryview):
        return value.tobytes().hex()

    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()

    return str(value)


def _load_json_dict(value: object) -> dict[str, Any]:
    """Return a dictionary decoded from a JSON column."""

    if value is None:
        return {}

    payload = json.loads(str(value))
    return payload if isinstance(payload, dict) else {}


def _load_json_list(value: object) -> list[Any]:
    """Return a list decoded from a JSON column."""

    if value is None:
        return []

    payload = json.loads(str(value))
    return payload if isinstance(payload, list) else []


def _load_str_tuple(value: object) -> tuple[str, ...]:
    """Return a tuple of strings decoded from a JSON column."""

    return tuple(str(item) for item in _load_json_list(value) if item is not None)


def _load_delimited_str_tuple(value: object, *, delimiter: str = "|") -> tuple[str, ...]:
    """Return a tuple of strings split from a delimited SQL aggregate."""

    if value is None:
        return ()

    return tuple(item for item in str(value).split(delimiter) if item.strip())


def _require_row_str(value: object, *, field_name: str) -> str:
    """Return a required string value from a SQL row."""

    if value is None:
        raise ValueError(f"SQL row field '{field_name}' is required")

    return str(value)


def _build_placeholder_list(item_count: int) -> str:
    """Return a DB-API placeholder list for an IN clause."""

    return ", ".join(["%s"] * item_count)


def _build_classification_definition_from_row(
    row: tuple[object, ...],
) -> ManagedClassificationDefinitionRecord:
    """Build a classification definition record from SQL."""

    return ManagedClassificationDefinitionRecord(
        classification_id=_require_row_str(row[0], field_name="classificationId"),
        classification_key=_require_row_str(
            row[1], field_name="classificationKey"
        ),
        display_name=_require_row_str(row[2], field_name="displayName"),
        description=_as_optional_str(row[3]),
        is_enabled=bool(row[4]),
        issuer_category=IssuerCategory(
            _require_row_str(row[5], field_name="issuerCategory")
        ),
        default_prompt_profile_id=(
            PromptProfileId(str(row[6])) if row[6] is not None else None
        ),
        created_at_utc=_as_optional_datetime(row[7]) or datetime.now(UTC),
        updated_at_utc=_as_optional_datetime(row[8]) or datetime.now(UTC),
    )


def _build_document_type_definition_from_row(
    row: tuple[object, ...],
) -> ManagedDocumentTypeDefinitionRecord:
    """Build a document-type definition record from SQL."""

    return ManagedDocumentTypeDefinitionRecord(
        document_type_id=_require_row_str(row[0], field_name="documentTypeId"),
        document_type_key=_require_row_str(row[1], field_name="documentTypeKey"),
        display_name=_require_row_str(row[2], field_name="displayName"),
        description=_as_optional_str(row[3]),
        is_enabled=bool(row[4]),
        classification_id=_as_optional_str(row[5]),
        default_prompt_profile_id=(
            PromptProfileId(str(row[6])) if row[6] is not None else None
        ),
        required_fields=_load_str_tuple(row[7]),
        created_at_utc=_as_optional_datetime(row[8]) or datetime.now(UTC),
        updated_at_utc=_as_optional_datetime(row[9]) or datetime.now(UTC),
    )


def _build_prompt_profile_from_row(
    row: tuple[object, ...],
) -> ManagedPromptProfileRecord:
    """Build a prompt-profile record from SQL."""

    return ManagedPromptProfileRecord(
        prompt_profile_id=PromptProfileId(
            _require_row_str(row[0], field_name="promptProfileId")
        ),
        display_name=_require_row_str(row[1], field_name="displayName"),
        description=_as_optional_str(row[2]),
        issuer_category=IssuerCategory(
            _require_row_str(row[3], field_name="issuerCategory")
        ),
        is_enabled=bool(row[4]),
        created_at_utc=_as_optional_datetime(row[5]) or datetime.now(UTC),
        updated_at_utc=_as_optional_datetime(row[6]) or datetime.now(UTC),
    )


def _build_prompt_profile_version_from_row(
    row: tuple[object, ...],
) -> PromptProfileVersionRecord:
    """Build a prompt-profile version record from SQL."""

    return PromptProfileVersionRecord(
        prompt_profile_version_id=_require_row_str(
            row[0], field_name="promptProfileVersionId"
        ),
        prompt_profile_id=PromptProfileId(
            _require_row_str(row[1], field_name="promptProfileId")
        ),
        version_number=_as_optional_int(row[2]) or 1,
        definition_payload=_load_json_dict(row[3]),
        is_active=bool(row[4]),
        created_at_utc=_as_optional_datetime(row[5]) or datetime.now(UTC),
    )


def _build_packet_record_from_row(row: tuple[object, ...]) -> PacketRecord:
    """Build a packet record from SQL."""

    return PacketRecord(
        packet_id=_require_row_str(row[0], field_name="packetId"),
        packet_name=_require_row_str(row[1], field_name="packetName"),
        source=DocumentSource(_require_row_str(row[2], field_name="source")),
        source_uri=_as_optional_str(row[3]),
        status=PacketStatus(_require_row_str(row[4], field_name="status")),
        submitted_by=_as_optional_str(row[5]),
        packet_tags=_load_str_tuple(row[6]),
        received_at_utc=_as_optional_datetime(row[7]) or datetime.now(UTC),
        created_at_utc=_as_optional_datetime(row[8]) or datetime.now(UTC),
        updated_at_utc=_as_optional_datetime(row[9]) or datetime.now(UTC),
        packet_fingerprint=_as_optional_str(row[10]),
        source_fingerprint=_as_optional_str(row[11]),
        duplicate_of_packet_id=_as_optional_str(row[12]),
        duplicate_detection=DuplicateDetectionResult.model_validate(
            _load_json_dict(row[13]) or DuplicateDetectionResult().model_dump()
        ),
    )


def _build_packet_queue_item_from_row(row: tuple[object, ...]) -> PacketQueueItem:
    """Build a packet queue row from SQL."""

    received_at_utc = _as_optional_datetime(row[7]) or datetime.now(UTC)
    status = PacketStatus(_require_row_str(row[4], field_name="status"))
    queue_age_hours = max(
        0.0,
        round((datetime.now(UTC) - received_at_utc).total_seconds() / 3600, 2),
    )
    assignment_state = PacketAssignmentState(
        _as_optional_str(row[14]) or PacketAssignmentState.UNASSIGNED.value
    )

    return PacketQueueItem(
        packet_id=_require_row_str(row[0], field_name="packetId"),
        packet_name=_require_row_str(row[1], field_name="packetName"),
        source=DocumentSource(_require_row_str(row[2], field_name="source")),
        source_uri=_as_optional_str(row[3]),
        status=status,
        submitted_by=_as_optional_str(row[5]),
        received_at_utc=received_at_utc,
        updated_at_utc=_as_optional_datetime(row[9]) or datetime.now(UTC),
        document_count=_as_optional_int(row[10]) or 0,
        awaiting_review_document_count=_as_optional_int(row[11]) or 0,
        completed_document_count=_as_optional_int(row[12]) or 0,
        review_task_count=_as_optional_int(row[13]) or 0,
        assignment_state=assignment_state,
        assigned_user_email=_as_optional_str(row[15]),
        oldest_review_task_created_at_utc=_as_optional_datetime(row[16]),
        primary_document_id=_as_optional_str(row[17]),
        primary_file_name=_as_optional_str(row[18]),
        primary_issuer_name=_as_optional_str(row[19]),
        primary_issuer_category=IssuerCategory(
            _as_optional_str(row[20]) or IssuerCategory.UNKNOWN.value
        ),
        latest_job_stage_name=(
            ProcessingStageName(str(row[21])) if row[21] is not None else None
        ),
        latest_job_status=(
            ProcessingJobStatus(str(row[22])) if row[22] is not None else None
        ),
        classification_keys=_load_delimited_str_tuple(row[23]),
        document_type_keys=_load_delimited_str_tuple(row[24]),
        operator_note_count=_as_optional_int(row[25]) or 0,
        audit_event_count=_as_optional_int(row[26]) or 0,
        stage_name=get_stage_name_for_status(status),
        queue_age_hours=queue_age_hours,
    )


def _build_packet_document_record_from_row(
    row: tuple[object, ...],
) -> PacketDocumentRecord:
    """Build a packet-document record from SQL."""

    return PacketDocumentRecord(
        document_id=_require_row_str(row[0], field_name="documentId"),
        packet_id=_require_row_str(row[1], field_name="packetId"),
        file_name=_require_row_str(row[2], field_name="fileName"),
        content_type=_require_row_str(row[3], field_name="contentType"),
        source=DocumentSource(_require_row_str(row[4], field_name="source")),
        source_uri=_as_optional_str(row[5]),
        status=PacketStatus(_require_row_str(row[6], field_name="status")),
        issuer_name=_as_optional_str(row[7]),
        issuer_category=IssuerCategory(
            _require_row_str(row[8], field_name="issuerCategory")
        ),
        requested_prompt_profile_id=(
            PromptProfileId(str(row[9])) if row[9] is not None else None
        ),
        source_summary=_as_optional_str(row[10]),
        source_tags=_load_str_tuple(row[11]),
        account_candidates=_load_str_tuple(row[12]),
        document_text=_as_optional_str(row[13]),
        file_hash_sha256=_as_optional_str(row[14]),
        lineage=ArchiveDocumentLineage(
            parent_document_id=_as_optional_str(row[15]),
            source_asset_id=_as_optional_str(row[16]),
            archive_member_path=_as_optional_str(row[17]),
            archive_depth=_as_optional_int(row[18]) or 0,
        ),
        archive_preflight=ArchivePreflightResult.model_validate(
            _load_json_dict(row[19]).get("archivePreflight") or {}
        ),
        received_at_utc=_as_optional_datetime(row[20]) or datetime.now(UTC),
        created_at_utc=_as_optional_datetime(row[21]) or datetime.now(UTC),
        updated_at_utc=_as_optional_datetime(row[22]) or datetime.now(UTC),
    )


def _build_document_asset_record_from_row(
    row: tuple[object, ...],
) -> DocumentAssetRecord:
    """Build a document-asset record from SQL."""

    return DocumentAssetRecord(
        asset_id=_require_row_str(row[0], field_name="assetId"),
        packet_id=_require_row_str(row[1], field_name="packetId"),
        document_id=_require_row_str(row[2], field_name="documentId"),
        asset_role=_require_row_str(row[3], field_name="assetRole"),
        container_name=_require_row_str(row[4], field_name="containerName"),
        blob_name=_require_row_str(row[5], field_name="blobName"),
        content_type=_require_row_str(row[6], field_name="contentType"),
        content_length_bytes=_as_optional_int(row[7]) or 0,
        storage_uri=_require_row_str(row[8], field_name="storageUri"),
        created_at_utc=_as_optional_datetime(row[9]) or datetime.now(UTC),
    )


def _build_packet_event_record_from_row(
    row: tuple[object, ...],
) -> PacketEventRecord:
    """Build a packet-event record from SQL."""

    return PacketEventRecord(
        event_id=_as_optional_int(row[0]) or 1,
        packet_id=_require_row_str(row[1], field_name="packetId"),
        document_id=_as_optional_str(row[2]),
        event_type=_require_row_str(row[3], field_name="eventType"),
        event_payload=_load_json_dict(row[4]) or None,
        created_at_utc=_as_optional_datetime(row[5]) or datetime.now(UTC),
    )


def _build_processing_job_record_from_row(
    row: tuple[object, ...],
) -> ProcessingJobRecord:
    """Build a processing-job record from SQL."""

    return ProcessingJobRecord(
        job_id=_require_row_str(row[0], field_name="jobId"),
        packet_id=_require_row_str(row[1], field_name="packetId"),
        document_id=_as_optional_str(row[2]),
        stage_name=ProcessingStageName(
            _require_row_str(row[3], field_name="stageName")
        ),
        status=ProcessingJobStatus(_require_row_str(row[4], field_name="status")),
        attempt_number=_as_optional_int(row[5]) or 1,
        queued_at_utc=_as_optional_datetime(row[6]) or datetime.now(UTC),
        started_at_utc=_as_optional_datetime(row[7]),
        completed_at_utc=_as_optional_datetime(row[8]),
        error_code=_as_optional_str(row[9]),
        error_message=_as_optional_str(row[10]),
        created_at_utc=_as_optional_datetime(row[11]) or datetime.now(UTC),
        updated_at_utc=_as_optional_datetime(row[12]) or datetime.now(UTC),
    )


def _build_ocr_result_record_from_row(row: tuple[object, ...]) -> OcrResultRecord:
    """Build an OCR result record from SQL."""

    return OcrResultRecord(
        ocr_result_id=_require_row_str(row[0], field_name="ocrResultId"),
        packet_id=_require_row_str(row[1], field_name="packetId"),
        document_id=_require_row_str(row[2], field_name="documentId"),
        provider=_require_row_str(row[3], field_name="provider"),
        model_name=_as_optional_str(row[4]),
        page_count=_as_optional_int(row[5]) or 0,
        ocr_confidence=_as_optional_float(row[6]) or 0.0,
        text_storage_uri=_as_optional_str(row[7]),
        text_excerpt=_as_optional_str(row[8]),
        created_at_utc=_as_optional_datetime(row[9]) or datetime.now(UTC),
    )


def _build_extraction_result_record_from_row(
    row: tuple[object, ...],
) -> ExtractionResultRecord:
    """Build an extraction result record from SQL."""

    return ExtractionResultRecord(
        extraction_result_id=_require_row_str(
            row[0], field_name="extractionResultId"
        ),
        packet_id=_require_row_str(row[1], field_name="packetId"),
        document_id=_require_row_str(row[2], field_name="documentId"),
        provider=_require_row_str(row[3], field_name="provider"),
        model_name=_as_optional_str(row[4]),
        document_type=_as_optional_str(row[5]),
        prompt_profile_id=(PromptProfileId(str(row[6])) if row[6] else None),
        summary=_as_optional_str(row[7]),
        result_payload=_load_json_dict(row[8]),
        created_at_utc=_as_optional_datetime(row[9]) or datetime.now(UTC),
    )


def _build_classification_result_record_from_row(
    row: tuple[object, ...],
) -> ClassificationResultRecord:
    """Build a classification result record from SQL."""

    return ClassificationResultRecord(
        classification_result_id=_require_row_str(
            row[0], field_name="classificationResultId"
        ),
        packet_id=_require_row_str(row[1], field_name="packetId"),
        document_id=_require_row_str(row[2], field_name="documentId"),
        classification_id=_as_optional_str(row[3]),
        document_type_id=_as_optional_str(row[4]),
        result_source=ClassificationResultSource(
            _require_row_str(row[5], field_name="resultSource")
        ),
        confidence=_as_optional_float(row[6]) or 0.0,
        result_payload=_load_json_dict(row[7]),
        prompt_profile_id=(PromptProfileId(str(row[8])) if row[8] else None),
        created_at_utc=_as_optional_datetime(row[9]) or datetime.now(UTC),
    )


def _build_classification_prior_record_from_row(
    row: tuple[object, ...],
) -> ClassificationPriorRecord:
    """Build a classification-prior record from SQL."""

    return ClassificationPriorRecord(
        classification_prior_id=_require_row_str(
            row[0], field_name="classificationPriorId"
        ),
        packet_id=_as_optional_str(row[1]),
        source_document_id=_as_optional_str(row[2]),
        document_fingerprint=_as_optional_str(row[3]),
        source_fingerprint=_as_optional_str(row[4]),
        issuer_name_normalized=_as_optional_str(row[5]),
        account_id=_as_optional_str(row[6]),
        classification_id=_require_row_str(row[7], field_name="classificationId"),
        document_type_id=_require_row_str(row[8], field_name="documentTypeId"),
        prompt_profile_id=PromptProfileId(
            _require_row_str(row[9], field_name="promptProfileId")
        ),
        confidence_weight=_as_optional_float(row[10]) or 0.0,
        confirmed_by_user_id=_as_optional_str(row[11]),
        confirmed_by_email=_as_optional_str(row[12]),
        confirmed_at_utc=_as_optional_datetime(row[13]) or datetime.now(UTC),
        is_enabled=bool(row[14]),
        created_at_utc=_as_optional_datetime(row[15]) or datetime.now(UTC),
        updated_at_utc=_as_optional_datetime(row[16]) or datetime.now(UTC),
    )


def _build_review_task_record_from_row(row: tuple[object, ...]) -> ReviewTaskRecord:
    """Build a review-task record from SQL."""

    return ReviewTaskRecord(
        review_task_id=_require_row_str(row[0], field_name="reviewTaskId"),
        packet_id=_require_row_str(row[1], field_name="packetId"),
        document_id=_require_row_str(row[2], field_name="documentId"),
        assigned_user_id=_as_optional_str(row[3]),
        assigned_user_email=_as_optional_str(row[4]),
        status=PacketStatus(_require_row_str(row[5], field_name="status")),
        priority=ReviewTaskPriority(_require_row_str(row[6], field_name="priority")),
        selected_account_id=_as_optional_str(row[7]),
        reason_codes=_load_str_tuple(row[8]),
        notes_summary=_as_optional_str(row[9]),
        due_at_utc=_as_optional_datetime(row[10]),
        created_at_utc=_as_optional_datetime(row[11]) or datetime.now(UTC),
        updated_at_utc=_as_optional_datetime(row[12]) or datetime.now(UTC),
        row_version=(
            _as_optional_row_version(row[13]) if len(row) > 13 else None
        ),
    )


def _build_review_decision_record_from_row(
    row: tuple[object, ...],
) -> ReviewDecisionRecord:
    """Build a review-decision record from SQL."""

    return ReviewDecisionRecord(
        decision_id=_require_row_str(row[0], field_name="decisionId"),
        review_task_id=_require_row_str(row[1], field_name="reviewTaskId"),
        packet_id=_require_row_str(row[2], field_name="packetId"),
        document_id=_require_row_str(row[3], field_name="documentId"),
        decision_status=ReviewStatus(
            _require_row_str(row[4], field_name="decisionStatus")
        ),
        decision_reason_code=_as_optional_str(row[5]),
        selected_account_id=_as_optional_str(row[6]),
        review_notes=_as_optional_str(row[7]),
        decided_by_user_id=_as_optional_str(row[8]),
        decided_by_email=_as_optional_str(row[9]),
        decided_at_utc=_as_optional_datetime(row[10]) or datetime.now(UTC),
    )


def _build_operator_note_record_from_row(row: tuple[object, ...]) -> OperatorNoteRecord:
    """Build an operator-note record from SQL."""

    return OperatorNoteRecord(
        note_id=_require_row_str(row[0], field_name="noteId"),
        packet_id=_as_optional_str(row[1]),
        document_id=_as_optional_str(row[2]),
        review_task_id=_as_optional_str(row[3]),
        created_by_user_id=_as_optional_str(row[4]),
        created_by_email=_as_optional_str(row[5]),
        note_text=_require_row_str(row[6], field_name="noteText"),
        is_private=bool(row[7]),
        created_at_utc=_as_optional_datetime(row[8]) or datetime.now(UTC),
    )


def _build_audit_event_record_from_row(row: tuple[object, ...]) -> AuditEventRecord:
    """Build an audit-event record from SQL."""

    return AuditEventRecord(
        audit_event_id=_as_optional_int(row[0]) or 1,
        actor_user_id=_as_optional_str(row[1]),
        actor_email=_as_optional_str(row[2]),
        packet_id=_as_optional_str(row[3]),
        document_id=_as_optional_str(row[4]),
        review_task_id=_as_optional_str(row[5]),
        event_type=_require_row_str(row[6], field_name="eventType"),
        event_payload=_load_json_dict(row[7]) or None,
        created_at_utc=_as_optional_datetime(row[8]) or datetime.now(UTC),
    )


def _build_recommendation_run_record_from_row(
    row: tuple[object, ...],
) -> RecommendationRunRecord:
    """Build a recommendation-run record from SQL."""

    return RecommendationRunRecord(
        recommendation_run_id=_require_row_str(
            row[0], field_name="recommendationRunId"
        ),
        packet_id=_require_row_str(row[1], field_name="packetId"),
        document_id=_as_optional_str(row[2]),
        review_task_id=_as_optional_str(row[3]),
        prompt_profile_id=(PromptProfileId(str(row[4])) if row[4] else None),
        status=RecommendationRunStatus(
            _require_row_str(row[5], field_name="status")
        ),
        requested_by_user_id=_as_optional_str(row[6]),
        requested_by_email=_as_optional_str(row[7]),
        input_payload=_load_json_dict(row[8]),
        completed_at_utc=_as_optional_datetime(row[9]),
        created_at_utc=_as_optional_datetime(row[10]) or datetime.now(UTC),
        updated_at_utc=_as_optional_datetime(row[11]) or datetime.now(UTC),
    )


def _build_recommendation_result_record_from_row(
    row: tuple[object, ...],
) -> RecommendationResultRecord:
    """Build a recommendation-result record from SQL."""

    evidence_items = tuple(
        RecommendationEvidenceItem.model_validate(item)
        for item in _load_json_list(row[6])
        if isinstance(item, dict)
    )
    return RecommendationResultRecord(
        recommendation_result_id=_require_row_str(
            row[0], field_name="recommendationResultId"
        ),
        recommendation_run_id=_require_row_str(
            row[1], field_name="recommendationRunId"
        ),
        packet_id=_require_row_str(row[2], field_name="packetId"),
        document_id=_as_optional_str(row[3]),
        recommendation_kind=_require_row_str(
            row[4], field_name="recommendationKind"
        ),
        summary=_require_row_str(row[5], field_name="summary"),
        rationale_payload=_load_json_dict(row[6]),
        evidence_items=evidence_items,
        confidence=_as_optional_float(row[8]) or 0.0,
        advisory_text=_as_optional_str(row[9]),
        disposition=RecommendationDisposition(
            _require_row_str(row[10], field_name="disposition")
        ),
        reviewed_by_user_id=_as_optional_str(row[11]),
        reviewed_by_email=_as_optional_str(row[12]),
        reviewed_at_utc=_as_optional_datetime(row[13]),
        created_at_utc=_as_optional_datetime(row[14]) or datetime.now(UTC),
        updated_at_utc=_as_optional_datetime(row[15]) or datetime.now(UTC),
    )


class SqlOperatorStateRepository:
    """Persist and query the remaining Epic 1 operator-state contracts."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def is_configured(self) -> bool:
        """Return whether Azure SQL operator-state storage is configured."""

        return bool(self._settings.sql_connection_string)

    def _get_connection_string(self) -> str:
        """Return the configured SQL connection string or raise."""

        connection_string = self._settings.sql_connection_string
        if not connection_string:
            raise RuntimeError("Azure SQL operator-state storage is not configured")
        return connection_string

    def _execute_transaction(
        self,
        statements: tuple[tuple[str, tuple[object, ...]], ...],
    ) -> None:
        """Execute one or more SQL statements within a transaction."""

        connection_string = self._get_connection_string()
        with open_sql_connection(connection_string, autocommit=False) as connection:
            try:
                with connection.cursor() as cursor:
                    for statement, params in statements:
                        cursor.execute(statement, params)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def list_classification_definitions(
        self,
    ) -> tuple[ManagedClassificationDefinitionRecord, ...]:
        """Return the managed classification definitions from Azure SQL."""

        connection_string = self._get_connection_string()
        with open_sql_connection(connection_string, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        classificationId,
                        classificationKey,
                        displayName,
                        description,
                        isEnabled,
                        issuerCategory,
                        defaultPromptProfileId,
                        createdAtUtc,
                        updatedAtUtc
                    FROM dbo.ClassificationDefinitions
                    ORDER BY displayName ASC
                    """
                )
                rows = cursor.fetchall()

        return tuple(_build_classification_definition_from_row(row) for row in rows)

    def list_document_type_definitions(
        self,
    ) -> tuple[ManagedDocumentTypeDefinitionRecord, ...]:
        """Return the managed document-type definitions from Azure SQL."""

        connection_string = self._get_connection_string()
        with open_sql_connection(connection_string, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        documentTypeId,
                        documentTypeKey,
                        displayName,
                        description,
                        isEnabled,
                        classificationId,
                        defaultPromptProfileId,
                        requiredFieldsJson,
                        createdAtUtc,
                        updatedAtUtc
                    FROM dbo.DocumentTypeDefinitions
                    ORDER BY displayName ASC
                    """
                )
                rows = cursor.fetchall()

        return tuple(_build_document_type_definition_from_row(row) for row in rows)

    def list_prompt_profiles(self) -> tuple[ManagedPromptProfileRecord, ...]:
        """Return the managed prompt profiles from Azure SQL."""

        connection_string = self._get_connection_string()
        with open_sql_connection(connection_string, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        promptProfileId,
                        displayName,
                        description,
                        issuerCategory,
                        isEnabled,
                        createdAtUtc,
                        updatedAtUtc
                    FROM dbo.PromptProfiles
                    ORDER BY displayName ASC
                    """
                )
                rows = cursor.fetchall()

        return tuple(_build_prompt_profile_from_row(row) for row in rows)

    def list_prompt_profile_versions(self) -> tuple[PromptProfileVersionRecord, ...]:
        """Return the active prompt-profile versions from Azure SQL."""

        connection_string = self._get_connection_string()
        with open_sql_connection(connection_string, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        promptProfileVersionId,
                        promptProfileId,
                        versionNumber,
                        definitionJson,
                        isActive,
                        createdAtUtc
                    FROM dbo.PromptProfileVersions
                    ORDER BY promptProfileId ASC, versionNumber DESC
                    """
                )
                rows = cursor.fetchall()

        return tuple(_build_prompt_profile_version_from_row(row) for row in rows)

    def list_classification_priors(
        self,
        *,
        account_ids: tuple[str, ...] = (),
        document_fingerprint: str | None = None,
        source_fingerprint: str | None = None,
    ) -> tuple[ClassificationPriorRecord, ...]:
        """Return reusable classification priors that match the supplied hints."""

        clauses = ["isEnabled = 1"]
        params: list[object] = []
        if document_fingerprint:
            clauses.append("documentFingerprint = %s")
            params.append(document_fingerprint)
        if source_fingerprint:
            clauses.append("sourceFingerprint = %s")
            params.append(source_fingerprint)
        if account_ids:
            placeholder_list = _build_placeholder_list(len(account_ids))
            clauses.append(f"accountId IN ({placeholder_list})")
            params.extend(account_ids)

        query = f"""
            SELECT
                classificationPriorId,
                packetId,
                sourceDocumentId,
                documentFingerprint,
                sourceFingerprint,
                issuerNameNormalized,
                accountId,
                classificationId,
                documentTypeId,
                promptProfileId,
                confidenceWeight,
                confirmedByUserId,
                confirmedByEmail,
                confirmedAtUtc,
                isEnabled,
                createdAtUtc,
                updatedAtUtc
            FROM dbo.ClassificationPriors
            WHERE {' AND '.join(clauses)}
            ORDER BY confirmedAtUtc DESC
        """
        connection_string = self._get_connection_string()
        with open_sql_connection(connection_string, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()

        return tuple(_build_classification_prior_record_from_row(row) for row in rows)

    def list_packet_queue(
        self,
        request: PacketQueueListRequest,
        *,
        stage_statuses: tuple[PacketStatus, ...] = (),
    ) -> PacketQueueListResponse:
        """Return a filtered and paged packet queue from Azure SQL."""

        clauses = ["1 = 1"]
        params: list[object] = []
        if request.source is not None:
            clauses.append("p.source = %s")
            params.append(request.source.value)
        if request.status is not None:
            clauses.append("p.status = %s")
            params.append(request.status.value)
        if stage_statuses:
            placeholder_list = _build_placeholder_list(len(stage_statuses))
            clauses.append(f"p.status IN ({placeholder_list})")
            params.extend(status.value for status in stage_statuses)
        if request.classification_key:
            clauses.append(
                """
                EXISTS (
                    SELECT 1
                    FROM dbo.ClassificationResults classificationResult
                    INNER JOIN dbo.ClassificationDefinitions definition
                        ON definition.classificationId = classificationResult.classificationId
                    WHERE classificationResult.packetId = p.packetId
                        AND definition.classificationKey = %s
                )
                """
            )
            params.append(request.classification_key)
        if request.document_type_key:
            clauses.append(
                """
                EXISTS (
                    SELECT 1
                    FROM dbo.ClassificationResults classificationResult
                    INNER JOIN dbo.DocumentTypeDefinitions definition
                        ON definition.documentTypeId = classificationResult.documentTypeId
                    WHERE classificationResult.packetId = p.packetId
                        AND definition.documentTypeKey = %s
                )
                """
            )
            params.append(request.document_type_key)
        if request.assigned_user_email:
            normalized_assignment = request.assigned_user_email.strip().lower()
            if normalized_assignment == PacketAssignmentState.UNASSIGNED.value:
                clauses.append(
                    """
                    NOT EXISTS (
                        SELECT 1
                        FROM dbo.ReviewTasks reviewTask
                        WHERE reviewTask.packetId = p.packetId
                            AND reviewTask.assignedUserEmail IS NOT NULL
                            AND LTRIM(RTRIM(reviewTask.assignedUserEmail)) <> ''
                    )
                    """
                )
            else:
                clauses.append(
                    """
                    EXISTS (
                        SELECT 1
                        FROM dbo.ReviewTasks reviewTask
                        WHERE reviewTask.packetId = p.packetId
                            AND LOWER(reviewTask.assignedUserEmail) = %s
                    )
                    """
                )
                params.append(normalized_assignment)
        if request.min_queue_age_hours is not None:
            clauses.append("p.receivedAtUtc <= DATEADD(hour, -%s, SYSUTCDATETIME())")
            params.append(request.min_queue_age_hours)

        offset = (request.page - 1) * request.page_size
        query = f"""
            WITH FilteredPackets AS (
                SELECT
                    p.packetId,
                    p.packetName,
                    p.source,
                    p.sourceUri,
                    p.status,
                    p.submittedBy,
                    p.packetTagsJson,
                    p.receivedAtUtc,
                    p.createdAtUtc,
                    p.updatedAtUtc
                FROM dbo.Packets p
                WHERE {' AND '.join(clauses)}
            )
            SELECT
                packet.packetId,
                packet.packetName,
                packet.source,
                packet.sourceUri,
                packet.status,
                packet.submittedBy,
                packet.packetTagsJson,
                packet.receivedAtUtc,
                packet.createdAtUtc,
                packet.updatedAtUtc,
                COALESCE(documentSummary.documentCount, 0) AS documentCount,
                COALESCE(documentSummary.awaitingReviewDocumentCount, 0) AS awaitingReviewDocumentCount,
                COALESCE(documentSummary.completedDocumentCount, 0) AS completedDocumentCount,
                COALESCE(reviewSummary.reviewTaskCount, 0) AS reviewTaskCount,
                assignmentSummary.assignmentState,
                assignmentSummary.assignedUserEmail,
                reviewSummary.oldestReviewTaskCreatedAtUtc,
                primaryDocument.documentId,
                primaryDocument.fileName,
                primaryDocument.issuerName,
                primaryDocument.issuerCategory,
                latestJob.stageName,
                latestJob.status,
                classificationSummary.classificationKeys,
                documentTypeSummary.documentTypeKeys,
                COALESCE(operatorNoteSummary.operatorNoteCount, 0) AS operatorNoteCount,
                COALESCE(auditSummary.auditEventCount, 0) AS auditEventCount,
                COUNT(*) OVER() AS totalCount
            FROM FilteredPackets packet
            OUTER APPLY (
                SELECT
                    COUNT(*) AS documentCount,
                    SUM(CASE WHEN document.status = '{PacketStatus.AWAITING_REVIEW.value}' THEN 1 ELSE 0 END) AS awaitingReviewDocumentCount,
                    SUM(CASE WHEN document.status = '{PacketStatus.COMPLETED.value}' THEN 1 ELSE 0 END) AS completedDocumentCount
                FROM dbo.PacketDocuments document
                WHERE document.packetId = packet.packetId
            ) documentSummary
            OUTER APPLY (
                SELECT TOP 1
                    document.documentId,
                    document.fileName,
                    document.issuerName,
                    document.issuerCategory
                FROM dbo.PacketDocuments document
                WHERE document.packetId = packet.packetId
                ORDER BY document.createdAtUtc ASC, document.documentId ASC
            ) primaryDocument
            OUTER APPLY (
                SELECT TOP 1
                    job.stageName,
                    job.status
                FROM dbo.ProcessingJobs job
                WHERE job.packetId = packet.packetId
                ORDER BY COALESCE(job.updatedAtUtc, job.createdAtUtc) DESC,
                    job.createdAtUtc DESC,
                    job.jobId DESC
            ) latestJob
            OUTER APPLY (
                SELECT
                    COUNT(*) AS reviewTaskCount,
                    MIN(reviewTask.createdAtUtc) AS oldestReviewTaskCreatedAtUtc
                FROM dbo.ReviewTasks reviewTask
                WHERE reviewTask.packetId = packet.packetId
            ) reviewSummary
            OUTER APPLY (
                SELECT
                    CASE
                        WHEN COUNT(DISTINCT CASE WHEN reviewTask.assignedUserEmail IS NOT NULL
                            AND LTRIM(RTRIM(reviewTask.assignedUserEmail)) <> ''
                            THEN LOWER(reviewTask.assignedUserEmail) END) = 0
                            THEN '{PacketAssignmentState.UNASSIGNED.value}'
                        WHEN COUNT(DISTINCT CASE WHEN reviewTask.assignedUserEmail IS NOT NULL
                            AND LTRIM(RTRIM(reviewTask.assignedUserEmail)) <> ''
                            THEN LOWER(reviewTask.assignedUserEmail) END) = 1
                            THEN '{PacketAssignmentState.ASSIGNED.value}'
                        ELSE '{PacketAssignmentState.MIXED.value}'
                    END AS assignmentState,
                    CASE
                        WHEN COUNT(DISTINCT CASE WHEN reviewTask.assignedUserEmail IS NOT NULL
                            AND LTRIM(RTRIM(reviewTask.assignedUserEmail)) <> ''
                            THEN LOWER(reviewTask.assignedUserEmail) END) = 1
                            THEN MIN(LOWER(reviewTask.assignedUserEmail))
                        ELSE NULL
                    END AS assignedUserEmail
                FROM dbo.ReviewTasks reviewTask
                WHERE reviewTask.packetId = packet.packetId
            ) assignmentSummary
            OUTER APPLY (
                SELECT
                    STRING_AGG(classificationRow.classificationKey, '|') AS classificationKeys
                FROM (
                    SELECT DISTINCT definition.classificationKey
                    FROM dbo.ClassificationResults classificationResult
                    INNER JOIN dbo.ClassificationDefinitions definition
                        ON definition.classificationId = classificationResult.classificationId
                    WHERE classificationResult.packetId = packet.packetId
                        AND definition.classificationKey IS NOT NULL
                ) classificationRow
            ) classificationSummary
            OUTER APPLY (
                SELECT
                    STRING_AGG(documentTypeRow.documentTypeKey, '|') AS documentTypeKeys
                FROM (
                    SELECT DISTINCT definition.documentTypeKey
                    FROM dbo.ClassificationResults classificationResult
                    INNER JOIN dbo.DocumentTypeDefinitions definition
                        ON definition.documentTypeId = classificationResult.documentTypeId
                    WHERE classificationResult.packetId = packet.packetId
                        AND definition.documentTypeKey IS NOT NULL
                ) documentTypeRow
            ) documentTypeSummary
            OUTER APPLY (
                SELECT COUNT(*) AS operatorNoteCount
                FROM dbo.OperatorNotes operatorNote
                WHERE operatorNote.packetId = packet.packetId
            ) operatorNoteSummary
            OUTER APPLY (
                SELECT COUNT(*) AS auditEventCount
                FROM dbo.AuditEvents auditEvent
                WHERE auditEvent.packetId = packet.packetId
            ) auditSummary
            ORDER BY packet.receivedAtUtc DESC, packet.packetId DESC
            OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
        """
        params.extend((offset, request.page_size))

        connection_string = self._get_connection_string()
        with open_sql_connection(connection_string, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()

        items = tuple(_build_packet_queue_item_from_row(row) for row in rows)
        total_count = _as_optional_int(rows[0][27]) if rows else 0
        if total_count is None:
            total_count = 0

        return PacketQueueListResponse(
            items=items,
            page=request.page,
            page_size=request.page_size,
            total_count=total_count,
            has_more=total_count > offset + len(items),
        )

    def create_ocr_result(self, request: OcrResultCreateRequest) -> OcrResultRecord:
        """Persist one OCR result row."""

        record = OcrResultRecord(
            ocr_result_id=request.ocr_result_id or f"ocr_{uuid4().hex}",
            packet_id=request.packet_id,
            document_id=request.document_id,
            provider=request.provider,
            model_name=request.model_name,
            page_count=request.page_count,
            ocr_confidence=request.ocr_confidence,
            text_storage_uri=request.text_storage_uri,
            text_excerpt=request.text_excerpt,
            created_at_utc=datetime.now(UTC),
        )
        self._execute_transaction(
            (
                (
                    """
                    INSERT INTO dbo.OcrResults (
                        ocrResultId, packetId, documentId, provider, modelName,
                        pageCount, ocrConfidence, textStorageUri, textExcerpt,
                        createdAtUtc
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.ocr_result_id,
                        record.packet_id,
                        record.document_id,
                        record.provider,
                        record.model_name,
                        record.page_count,
                        record.ocr_confidence,
                        record.text_storage_uri,
                        record.text_excerpt,
                        record.created_at_utc,
                    ),
                ),
            )
        )
        return record

    def create_extraction_result(
        self,
        request: ExtractionResultCreateRequest,
    ) -> ExtractionResultRecord:
        """Persist one extraction result row."""

        result_payload = attach_content_controls(
            request.result_payload,
            retention_class="extracted_content",
            contains_sensitive_content=True,
        )

        record = ExtractionResultRecord(
            extraction_result_id=(
                request.extraction_result_id or f"ext_{uuid4().hex}"
            ),
            packet_id=request.packet_id,
            document_id=request.document_id,
            provider=request.provider,
            model_name=request.model_name,
            document_type=request.document_type,
            prompt_profile_id=request.prompt_profile_id,
            summary=request.summary,
            result_payload=result_payload,
            created_at_utc=datetime.now(UTC),
        )
        self._execute_transaction(
            (
                (
                    """
                    INSERT INTO dbo.ExtractionResults (
                        extractionResultId, packetId, documentId, provider, modelName,
                        documentType, promptProfileId, summary, resultJson, createdAtUtc
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.extraction_result_id,
                        record.packet_id,
                        record.document_id,
                        record.provider,
                        record.model_name,
                        record.document_type,
                        (
                            record.prompt_profile_id.value
                            if record.prompt_profile_id is not None
                            else None
                        ),
                        record.summary,
                        json.dumps(record.result_payload),
                        record.created_at_utc,
                    ),
                ),
            )
        )
        return record

    def create_classification_result(
        self,
        request: ClassificationResultCreateRequest,
    ) -> ClassificationResultRecord:
        """Persist one classification result row."""

        record = ClassificationResultRecord(
            classification_result_id=(
                request.classification_result_id or f"clsr_{uuid4().hex}"
            ),
            packet_id=request.packet_id,
            document_id=request.document_id,
            classification_id=request.classification_id,
            document_type_id=request.document_type_id,
            result_source=request.result_source,
            confidence=request.confidence,
            result_payload=request.result_payload,
            prompt_profile_id=request.prompt_profile_id,
            created_at_utc=datetime.now(UTC),
        )
        self._execute_transaction(
            (
                (
                    """
                    INSERT INTO dbo.ClassificationResults (
                        classificationResultId, packetId, documentId, classificationId,
                        documentTypeId, resultSource, confidence, resultJson,
                        promptProfileId, createdAtUtc
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.classification_result_id,
                        record.packet_id,
                        record.document_id,
                        record.classification_id,
                        record.document_type_id,
                        record.result_source.value,
                        record.confidence,
                        json.dumps(record.result_payload),
                        (
                            record.prompt_profile_id.value
                            if record.prompt_profile_id is not None
                            else None
                        ),
                        record.created_at_utc,
                    ),
                ),
            )
        )
        return record

    def create_classification_prior(
        self,
        request: ClassificationPriorCreateRequest,
    ) -> ClassificationPriorRecord:
        """Persist one reusable operator-confirmed classification prior."""

        now = datetime.now(UTC)
        record = ClassificationPriorRecord(
            classification_prior_id=(
                request.classification_prior_id or f"prior_{uuid4().hex}"
            ),
            packet_id=request.packet_id,
            source_document_id=request.source_document_id,
            document_fingerprint=request.document_fingerprint,
            source_fingerprint=request.source_fingerprint,
            issuer_name_normalized=request.issuer_name_normalized,
            account_id=request.account_id,
            classification_id=request.classification_id,
            document_type_id=request.document_type_id,
            prompt_profile_id=request.prompt_profile_id,
            confidence_weight=request.confidence_weight,
            confirmed_by_user_id=request.confirmed_by_user_id,
            confirmed_by_email=request.confirmed_by_email,
            confirmed_at_utc=request.confirmed_at_utc,
            is_enabled=True,
            created_at_utc=now,
            updated_at_utc=now,
        )
        self._execute_transaction(
            (
                (
                    """
                    INSERT INTO dbo.ClassificationPriors (
                        classificationPriorId, packetId, sourceDocumentId,
                        documentFingerprint, sourceFingerprint, issuerNameNormalized,
                        accountId, classificationId, documentTypeId, promptProfileId,
                        confidenceWeight, confirmedByUserId, confirmedByEmail,
                        confirmedAtUtc, isEnabled, createdAtUtc, updatedAtUtc
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        record.classification_prior_id,
                        record.packet_id,
                        record.source_document_id,
                        record.document_fingerprint,
                        record.source_fingerprint,
                        record.issuer_name_normalized,
                        record.account_id,
                        record.classification_id,
                        record.document_type_id,
                        record.prompt_profile_id.value,
                        record.confidence_weight,
                        record.confirmed_by_user_id,
                        record.confirmed_by_email,
                        record.confirmed_at_utc,
                        record.is_enabled,
                        record.created_at_utc,
                        record.updated_at_utc,
                    ),
                ),
            )
        )
        return record

    def persist_operator_confirmed_classification(
        self,
        *,
        classification_request: ClassificationResultCreateRequest,
        prior_request: ClassificationPriorCreateRequest,
    ) -> tuple[ClassificationResultRecord, ClassificationPriorRecord]:
        """Persist an operator-confirmed classification and its reusable prior."""

        classification_record = ClassificationResultRecord(
            classification_result_id=(
                classification_request.classification_result_id
                or f"clsr_{uuid4().hex}"
            ),
            packet_id=classification_request.packet_id,
            document_id=classification_request.document_id,
            classification_id=classification_request.classification_id,
            document_type_id=classification_request.document_type_id,
            result_source=ClassificationResultSource.OPERATOR_CONFIRMED,
            confidence=classification_request.confidence,
            result_payload=classification_request.result_payload,
            prompt_profile_id=classification_request.prompt_profile_id,
            created_at_utc=datetime.now(UTC),
        )
        now = datetime.now(UTC)
        prior_record = ClassificationPriorRecord(
            classification_prior_id=(
                prior_request.classification_prior_id or f"prior_{uuid4().hex}"
            ),
            packet_id=prior_request.packet_id,
            source_document_id=prior_request.source_document_id,
            document_fingerprint=prior_request.document_fingerprint,
            source_fingerprint=prior_request.source_fingerprint,
            issuer_name_normalized=prior_request.issuer_name_normalized,
            account_id=prior_request.account_id,
            classification_id=prior_request.classification_id,
            document_type_id=prior_request.document_type_id,
            prompt_profile_id=prior_request.prompt_profile_id,
            confidence_weight=prior_request.confidence_weight,
            confirmed_by_user_id=prior_request.confirmed_by_user_id,
            confirmed_by_email=prior_request.confirmed_by_email,
            confirmed_at_utc=prior_request.confirmed_at_utc,
            is_enabled=True,
            created_at_utc=now,
            updated_at_utc=now,
        )
        self._execute_transaction(
            (
                (
                    """
                    INSERT INTO dbo.ClassificationResults (
                        classificationResultId, packetId, documentId, classificationId,
                        documentTypeId, resultSource, confidence, resultJson,
                        promptProfileId, createdAtUtc
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        classification_record.classification_result_id,
                        classification_record.packet_id,
                        classification_record.document_id,
                        classification_record.classification_id,
                        classification_record.document_type_id,
                        classification_record.result_source.value,
                        classification_record.confidence,
                        json.dumps(classification_record.result_payload),
                        (
                            classification_record.prompt_profile_id.value
                            if classification_record.prompt_profile_id is not None
                            else None
                        ),
                        classification_record.created_at_utc,
                    ),
                ),
                (
                    """
                    INSERT INTO dbo.ClassificationPriors (
                        classificationPriorId, packetId, sourceDocumentId,
                        documentFingerprint, sourceFingerprint, issuerNameNormalized,
                        accountId, classificationId, documentTypeId, promptProfileId,
                        confidenceWeight, confirmedByUserId, confirmedByEmail,
                        confirmedAtUtc, isEnabled, createdAtUtc, updatedAtUtc
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        prior_record.classification_prior_id,
                        prior_record.packet_id,
                        prior_record.source_document_id,
                        prior_record.document_fingerprint,
                        prior_record.source_fingerprint,
                        prior_record.issuer_name_normalized,
                        prior_record.account_id,
                        prior_record.classification_id,
                        prior_record.document_type_id,
                        prior_record.prompt_profile_id.value,
                        prior_record.confidence_weight,
                        prior_record.confirmed_by_user_id,
                        prior_record.confirmed_by_email,
                        prior_record.confirmed_at_utc,
                        prior_record.is_enabled,
                        prior_record.created_at_utc,
                        prior_record.updated_at_utc,
                    ),
                ),
            )
        )
        return classification_record, prior_record

    def create_account_match_run(
        self,
        request: AccountMatchRunCreateRequest,
    ) -> AccountMatchRunRecord:
        """Persist one account-match run and its candidates."""

        record = AccountMatchRunRecord(
            match_run_id=request.match_run_id or f"match_{uuid4().hex}",
            packet_id=request.packet_id,
            document_id=request.document_id,
            status=request.status,
            selected_account_id=request.selected_account_id,
            rationale=request.rationale,
            candidates=request.candidates,
            created_at_utc=datetime.now(UTC),
        )
        statements: list[tuple[str, tuple[object, ...]]] = [
            (
                """
                INSERT INTO dbo.AccountMatchRuns (
                    matchRunId, packetId, documentId, status,
                    selectedAccountId, rationale, createdAtUtc
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record.match_run_id,
                    record.packet_id,
                    record.document_id,
                    record.status.value,
                    record.selected_account_id,
                    record.rationale,
                    record.created_at_utc,
                ),
            )
        ]
        for rank_order, candidate in enumerate(record.candidates, start=1):
            statements.append(
                (
                    """
                    INSERT INTO dbo.AccountMatchCandidates (
                        matchCandidateId, matchRunId, accountId, accountNumber,
                        debtorName, issuerName, matchedOnJson, score,
                        rankOrder, createdAtUtc
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        f"cand_{uuid4().hex}",
                        record.match_run_id,
                        candidate.account_id,
                        candidate.account_number,
                        candidate.debtor_name,
                        candidate.issuer_name,
                        json.dumps(list(candidate.matched_on)),
                        candidate.score,
                        rank_order,
                        record.created_at_utc,
                    ),
                )
            )
        self._execute_transaction(tuple(statements))
        return record

    def create_review_task(self, request: ReviewTaskCreateRequest) -> ReviewTaskRecord:
        """Persist one review task."""

        now = datetime.now(UTC)
        record = ReviewTaskRecord(
            review_task_id=request.review_task_id or f"task_{uuid4().hex}",
            packet_id=request.packet_id,
            document_id=request.document_id,
            assigned_user_id=request.assigned_user_id,
            assigned_user_email=request.assigned_user_email,
            status=request.status,
            priority=request.priority,
            selected_account_id=request.selected_account_id,
            reason_codes=request.reason_codes,
            notes_summary=request.notes_summary,
            due_at_utc=request.due_at_utc,
            created_at_utc=now,
            updated_at_utc=now,
        )
        self._execute_transaction(
            (
                (
                    """
                    INSERT INTO dbo.ReviewTasks (
                        reviewTaskId, packetId, documentId, assignedUserId,
                        assignedUserEmail, status, priority, selectedAccountId,
                        reasonCodesJson, notesSummary, dueAtUtc, createdAtUtc,
                        updatedAtUtc
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.review_task_id,
                        record.packet_id,
                        record.document_id,
                        record.assigned_user_id,
                        record.assigned_user_email,
                        record.status.value,
                        record.priority.value,
                        record.selected_account_id,
                        json.dumps(list(record.reason_codes)),
                        record.notes_summary,
                        record.due_at_utc,
                        record.created_at_utc,
                        record.updated_at_utc,
                    ),
                ),
            )
        )
        return record

    def create_review_decision(
        self,
        request: ReviewDecisionCreateRequest,
    ) -> ReviewDecisionRecord:
        """Persist one review decision."""

        record = ReviewDecisionRecord(
            decision_id=request.decision_id or f"decision_{uuid4().hex}",
            review_task_id=request.review_task_id,
            packet_id=request.packet_id,
            document_id=request.document_id,
            decision_status=request.decision_status,
            decision_reason_code=request.decision_reason_code,
            selected_account_id=request.selected_account_id,
            review_notes=request.review_notes,
            decided_by_user_id=request.decided_by_user_id,
            decided_by_email=request.decided_by_email,
            decided_at_utc=request.decided_at_utc,
        )
        self._execute_transaction(
            (
                (
                    """
                    INSERT INTO dbo.ReviewDecisions (
                        decisionId, reviewTaskId, packetId, documentId,
                        decisionStatus, decisionReasonCode, selectedAccountId,
                        reviewNotes, decidedByUserId, decidedByEmail, decidedAtUtc
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.decision_id,
                        record.review_task_id,
                        record.packet_id,
                        record.document_id,
                        record.decision_status.value,
                        record.decision_reason_code,
                        record.selected_account_id,
                        record.review_notes,
                        record.decided_by_user_id,
                        record.decided_by_email,
                        record.decided_at_utc,
                    ),
                ),
            )
        )
        return record

    def create_operator_note(
        self,
        request: OperatorNoteCreateRequest,
    ) -> OperatorNoteRecord:
        """Persist one operator note."""

        note_text = request.note_text
        if self._settings.mask_sensitive_history:
            note_text = mask_sensitive_text(note_text) or request.note_text

        record = OperatorNoteRecord(
            note_id=request.note_id or f"note_{uuid4().hex}",
            packet_id=request.packet_id,
            document_id=request.document_id,
            review_task_id=request.review_task_id,
            created_by_user_id=request.created_by_user_id,
            created_by_email=request.created_by_email,
            note_text=note_text,
            is_private=request.is_private,
            created_at_utc=request.created_at_utc,
        )
        self._execute_transaction(
            (
                (
                    """
                    INSERT INTO dbo.OperatorNotes (
                        noteId, packetId, documentId, reviewTaskId,
                        createdByUserId, createdByEmail, noteText, isPrivate,
                        createdAtUtc
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.note_id,
                        record.packet_id,
                        record.document_id,
                        record.review_task_id,
                        record.created_by_user_id,
                        record.created_by_email,
                        record.note_text,
                        record.is_private,
                        record.created_at_utc,
                    ),
                ),
            )
        )
        return record

    def create_audit_event(self, request: AuditEventCreateRequest) -> AuditEventRecord:
        """Persist one audit event."""

        event_payload = request.event_payload or None
        if self._settings.mask_sensitive_history:
            event_payload = mask_history_payload(
                request.event_payload,
                retention_class="audit_history",
            )

        record = AuditEventRecord(
            audit_event_id=1,
            actor_user_id=request.actor_user_id,
            actor_email=request.actor_email,
            packet_id=request.packet_id,
            document_id=request.document_id,
            review_task_id=request.review_task_id,
            event_type=request.event_type,
            event_payload=event_payload,
            created_at_utc=request.created_at_utc,
        )
        self._execute_transaction(
            (
                (
                    """
                    INSERT INTO dbo.AuditEvents (
                        actorUserId, actorEmail, packetId, documentId,
                        reviewTaskId, eventType, eventPayloadJson, createdAtUtc
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.actor_user_id,
                        record.actor_email,
                        record.packet_id,
                        record.document_id,
                        record.review_task_id,
                        record.event_type,
                        json.dumps(record.event_payload or {}),
                        record.created_at_utc,
                    ),
                ),
            )
        )
        return record

    def create_recommendation_run(
        self,
        request: RecommendationRunCreateRequest,
    ) -> RecommendationRunRecord:
        """Persist one recommendation run."""

        now = datetime.now(UTC)
        record = RecommendationRunRecord(
            recommendation_run_id=(
                request.recommendation_run_id or f"recrun_{uuid4().hex}"
            ),
            packet_id=request.packet_id,
            document_id=request.document_id,
            review_task_id=request.review_task_id,
            prompt_profile_id=request.prompt_profile_id,
            status=request.status,
            requested_by_user_id=request.requested_by_user_id,
            requested_by_email=request.requested_by_email,
            input_payload=request.input_payload,
            completed_at_utc=None,
            created_at_utc=now,
            updated_at_utc=now,
        )
        self._execute_transaction(
            (
                (
                    """
                    INSERT INTO dbo.RecommendationRuns (
                        recommendationRunId, packetId, documentId, reviewTaskId,
                        promptProfileId, status, requestedByUserId,
                        requestedByEmail, inputJson, completedAtUtc,
                        createdAtUtc, updatedAtUtc
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.recommendation_run_id,
                        record.packet_id,
                        record.document_id,
                        record.review_task_id,
                        (
                            record.prompt_profile_id.value
                            if record.prompt_profile_id is not None
                            else None
                        ),
                        record.status.value,
                        record.requested_by_user_id,
                        record.requested_by_email,
                        json.dumps(record.input_payload),
                        record.completed_at_utc,
                        record.created_at_utc,
                        record.updated_at_utc,
                    ),
                ),
            )
        )
        return record

    def create_recommendation_result(
        self,
        request: RecommendationResultCreateRequest,
    ) -> RecommendationResultRecord:
        """Persist one recommendation result."""

        now = datetime.now(UTC)
        record = RecommendationResultRecord(
            recommendation_result_id=(
                request.recommendation_result_id or f"recres_{uuid4().hex}"
            ),
            recommendation_run_id=request.recommendation_run_id,
            packet_id=request.packet_id,
            document_id=request.document_id,
            recommendation_kind=request.recommendation_kind,
            summary=request.summary,
            rationale_payload=request.rationale_payload,
            evidence_items=request.evidence_items,
            confidence=request.confidence,
            advisory_text=request.advisory_text,
            disposition=request.disposition,
            reviewed_by_user_id=request.reviewed_by_user_id,
            reviewed_by_email=request.reviewed_by_email,
            reviewed_at_utc=request.reviewed_at_utc,
            created_at_utc=now,
            updated_at_utc=now,
        )
        self._execute_transaction(
            (
                (
                    """
                    INSERT INTO dbo.RecommendationResults (
                        recommendationResultId, recommendationRunId, packetId,
                        documentId, recommendationKind, summary, rationaleJson,
                        evidenceJson, confidence, advisoryText, disposition,
                        reviewedByUserId, reviewedByEmail, reviewedAtUtc,
                        createdAtUtc, updatedAtUtc
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        record.recommendation_result_id,
                        record.recommendation_run_id,
                        record.packet_id,
                        record.document_id,
                        record.recommendation_kind,
                        record.summary,
                        json.dumps(record.rationale_payload),
                        json.dumps(
                            [
                                evidence_item.model_dump(mode="json")
                                for evidence_item in record.evidence_items
                            ]
                        ),
                        record.confidence,
                        record.advisory_text,
                        record.disposition.value,
                        record.reviewed_by_user_id,
                        record.reviewed_by_email,
                        record.reviewed_at_utc,
                        record.created_at_utc,
                        record.updated_at_utc,
                    ),
                ),
            )
        )
        return record

    def get_packet_workspace_snapshot_for_review_task(
        self,
        review_task_id: str,
    ) -> PacketWorkspaceSnapshot:
        """Return the packet workspace snapshot that owns one review task."""

        connection_string = self._get_connection_string()
        with open_sql_connection(connection_string, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT TOP 1 packetId
                    FROM dbo.ReviewTasks
                    WHERE reviewTaskId = %s
                    """,
                    (review_task_id,),
                )
                row = cursor.fetchone()

        if row is None:
            raise RuntimeError(f"Review task '{review_task_id}' was not found.")

        packet_id = _require_row_str(row[0], field_name="packetId")
        return self.get_packet_workspace_snapshot(packet_id)

    def get_packet_workspace_snapshot(self, packet_id: str) -> PacketWorkspaceSnapshot:
        """Return the full packet workspace snapshot from Azure SQL."""

        connection_string = self._get_connection_string()
        with open_sql_connection(connection_string, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        packetId, packetName, source, sourceUri, status,
                        submittedBy, packetTagsJson, receivedAtUtc, createdAtUtc,
                        updatedAtUtc, packetFingerprint, sourceFingerprint,
                        duplicateOfPacketId, duplicateSignalsJson
                    FROM dbo.Packets
                    WHERE packetId = %s
                    """,
                    (packet_id,),
                )
                packet_row = cursor.fetchone()
                if packet_row is None:
                    raise RuntimeError(f"Packet '{packet_id}' could not be loaded.")

                cursor.execute(
                    """
                    SELECT
                        documentId, packetId, fileName, contentType, source,
                        sourceUri, status, issuerName, issuerCategory,
                        requestedPromptProfileId, sourceSummary, sourceTagsJson,
                        accountCandidatesJson, documentText, fileHashSha256,
                        parentDocumentId, sourceAssetId, archiveMemberPath,
                        archiveDepth,
                        (
                            SELECT TOP 1 eventPayloadJson
                            FROM dbo.PacketEvents
                            WHERE documentId = dbo.PacketDocuments.documentId
                                AND eventType IN (
                                    'document.manual_intake.archive_detected',
                                    'document.manual_intake.quarantined',
                                    'document.manual_intake.staged'
                                )
                            ORDER BY createdAtUtc DESC
                        ) AS eventPayloadJson,
                        receivedAtUtc, createdAtUtc, updatedAtUtc
                    FROM dbo.PacketDocuments
                    WHERE packetId = %s
                    ORDER BY createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                document_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        assetId, packetId, documentId, assetRole, containerName,
                        blobName, contentType, contentLengthBytes, storageUri,
                        createdAtUtc
                    FROM dbo.DocumentAssets
                    WHERE packetId = %s
                    ORDER BY createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                asset_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        eventId, packetId, documentId, eventType,
                        eventPayloadJson, createdAtUtc
                    FROM dbo.PacketEvents
                    WHERE packetId = %s
                    ORDER BY createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                event_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        jobId, packetId, documentId, stageName, status,
                        attemptNumber, queuedAtUtc, startedAtUtc, completedAtUtc,
                        errorCode, errorMessage, createdAtUtc, updatedAtUtc
                    FROM dbo.ProcessingJobs
                    WHERE packetId = %s
                    ORDER BY createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                job_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        ocrResultId, packetId, documentId, provider, modelName,
                        pageCount, ocrConfidence, textStorageUri, textExcerpt,
                        createdAtUtc
                    FROM dbo.OcrResults
                    WHERE packetId = %s
                    ORDER BY createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                ocr_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        extractionResultId, packetId, documentId, provider,
                        modelName, documentType, promptProfileId, summary,
                        resultJson, createdAtUtc
                    FROM dbo.ExtractionResults
                    WHERE packetId = %s
                    ORDER BY createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                extraction_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        classificationResultId, packetId, documentId,
                        classificationId, documentTypeId, resultSource,
                        confidence, resultJson, promptProfileId, createdAtUtc
                    FROM dbo.ClassificationResults
                    WHERE packetId = %s
                    ORDER BY createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                classification_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        matchRunId, packetId, documentId, status,
                        selectedAccountId, rationale, createdAtUtc
                    FROM dbo.AccountMatchRuns
                    WHERE packetId = %s
                    ORDER BY createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                match_run_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        matchRunId, accountId, accountNumber, debtorName,
                        issuerName, matchedOnJson, score, rankOrder
                    FROM dbo.AccountMatchCandidates
                    WHERE matchRunId IN (
                        SELECT matchRunId
                        FROM dbo.AccountMatchRuns
                        WHERE packetId = %s
                    )
                    ORDER BY matchRunId ASC, rankOrder ASC
                    """,
                    (packet_id,),
                )
                candidate_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        reviewTaskId, packetId, documentId, assignedUserId,
                        assignedUserEmail, status, priority, selectedAccountId,
                        reasonCodesJson, notesSummary, dueAtUtc, createdAtUtc,
                        updatedAtUtc, rowVersion
                    FROM dbo.ReviewTasks
                    WHERE packetId = %s
                    ORDER BY createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                review_task_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        decisionId, reviewTaskId, packetId, documentId,
                        decisionStatus, decisionReasonCode, selectedAccountId,
                        reviewNotes, decidedByUserId, decidedByEmail,
                        decidedAtUtc
                    FROM dbo.ReviewDecisions
                    WHERE packetId = %s
                    ORDER BY decidedAtUtc ASC
                    """,
                    (packet_id,),
                )
                review_decision_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        noteId, packetId, documentId, reviewTaskId,
                        createdByUserId, createdByEmail, noteText,
                        isPrivate, createdAtUtc
                    FROM dbo.OperatorNotes
                    WHERE packetId = %s
                    ORDER BY createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                operator_note_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        auditEventId, actorUserId, actorEmail, packetId,
                        documentId, reviewTaskId, eventType, eventPayloadJson,
                        createdAtUtc
                    FROM dbo.AuditEvents
                    WHERE packetId = %s
                    ORDER BY createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                audit_event_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        recommendationRunId, packetId, documentId, reviewTaskId,
                        promptProfileId, status, requestedByUserId,
                        requestedByEmail, inputJson, completedAtUtc,
                        createdAtUtc, updatedAtUtc
                    FROM dbo.RecommendationRuns
                    WHERE packetId = %s
                    ORDER BY createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                recommendation_run_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT
                        recommendationResultId, recommendationRunId, packetId,
                        documentId, recommendationKind, summary, rationaleJson,
                        evidenceJson, confidence, advisoryText, disposition,
                        reviewedByUserId, reviewedByEmail, reviewedAtUtc,
                        createdAtUtc, updatedAtUtc
                    FROM dbo.RecommendationResults
                    WHERE packetId = %s
                    ORDER BY createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                recommendation_result_rows = cursor.fetchall()

        candidate_map: dict[str, list[AccountMatchCandidate]] = {}
        for row in candidate_rows:
            match_run_id = _require_row_str(row[0], field_name="matchRunId")
            candidate_map.setdefault(match_run_id, []).append(
                AccountMatchCandidate(
                    account_id=_require_row_str(row[1], field_name="accountId"),
                    account_number=_as_optional_str(row[2]),
                    debtor_name=_as_optional_str(row[3]),
                    issuer_name=_as_optional_str(row[4]),
                    matched_on=_load_str_tuple(row[5]),
                    score=_as_optional_float(row[6]) or 0.0,
                )
            )

        account_match_runs = tuple(
            AccountMatchRunRecord(
                match_run_id=_require_row_str(row[0], field_name="matchRunId"),
                packet_id=_require_row_str(row[1], field_name="packetId"),
                document_id=_require_row_str(row[2], field_name="documentId"),
                status=AccountMatchStatus(
                    _require_row_str(row[3], field_name="status")
                ),
                selected_account_id=_as_optional_str(row[4]),
                rationale=_as_optional_str(row[5]),
                created_at_utc=_as_optional_datetime(row[6]) or datetime.now(UTC),
                candidates=tuple(
                    candidate_map.get(
                        _require_row_str(row[0], field_name="matchRunId"),
                        [],
                    )
                ),
            )
            for row in match_run_rows
        )

        recommendation_results: list[RecommendationResultRecord] = []
        for row in recommendation_result_rows:
            evidence_items = tuple(
                RecommendationEvidenceItem.model_validate(item)
                for item in _load_json_list(row[7])
                if isinstance(item, dict)
            )
            recommendation_results.append(
                RecommendationResultRecord(
                    recommendation_result_id=_require_row_str(
                        row[0], field_name="recommendationResultId"
                    ),
                    recommendation_run_id=_require_row_str(
                        row[1], field_name="recommendationRunId"
                    ),
                    packet_id=_require_row_str(row[2], field_name="packetId"),
                    document_id=_as_optional_str(row[3]),
                    recommendation_kind=_require_row_str(
                        row[4], field_name="recommendationKind"
                    ),
                    summary=_require_row_str(row[5], field_name="summary"),
                    rationale_payload=_load_json_dict(row[6]),
                    evidence_items=evidence_items,
                    confidence=_as_optional_float(row[8]) or 0.0,
                    advisory_text=_as_optional_str(row[9]),
                    disposition=RecommendationDisposition(
                        _require_row_str(row[10], field_name="disposition")
                    ),
                    reviewed_by_user_id=_as_optional_str(row[11]),
                    reviewed_by_email=_as_optional_str(row[12]),
                    reviewed_at_utc=_as_optional_datetime(row[13]),
                    created_at_utc=_as_optional_datetime(row[14])
                    or datetime.now(UTC),
                    updated_at_utc=_as_optional_datetime(row[15])
                    or datetime.now(UTC),
                )
            )

        return PacketWorkspaceSnapshot(
            packet=_build_packet_record_from_row(packet_row),
            documents=tuple(
                _build_packet_document_record_from_row(row) for row in document_rows
            ),
            document_assets=tuple(
                _build_document_asset_record_from_row(row) for row in asset_rows
            ),
            packet_events=tuple(
                _build_packet_event_record_from_row(row) for row in event_rows
            ),
            processing_jobs=tuple(
                _build_processing_job_record_from_row(row) for row in job_rows
            ),
            ocr_results=tuple(
                _build_ocr_result_record_from_row(row) for row in ocr_rows
            ),
            extraction_results=tuple(
                _build_extraction_result_record_from_row(row)
                for row in extraction_rows
            ),
            classification_results=tuple(
                _build_classification_result_record_from_row(row)
                for row in classification_rows
            ),
            account_match_runs=account_match_runs,
            review_tasks=tuple(
                _build_review_task_record_from_row(row)
                for row in review_task_rows
            ),
            review_decisions=tuple(
                _build_review_decision_record_from_row(row)
                for row in review_decision_rows
            ),
            operator_notes=tuple(
                _build_operator_note_record_from_row(row)
                for row in operator_note_rows
            ),
            audit_events=tuple(
                _build_audit_event_record_from_row(row)
                for row in audit_event_rows
            ),
            recommendation_runs=tuple(
                _build_recommendation_run_record_from_row(row)
                for row in recommendation_run_rows
            ),
            recommendation_results=tuple(recommendation_results),
        )