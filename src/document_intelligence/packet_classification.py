"""Packet-level classification execution and OCR handoff helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from openai import AzureOpenAI

from document_intelligence.models import (
    ClassificationPriorRecord,
    ClassificationResultSource,
    DocumentAssetRecord,
    DocumentIngestionRequest,
    IssuerCategory,
    ManagedClassificationDefinitionRecord,
    ManagedDocumentTypeDefinitionRecord,
    PacketClassificationExecutionDocumentResult,
    PacketClassificationExecutionResponse,
    PacketDocumentRecord,
    PacketStatus,
    PacketWorkspaceSnapshot,
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStageName,
    ProfileSelectionMode,
    PromptProfileId,
    ReviewReason,
    ReviewTaskPriority,
    SafetyIssue,
    SafetyIssueSeverity,
)
from document_intelligence.operator_state import SqlOperatorStateRepository
from document_intelligence.orchestration import normalize_request
from document_intelligence.profiles import select_prompt_profile
from document_intelligence.safety import serialize_safety_issues
from document_intelligence.settings import AppSettings
from document_intelligence.utils.sql import open_sql_connection


class PacketClassificationConfigurationError(RuntimeError):
    """Raised when packet classification execution cannot run."""


@dataclass(frozen=True)
class _ResolvedClassification:
    """Resolved packet classification result before SQL persistence."""

    classification_id: str | None
    confidence: float
    document_type_id: str | None
    prompt_profile_id: PromptProfileId | None
    result_payload: dict[str, Any]
    result_source: ClassificationResultSource
    safety_issues: tuple[SafetyIssue, ...] = ()


@dataclass(frozen=True)
class _PendingClassificationExecution:
    """A queued packet document ready to persist classification execution."""

    classification_job_id: str
    classification_result_id: str | None
    document: PacketDocumentRecord
    ocr_job_id: str | None
    resolved_classification: _ResolvedClassification | None
    review_notes_summary: str | None
    review_reason_codes: tuple[str, ...]
    review_task_id: str | None
    status: PacketStatus


def _serialize_prompt_profile_id(
    prompt_profile_id: PromptProfileId | None,
) -> str | None:
    """Return the prompt-profile id when one is available."""

    return prompt_profile_id.value if prompt_profile_id is not None else None


def _serialize_prompt_profile_selection(
    request: DocumentIngestionRequest,
) -> dict[str, Any]:
    """Return the prompt-profile selection payload used for routing."""

    prompt_profile = select_prompt_profile(request)
    return {
        "candidateProfiles": [
            {
                "issuerCategory": candidate.issuer_category.value,
                "profileId": candidate.profile_id.value,
                "rationale": list(candidate.rationale),
                "score": candidate.score,
            }
            for candidate in prompt_profile.candidate_profiles
        ],
        "documentTypeHints": list(prompt_profile.document_type_hints),
        "issuerCategory": prompt_profile.issuer_category.value,
        "keywordHints": list(prompt_profile.keyword_hints),
        "primaryProfileId": prompt_profile.primary_profile_id.value,
        "promptFocus": list(prompt_profile.prompt_focus),
        "selectionMode": prompt_profile.selection_mode.value,
    }


def _resolve_selection_confidence(
    *,
    selection_mode: ProfileSelectionMode,
    top_candidate_score: int,
) -> float:
    """Return a stage-execution confidence derived from prompt-profile routing."""

    if selection_mode == ProfileSelectionMode.EXPLICIT:
        return 0.99

    if selection_mode == ProfileSelectionMode.HEURISTIC:
        return max(0.7, min(top_candidate_score / 100, 0.92))

    return 0.55


def _build_definition_lookup_by_classification_id(
    classification_definitions: tuple[ManagedClassificationDefinitionRecord, ...],
) -> dict[str, ManagedClassificationDefinitionRecord]:
    """Return enabled classification definitions keyed by id."""

    return {
        definition.classification_id: definition
        for definition in classification_definitions
        if definition.is_enabled
    }


def _build_definition_lookup_by_document_type_id(
    document_type_definitions: tuple[ManagedDocumentTypeDefinitionRecord, ...],
) -> dict[str, ManagedDocumentTypeDefinitionRecord]:
    """Return enabled document-type definitions keyed by id."""

    return {
        definition.document_type_id: definition
        for definition in document_type_definitions
        if definition.is_enabled
    }


def _build_classification_review_issue(
    *,
    code: ReviewReason,
    message: str,
) -> SafetyIssue:
    """Build one blocking safety issue for classification review handoff."""

    return SafetyIssue(
        code=code.value,
        message=message,
        severity=SafetyIssueSeverity.BLOCKING,
        stage_name=ProcessingStageName.REVIEW,
    )


def _resolve_classification_safety_issues(
    *,
    classification_definitions: tuple[ManagedClassificationDefinitionRecord, ...],
    document_type_definitions: tuple[ManagedDocumentTypeDefinitionRecord, ...],
    request: DocumentIngestionRequest,
    resolved_classification: _ResolvedClassification,
    settings: AppSettings,
) -> tuple[SafetyIssue, ...]:
    """Return blocking safety issues that require classification review."""

    if resolved_classification.result_source != ClassificationResultSource.AI:
        return ()

    issues_by_code: dict[str, SafetyIssue] = {}
    prompt_profile = select_prompt_profile(request)
    classification_by_id = _build_definition_lookup_by_classification_id(
        classification_definitions
    )
    document_type_by_id = _build_definition_lookup_by_document_type_id(
        document_type_definitions
    )
    classification_definition = classification_by_id.get(
        resolved_classification.classification_id or ""
    )
    document_type_definition = document_type_by_id.get(
        resolved_classification.document_type_id or ""
    )

    if (
        resolved_classification.confidence
        < settings.classification_drift_confidence_threshold
    ):
        issues_by_code[ReviewReason.CLASSIFICATION_DRIFT.value] = (
            _build_classification_review_issue(
                code=ReviewReason.CLASSIFICATION_DRIFT,
                message=(
                    "The fallback AI classification confidence was below the "
                    "configured drift threshold and must be confirmed by an "
                    "operator before OCR continues."
                ),
            )
        )

    if (
        classification_definition is not None
        and classification_definition.default_prompt_profile_id is not None
        and classification_definition.default_prompt_profile_id
        != prompt_profile.primary_profile_id
    ):
        issues_by_code[ReviewReason.CLASSIFICATION_DRIFT.value] = (
            _build_classification_review_issue(
                code=ReviewReason.CLASSIFICATION_DRIFT,
                message=(
                    "The fallback AI classification conflicts with the managed "
                    "prompt-profile routing and was paused for operator review."
                ),
            )
        )

    if (
        document_type_definition is not None
        and document_type_definition.default_prompt_profile_id is not None
        and document_type_definition.default_prompt_profile_id
        != prompt_profile.primary_profile_id
    ):
        issues_by_code[ReviewReason.CLASSIFICATION_DRIFT.value] = (
            _build_classification_review_issue(
                code=ReviewReason.CLASSIFICATION_DRIFT,
                message=(
                    "The fallback AI document type conflicts with the managed "
                    "prompt-profile routing and was paused for operator review."
                ),
            )
        )

    if (
        classification_definition is not None
        and classification_definition.issuer_category != IssuerCategory.UNKNOWN
        and request.issuer_category != IssuerCategory.UNKNOWN
        and classification_definition.issuer_category != request.issuer_category
    ):
        issues_by_code[ReviewReason.CLASSIFICATION_DRIFT.value] = (
            _build_classification_review_issue(
                code=ReviewReason.CLASSIFICATION_DRIFT,
                message=(
                    "The fallback AI classification conflicts with the request "
                    "issuer category and was paused for operator review."
                ),
            )
        )

    return tuple(issues_by_code.values())


def _build_review_notes_summary(
    *,
    review_reason_codes: tuple[str, ...],
    safety_issues: tuple[SafetyIssue, ...] = (),
    fallback_message: str | None = None,
) -> str:
    """Build the review-task summary for classification review handoff."""

    if safety_issues:
        return " ".join(issue.message for issue in safety_issues)

    if fallback_message is not None:
        return fallback_message

    return (
        "Classification paused for operator review: "
        + ", ".join(review_reason_codes)
        + "."
    )


def _build_review_required_execution(
    *,
    classification_job_id: str,
    document: PacketDocumentRecord,
    resolved_classification: _ResolvedClassification | None,
    review_notes_summary: str,
    review_reason_codes: tuple[str, ...],
) -> _PendingClassificationExecution:
    """Build one classification execution that pauses for operator review."""

    return _PendingClassificationExecution(
        classification_job_id=classification_job_id,
        classification_result_id=(
            f"clsr_{uuid4().hex}" if resolved_classification is not None else None
        ),
        document=document,
        ocr_job_id=None,
        resolved_classification=resolved_classification,
        review_notes_summary=review_notes_summary,
        review_reason_codes=review_reason_codes,
        review_task_id=f"task_{uuid4().hex}",
        status=PacketStatus.AWAITING_REVIEW,
    )


def _build_ocr_handoff_execution(
    *,
    classification_job_id: str,
    document: PacketDocumentRecord,
    resolved_classification: _ResolvedClassification,
) -> _PendingClassificationExecution:
    """Build one classification execution that queues OCR."""

    return _PendingClassificationExecution(
        classification_job_id=classification_job_id,
        classification_result_id=f"clsr_{uuid4().hex}",
        document=document,
        ocr_job_id=f"job_{uuid4().hex}",
        resolved_classification=resolved_classification,
        review_notes_summary=None,
        review_reason_codes=(),
        review_task_id=None,
        status=PacketStatus.OCR_RUNNING,
    )


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


def _select_rule_classification(
    *,
    classification_definitions: tuple[ManagedClassificationDefinitionRecord, ...],
    document_type_definitions: tuple[ManagedDocumentTypeDefinitionRecord, ...],
    request: DocumentIngestionRequest,
) -> _ResolvedClassification | None:
    """Resolve the classification contract directly from prompt-profile rules."""

    prompt_profile = select_prompt_profile(request)
    top_candidate_score = (
        prompt_profile.candidate_profiles[0].score
        if prompt_profile.candidate_profiles
        else 0
    )
    classification_definition = next(
        (
            definition
            for definition in classification_definitions
            if definition.is_enabled
            and definition.default_prompt_profile_id
            == prompt_profile.primary_profile_id
        ),
        None,
    )
    if classification_definition is None:
        classification_definition = next(
            (
                definition
                for definition in classification_definitions
                if definition.is_enabled
                and definition.issuer_category == prompt_profile.issuer_category
            ),
            None,
        )

    if classification_definition is None:
        return None

    document_type_definition = next(
        (
            definition
            for definition in document_type_definitions
            if definition.is_enabled
            and definition.default_prompt_profile_id
            == prompt_profile.primary_profile_id
        ),
        None,
    )
    if document_type_definition is None:
        document_type_definition = next(
            (
                definition
                for definition in document_type_definitions
                if definition.is_enabled
                and definition.classification_id
                == classification_definition.classification_id
            ),
            None,
        )

    if document_type_definition is None:
        return None

    return _ResolvedClassification(
        classification_id=classification_definition.classification_id,
        confidence=_resolve_selection_confidence(
            selection_mode=prompt_profile.selection_mode,
            top_candidate_score=top_candidate_score,
        ),
        document_type_id=document_type_definition.document_type_id,
        prompt_profile_id=prompt_profile.primary_profile_id,
        result_payload={
            "classificationExecution": {
                "classificationKey": classification_definition.classification_key,
                "documentTypeKey": document_type_definition.document_type_key,
                "executionMode": "rule_contract_match",
            },
            "lineage": request.source_uri,
            "promptProfileSelection": _serialize_prompt_profile_selection(request),
            "requiredFields": list(document_type_definition.required_fields),
            "sourceHints": {
                "issuerCategory": request.issuer_category.value,
                "issuerName": request.issuer_name,
                "sourceSummary": request.source_summary,
                "sourceTags": list(request.source_tags),
            },
        },
        result_source=ClassificationResultSource.RULE,
    )


def _select_prior_classification(
    *,
    classification_definitions: tuple[ManagedClassificationDefinitionRecord, ...],
    classification_priors: tuple[ClassificationPriorRecord, ...],
    document_type_definitions: tuple[ManagedDocumentTypeDefinitionRecord, ...],
    request: DocumentIngestionRequest,
) -> _ResolvedClassification | None:
    """Resolve the classification contract from previously learned priors."""

    enabled_classifications = {
        definition.classification_id: definition
        for definition in classification_definitions
        if definition.is_enabled
    }
    enabled_document_types = {
        definition.document_type_id: definition
        for definition in document_type_definitions
        if definition.is_enabled
    }
    valid_priors = [
        prior
        for prior in classification_priors
        if prior.classification_id in enabled_classifications
        and prior.document_type_id in enabled_document_types
        and enabled_document_types[prior.document_type_id].classification_id
        == prior.classification_id
    ]
    if not valid_priors:
        return None

    selected_prior = max(
        valid_priors,
        key=lambda prior: (prior.confidence_weight, prior.confirmed_at_utc),
    )
    selected_document_type = enabled_document_types[selected_prior.document_type_id]
    return _ResolvedClassification(
        classification_id=selected_prior.classification_id,
        confidence=max(0.0, min(1.0, selected_prior.confidence_weight)),
        document_type_id=selected_prior.document_type_id,
        prompt_profile_id=selected_prior.prompt_profile_id,
        result_payload={
            "classificationExecution": {
                "classificationKey": (
                    enabled_classifications[selected_prior.classification_id].classification_key
                ),
                "documentTypeKey": selected_document_type.document_type_key,
                "executionMode": "classification_prior_reuse",
            },
            "priorReuse": {
                "accountId": selected_prior.account_id,
                "classificationPriorId": selected_prior.classification_prior_id,
                "issuerNameNormalized": selected_prior.issuer_name_normalized,
                "sourceDocumentId": selected_prior.source_document_id,
            },
            "requiredFields": list(selected_document_type.required_fields),
            "sourceHints": {
                "issuerCategory": request.issuer_category.value,
                "issuerName": request.issuer_name,
                "sourceSummary": request.source_summary,
                "sourceTags": list(request.source_tags),
            },
        },
        result_source=ClassificationResultSource.PRIOR_REUSE,
    )


def _build_ai_classification_prompt(
    *,
    classification_definitions: tuple[ManagedClassificationDefinitionRecord, ...],
    document_type_definitions: tuple[ManagedDocumentTypeDefinitionRecord, ...],
    request: DocumentIngestionRequest,
) -> str:
    """Build the JSON prompt sent to Azure OpenAI for classification fallback."""

    payload = {
        "document": {
            "file_name": request.file_name,
            "issuer_category": request.issuer_category.value,
            "issuer_name": request.issuer_name,
            "source_summary": request.source_summary,
            "source_tags": list(request.source_tags),
            "source_uri": request.source_uri,
        },
        "classification_options": [
            {
                "classification_id": definition.classification_id,
                "classification_key": definition.classification_key,
                "default_prompt_profile_id": (
                    definition.default_prompt_profile_id.value
                    if definition.default_prompt_profile_id is not None
                    else None
                ),
                "description": definition.description,
                "display_name": definition.display_name,
                "issuer_category": definition.issuer_category.value,
            }
            for definition in classification_definitions
            if definition.is_enabled
        ],
        "document_type_options": [
            {
                "classification_id": definition.classification_id,
                "default_prompt_profile_id": (
                    definition.default_prompt_profile_id.value
                    if definition.default_prompt_profile_id is not None
                    else None
                ),
                "description": definition.description,
                "display_name": definition.display_name,
                "document_type_id": definition.document_type_id,
                "document_type_key": definition.document_type_key,
                "required_fields": list(definition.required_fields),
            }
            for definition in document_type_definitions
            if definition.is_enabled
        ],
    }
    return (
        "Select the best classification_id and document_type_id for the packet "
        "document below. Respond only with JSON using this shape: "
        '{"classification_id":"string","document_type_id":"string",'
        '"confidence":0.0,"rationale":"string"}.\n\n'
        f"{json.dumps(payload, indent=2)}"
    )


def _select_ai_classification(
    *,
    classification_definitions: tuple[ManagedClassificationDefinitionRecord, ...],
    document_type_definitions: tuple[ManagedDocumentTypeDefinitionRecord, ...],
    request: DocumentIngestionRequest,
    settings: AppSettings,
) -> _ResolvedClassification | None:
    """Use Azure OpenAI when contract rules cannot classify the document."""

    if not (
        settings.azure_openai_endpoint
        and settings.azure_openai_api_key
        and settings.azure_openai_deployment
    ):
        return None

    client = AzureOpenAI(
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        azure_endpoint=settings.azure_openai_endpoint,
    )
    response = client.chat.completions.create(
        model=settings.azure_openai_deployment,
        response_format={"type": "json_object"},
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": (
                    "You classify debt-relief packet documents before OCR-driven "
                    "extraction. Respond only with valid JSON."
                ),
            },
            {
                "role": "user",
                "content": _build_ai_classification_prompt(
                    classification_definitions=classification_definitions,
                    document_type_definitions=document_type_definitions,
                    request=request,
                ),
            },
        ],
    )
    payload = json.loads(response.choices[0].message.content or "{}")
    classification_id = str(payload.get("classification_id") or "").strip() or None
    document_type_id = str(payload.get("document_type_id") or "").strip() or None
    if classification_id is None or document_type_id is None:
        return None

    classification_definition = next(
        (
            definition
            for definition in classification_definitions
            if definition.classification_id == classification_id
            and definition.is_enabled
        ),
        None,
    )
    document_type_definition = next(
        (
            definition
            for definition in document_type_definitions
            if definition.document_type_id == document_type_id and definition.is_enabled
        ),
        None,
    )
    if classification_definition is None or document_type_definition is None:
        return None
    if (
        document_type_definition.classification_id
        != classification_definition.classification_id
    ):
        return None

    prompt_profile = select_prompt_profile(request)
    confidence_value = payload.get("confidence", 0.5)
    try:
        confidence = max(0.0, min(1.0, float(confidence_value)))
    except (TypeError, ValueError):
        confidence = 0.5

    return _ResolvedClassification(
        classification_id=classification_definition.classification_id,
        confidence=confidence,
        document_type_id=document_type_definition.document_type_id,
        prompt_profile_id=prompt_profile.primary_profile_id,
        result_payload={
            "classificationExecution": {
                "classificationKey": classification_definition.classification_key,
                "documentTypeKey": document_type_definition.document_type_key,
                "executionMode": "azure_openai_fallback",
                "rationale": str(payload.get("rationale") or "").strip() or None,
            },
            "promptProfileSelection": _serialize_prompt_profile_selection(request),
            "requiredFields": list(document_type_definition.required_fields),
            "sourceHints": {
                "issuerCategory": request.issuer_category.value,
                "issuerName": request.issuer_name,
                "sourceSummary": request.source_summary,
                "sourceTags": list(request.source_tags),
            },
        },
        result_source=ClassificationResultSource.AI,
    )


def _resolve_classification(
    *,
    classification_definitions: tuple[ManagedClassificationDefinitionRecord, ...],
    classification_priors: tuple[ClassificationPriorRecord, ...],
    document_type_definitions: tuple[ManagedDocumentTypeDefinitionRecord, ...],
    request: DocumentIngestionRequest,
    settings: AppSettings,
) -> _ResolvedClassification:
    """Resolve the final classification contract for one queued document."""

    prior_match = _select_prior_classification(
        classification_definitions=classification_definitions,
        classification_priors=classification_priors,
        document_type_definitions=document_type_definitions,
        request=request,
    )
    if prior_match is not None:
        return prior_match

    rule_match = _select_rule_classification(
        classification_definitions=classification_definitions,
        document_type_definitions=document_type_definitions,
        request=request,
    )
    if rule_match is not None:
        return rule_match

    ai_match = _select_ai_classification(
        classification_definitions=classification_definitions,
        document_type_definitions=document_type_definitions,
        request=request,
        settings=settings,
    )
    if ai_match is not None:
        return ai_match

    raise RuntimeError(
        "Document "
        f"'{request.document_id}' could not be classified into a managed "
        "contract."
    )


def _resolve_packet_handoff(
    *,
    processed_statuses: dict[str, PacketStatus],
    snapshot: PacketWorkspaceSnapshot,
) -> tuple[PacketStatus, ProcessingStageName]:
    """Return the packet status after classification has queued OCR work."""

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

    if any(status == PacketStatus.OCR_RUNNING for status in processed_statuses.values()):
        return PacketStatus.OCR_RUNNING, ProcessingStageName.OCR

    if any(
        latest_jobs.get(document.document_id) is not None
        and latest_jobs[document.document_id].stage_name
        == ProcessingStageName.CLASSIFICATION
        and latest_jobs[document.document_id].status != ProcessingJobStatus.SUCCEEDED
        and document.document_id not in processed_statuses
        for document in snapshot.documents
    ):
        return PacketStatus.CLASSIFYING, ProcessingStageName.CLASSIFICATION

    return snapshot.packet.status, ProcessingStageName.OCR


def _insert_review_task(
    cursor: Any,
    *,
    execution: _PendingClassificationExecution,
    packet_id: str,
) -> None:
    """Persist one classification-driven review task when required."""

    if execution.review_task_id is None:
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
            json.dumps(list(execution.review_reason_codes)),
            execution.review_notes_summary,
        ),
    )


def _persist_classification_handoff(
    *,
    packet_id: str,
    next_stage: ProcessingStageName,
    packet_status: PacketStatus,
    pending_executions: tuple[_PendingClassificationExecution, ...],
    settings: AppSettings,
) -> None:
    """Persist classification completion and queue OCR for the packet."""

    if not pending_executions:
        return

    first_packet_id = pending_executions[0].document.packet_id
    if packet_id != first_packet_id:
        raise RuntimeError(
            "Pending execution packet ids do not match the target packet."
        )

    connection_string = settings.sql_connection_string
    if not connection_string:
        raise PacketClassificationConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    with open_sql_connection(connection_string, autocommit=False) as connection:
        try:
            with connection.cursor() as cursor:
                for execution in pending_executions:
                    cursor.execute(
                        """
                        UPDATE dbo.ProcessingJobs
                        SET
                            status = %s,
                            startedAtUtc = COALESCE(startedAtUtc, SYSUTCDATETIME()),
                            updatedAtUtc = SYSUTCDATETIME()
                        WHERE jobId = %s
                        """,
                        (
                            ProcessingJobStatus.RUNNING.value,
                            execution.classification_job_id,
                        ),
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
                            execution.document.document_id,
                            "document.classification.started",
                            json.dumps(
                                _build_classification_started_event_payload(
                                    execution
                                )
                            ),
                        ),
                    )
                    if (
                        execution.resolved_classification is not None
                        and execution.classification_result_id is not None
                    ):
                        cursor.execute(
                            """
                            INSERT INTO dbo.ClassificationResults (
                                classificationResultId,
                                packetId,
                                documentId,
                                classificationId,
                                documentTypeId,
                                resultSource,
                                confidence,
                                resultJson,
                                promptProfileId,
                                createdAtUtc
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, SYSUTCDATETIME())
                            """,
                            (
                                execution.classification_result_id,
                                packet_id,
                                execution.document.document_id,
                                execution.resolved_classification.classification_id,
                                execution.resolved_classification.document_type_id,
                                execution.resolved_classification.result_source.value,
                                execution.resolved_classification.confidence,
                                json.dumps(
                                    execution.resolved_classification.result_payload
                                ),
                                _serialize_prompt_profile_id(
                                    execution.resolved_classification.prompt_profile_id
                                ),
                            ),
                        )
                    cursor.execute(
                        """
                        UPDATE dbo.ProcessingJobs
                        SET
                            status = %s,
                            completedAtUtc = SYSUTCDATETIME(),
                            updatedAtUtc = SYSUTCDATETIME()
                        WHERE jobId = %s
                        """,
                        (
                            ProcessingJobStatus.SUCCEEDED.value,
                            execution.classification_job_id,
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
                            execution.status.value,
                            execution.document.document_id,
                        ),
                    )
                    if execution.review_task_id is None and execution.ocr_job_id is not None:
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
                                execution.ocr_job_id,
                                packet_id,
                                execution.document.document_id,
                                ProcessingStageName.OCR.value,
                                ProcessingJobStatus.QUEUED.value,
                            ),
                        )
                    if execution.resolved_classification is not None:
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
                                execution.document.document_id,
                                "document.classification.completed",
                                json.dumps(
                                    _build_classification_completed_event_payload(
                                        execution
                                    )
                                ),
                            ),
                        )
                    if execution.review_task_id is not None:
                        _insert_review_task(
                            cursor,
                            execution=execution,
                            packet_id=packet_id,
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
                                execution.document.document_id,
                                "document.classification.review_required",
                                json.dumps(
                                    _build_classification_review_required_event_payload(
                                        execution
                                    )
                                ),
                            ),
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
                                execution.document.document_id,
                                "document.review_task.created",
                                json.dumps(
                                    _build_review_task_created_event_payload(execution)
                                ),
                            ),
                        )
                        continue

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
                            execution.document.document_id,
                            "document.ocr.queued",
                            json.dumps(_build_ocr_queued_event_payload(execution)),
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
                    (packet_status.value, packet_id),
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
                        "packet.classification.executed",
                        json.dumps(
                            {
                                "executedDocumentCount": len(pending_executions),
                                "nextStage": next_stage.value,
                                "status": packet_status.value,
                            }
                        ),
                    ),
                )

            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _build_classification_started_event_payload(
    execution: _PendingClassificationExecution,
) -> dict[str, Any]:
    """Return the event payload for a started classification job."""

    return {
        "classificationJobId": execution.classification_job_id,
        "stageName": ProcessingStageName.CLASSIFICATION.value,
        "status": ProcessingJobStatus.RUNNING.value,
    }


def _build_classification_completed_event_payload(
    execution: _PendingClassificationExecution,
) -> dict[str, Any]:
    """Return the event payload for a completed classification job."""

    if execution.resolved_classification is None:
        raise RuntimeError(
            "Classification completed payload requires a resolved classification."
        )

    return {
        "classificationId": execution.resolved_classification.classification_id,
        "classificationJobId": execution.classification_job_id,
        "classificationResultId": execution.classification_result_id,
        "confidence": execution.resolved_classification.confidence,
        "documentTypeId": execution.resolved_classification.document_type_id,
        "promptProfileId": _serialize_prompt_profile_id(
            execution.resolved_classification.prompt_profile_id
        ),
        "resultSource": execution.resolved_classification.result_source.value,
        "reviewTaskId": execution.review_task_id,
        "safetyIssues": serialize_safety_issues(
            execution.resolved_classification.safety_issues
        ),
        "status": execution.status.value,
    }


def _build_classification_review_required_event_payload(
    execution: _PendingClassificationExecution,
) -> dict[str, Any]:
    """Return the event payload when classification requires operator review."""

    safety_issues = ()
    if execution.resolved_classification is not None:
        safety_issues = execution.resolved_classification.safety_issues

    return {
        "classificationJobId": execution.classification_job_id,
        "classificationResultId": execution.classification_result_id,
        "reasonCodes": list(execution.review_reason_codes),
        "reviewTaskId": execution.review_task_id,
        "safetyIssues": serialize_safety_issues(safety_issues),
        "stageName": ProcessingStageName.REVIEW.value,
        "status": execution.status.value,
        "summary": execution.review_notes_summary,
    }


def _build_review_task_created_event_payload(
    execution: _PendingClassificationExecution,
) -> dict[str, Any]:
    """Return the event payload for a classification-created review task."""

    safety_issues = ()
    if execution.resolved_classification is not None:
        safety_issues = execution.resolved_classification.safety_issues

    return {
        "priority": ReviewTaskPriority.HIGH.value,
        "reasonCodes": list(execution.review_reason_codes),
        "reviewTaskId": execution.review_task_id,
        "safetyIssues": serialize_safety_issues(safety_issues),
        "stageName": ProcessingStageName.REVIEW.value,
        "status": PacketStatus.AWAITING_REVIEW.value,
        "summary": execution.review_notes_summary,
    }


def _build_ocr_queued_event_payload(
    execution: _PendingClassificationExecution,
) -> dict[str, Any]:
    """Return the event payload for an OCR handoff."""

    if execution.ocr_job_id is None:
        raise RuntimeError("OCR queued payload requires a queued OCR job id.")

    return {
        "classificationResultId": execution.classification_result_id,
        "ocrJobId": execution.ocr_job_id,
        "stageName": ProcessingStageName.OCR.value,
        "status": ProcessingJobStatus.QUEUED.value,
    }


def execute_packet_classification_stage(
    packet_id: str,
    settings: AppSettings,
) -> PacketClassificationExecutionResponse:
    """Execute queued packet classification work and queue OCR handoff."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        raise PacketClassificationConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    snapshot = repository.get_packet_workspace_snapshot(packet_id)
    classification_definitions = repository.list_classification_definitions()
    document_type_definitions = repository.list_document_type_definitions()
    latest_jobs = _select_latest_jobs_by_document(snapshot.processing_jobs)
    asset_by_document_id = _select_primary_asset_by_document(snapshot.document_assets)
    pending_executions: list[_PendingClassificationExecution] = []
    skipped_document_ids: list[str] = []

    for document in snapshot.documents:
        latest_job = latest_jobs.get(document.document_id)
        if latest_job is None:
            skipped_document_ids.append(document.document_id)
            continue

        if (
            latest_job.stage_name != ProcessingStageName.CLASSIFICATION
            or latest_job.status != ProcessingJobStatus.QUEUED
            or document.status != PacketStatus.CLASSIFYING
        ):
            skipped_document_ids.append(document.document_id)
            continue

        request = _build_document_request(
            asset_by_document_id=asset_by_document_id,
            document=document,
            packet_source_uri=snapshot.packet.source_uri
            or f"manual://packets/{snapshot.packet.packet_id}",
        )
        classification_priors = _list_classification_priors(
            repository=repository,
            document=document,
            packet_source_fingerprint=snapshot.packet.source_fingerprint,
        )
        try:
            resolved_classification = _resolve_classification(
                classification_definitions=classification_definitions,
                classification_priors=classification_priors,
                document_type_definitions=document_type_definitions,
                request=request,
                settings=settings,
            )
        except RuntimeError as error:
            pending_executions.append(
                _build_review_required_execution(
                    classification_job_id=latest_job.job_id,
                    document=document,
                    resolved_classification=None,
                    review_notes_summary=_build_review_notes_summary(
                        review_reason_codes=(
                            ReviewReason.UNSEEN_DOCUMENT_TYPE.value,
                        ),
                        fallback_message=str(error),
                    ),
                    review_reason_codes=(
                        ReviewReason.UNSEEN_DOCUMENT_TYPE.value,
                    ),
                )
            )
            continue

        safety_issues = _resolve_classification_safety_issues(
            classification_definitions=classification_definitions,
            document_type_definitions=document_type_definitions,
            request=request,
            resolved_classification=resolved_classification,
            settings=settings,
        )
        if safety_issues:
            guarded_classification = _ResolvedClassification(
                classification_id=resolved_classification.classification_id,
                confidence=resolved_classification.confidence,
                document_type_id=resolved_classification.document_type_id,
                prompt_profile_id=resolved_classification.prompt_profile_id,
                result_payload={
                    **resolved_classification.result_payload,
                    "safetyIssues": serialize_safety_issues(safety_issues),
                },
                result_source=resolved_classification.result_source,
                safety_issues=safety_issues,
            )
            pending_executions.append(
                _build_review_required_execution(
                    classification_job_id=latest_job.job_id,
                    document=document,
                    resolved_classification=guarded_classification,
                    review_notes_summary=_build_review_notes_summary(
                        review_reason_codes=tuple(
                            issue.code for issue in safety_issues
                        ),
                        safety_issues=safety_issues,
                    ),
                    review_reason_codes=tuple(issue.code for issue in safety_issues),
                )
            )
            continue

        pending_executions.append(
            _build_ocr_handoff_execution(
                classification_job_id=latest_job.job_id,
                document=document,
                resolved_classification=resolved_classification,
            )
        )

    packet_status, next_stage = _resolve_packet_handoff(
        processed_statuses={
            execution.document.document_id: execution.status
            for execution in pending_executions
        },
        snapshot=snapshot,
    )
    _persist_classification_handoff(
        packet_id=packet_id,
        next_stage=next_stage,
        packet_status=packet_status,
        pending_executions=tuple(pending_executions),
        settings=settings,
    )

    return PacketClassificationExecutionResponse(
        executed_document_count=len(pending_executions),
        next_stage=next_stage,
        packet_id=packet_id,
        processed_documents=tuple(
            PacketClassificationExecutionDocumentResult(
                classification_id=(
                    execution.resolved_classification.classification_id
                    if execution.resolved_classification is not None
                    else None
                ),
                classification_job_id=execution.classification_job_id,
                classification_result_id=execution.classification_result_id,
                document_id=execution.document.document_id,
                document_type_id=(
                    execution.resolved_classification.document_type_id
                    if execution.resolved_classification is not None
                    else None
                ),
                ocr_job_id=execution.ocr_job_id,
                packet_id=packet_id,
                prompt_profile_id=(
                    execution.resolved_classification.prompt_profile_id
                    if execution.resolved_classification is not None
                    else None
                ),
                result_source=(
                    execution.resolved_classification.result_source
                    if execution.resolved_classification is not None
                    else None
                ),
                review_task_id=execution.review_task_id,
                status=execution.status,
            )
            for execution in pending_executions
        ),
        skipped_document_ids=tuple(skipped_document_ids),
        status=packet_status,
    )


def _list_classification_priors(
    *,
    repository: SqlOperatorStateRepository,
    document: PacketDocumentRecord,
    packet_source_fingerprint: str | None,
) -> tuple[ClassificationPriorRecord, ...]:
    """Return candidate priors for one packet document ordered by specificity."""

    seen_prior_ids: set[str] = set()
    collected_priors: list[ClassificationPriorRecord] = []
    lookup_specs = (
        (document.account_candidates, document.file_hash_sha256, None),
        ((), document.file_hash_sha256, None),
        (document.account_candidates, None, packet_source_fingerprint),
        ((), None, packet_source_fingerprint),
    )
    for account_ids, document_fingerprint, source_fingerprint in lookup_specs:
        if (
            not account_ids
            and document_fingerprint is None
            and source_fingerprint is None
        ):
            continue

        for prior in repository.list_classification_priors(
            account_ids=account_ids,
            document_fingerprint=document_fingerprint,
            source_fingerprint=source_fingerprint,
        ):
            if prior.classification_prior_id in seen_prior_ids:
                continue

            seen_prior_ids.add(prior.classification_prior_id)
            collected_priors.append(prior)

    return tuple(collected_priors)
