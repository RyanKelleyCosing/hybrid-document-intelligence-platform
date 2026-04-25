"""Packet-level recommendation execution and completion helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from document_intelligence.models import (
    AccountMatchRunRecord,
    ClassificationResultRecord,
    ClassificationResultSource,
    DocumentAssetRecord,
    ExtractedField,
    ExtractionResultRecord,
    OcrResultRecord,
    PacketDocumentRecord,
    PacketRecommendationExecutionDocumentResult,
    PacketRecommendationExecutionResponse,
    PacketStatus,
    PacketWorkspaceSnapshot,
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStageName,
    RecommendationDisposition,
    RecommendationEvidenceItem,
    RecommendationRunStatus,
    ReviewReason,
    ReviewTaskPriority,
    SafetyIssue,
    SafetyIssueSeverity,
)
from document_intelligence.operator_contracts import build_recommendation_contract
from document_intelligence.operator_state import SqlOperatorStateRepository
from document_intelligence.safety import serialize_safety_issues
from document_intelligence.settings import AppSettings
from document_intelligence.utils.sql import open_sql_connection


class PacketRecommendationConfigurationError(RuntimeError):
    """Raised when packet recommendation execution cannot run."""


@dataclass(frozen=True)
class _ResolvedRecommendation:
    """Resolved recommendation data for one queued packet document."""

    advisory_text: str
    confidence: float
    disposition: RecommendationDisposition
    evidence_items: tuple[RecommendationEvidenceItem, ...]
    recommendation_kind: str
    rationale_payload: dict[str, Any]
    summary: str
    safety_issues: tuple[SafetyIssue, ...] = ()


@dataclass(frozen=True)
class _PendingRecommendationExecution:
    """One queued recommendation job ready for persistence."""

    account_match_run: AccountMatchRunRecord | None
    classification_prior_id: str | None
    classification_result: ClassificationResultRecord | None
    document: PacketDocumentRecord
    extraction_result: ExtractionResultRecord
    ocr_result: OcrResultRecord | None
    recommendation_job_id: str
    recommendation_result_id: str
    recommendation_run_id: str
    resolved_recommendation: _ResolvedRecommendation
    review_task_id: str | None
    source_asset: DocumentAssetRecord | None


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


def _select_latest_extraction_results_by_document(
    extraction_results: tuple[ExtractionResultRecord, ...],
) -> dict[str, ExtractionResultRecord]:
    """Return the latest persisted extraction result for each document."""

    latest_results: dict[str, ExtractionResultRecord] = {}
    for result in extraction_results:
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


def _normalize_text(value: str | None) -> str | None:
    """Normalize free text for reusable packet hints."""

    if value is None:
        return None

    normalized_value = " ".join(value.strip().lower().split())
    return normalized_value or None


def _resolve_selected_account_id(
    document: PacketDocumentRecord,
    account_match_run: AccountMatchRunRecord | None,
) -> str | None:
    """Return the best available selected account id for recommendation."""

    if account_match_run is not None and account_match_run.selected_account_id:
        return account_match_run.selected_account_id

    if len(document.account_candidates) == 1:
        return document.account_candidates[0]

    return None


def _extract_fields_from_result(
    extraction_result: ExtractionResultRecord,
) -> tuple[ExtractedField, ...]:
    """Return extracted fields persisted inside one extraction result."""

    raw_fields = extraction_result.result_payload.get("extractedFields", [])
    if not isinstance(raw_fields, list):
        return ()

    extracted_fields: list[ExtractedField] = []
    for raw_field in raw_fields:
        if not isinstance(raw_field, dict):
            continue

        extracted_fields.append(ExtractedField.model_validate(raw_field))

    return tuple(extracted_fields)


def _build_field_lookup(
    extracted_fields: tuple[ExtractedField, ...],
) -> dict[str, str]:
    """Return extracted fields indexed by lower-cased name."""

    return {field.name.strip().lower(): field.value for field in extracted_fields}


def _build_packet_field_values_by_name(
    extraction_results: tuple[ExtractionResultRecord, ...],
) -> dict[str, set[str]]:
    """Return normalized extracted-field values observed across the packet."""

    field_values_by_name: dict[str, set[str]] = {}
    for extraction_result in extraction_results:
        for field in _extract_fields_from_result(extraction_result):
            normalized_name = field.name.strip().lower()
            normalized_value = _normalize_text(field.value)
            if not normalized_name or normalized_value is None:
                continue

            field_values_by_name.setdefault(normalized_name, set()).add(
                normalized_value
            )

    return field_values_by_name


def _build_packet_document_types(
    extraction_results: tuple[ExtractionResultRecord, ...],
) -> set[str]:
    """Return normalized document types observed across the packet."""

    packet_document_types: set[str] = set()
    for extraction_result in extraction_results:
        document_type = _normalize_text(extraction_result.document_type)
        if document_type is not None:
            packet_document_types.add(document_type)

    return packet_document_types


def _load_required_fields_from_classification_result(
    classification_result: ClassificationResultRecord | None,
) -> tuple[str, ...]:
    """Return normalized required fields persisted with the classification result."""

    if classification_result is None:
        return ()

    raw_required_fields = classification_result.result_payload.get("requiredFields")
    if not isinstance(raw_required_fields, list):
        return ()

    required_fields: list[str] = []
    for raw_field in raw_required_fields:
        if not isinstance(raw_field, str):
            continue

        normalized_field = raw_field.strip().lower()
        if normalized_field:
            required_fields.append(normalized_field)

    return tuple(required_fields)


def _build_supported_recommendation_field_names(
    *,
    classification_result: ClassificationResultRecord | None,
    contract: Any,
    settings: AppSettings,
) -> set[str]:
    """Return supported extracted-field names for recommendation evidence."""

    supported_field_names = {
        field_name.strip().lower()
        for field_name in contract.supported_field_names
        if field_name.strip()
    }
    supported_field_names.update(
        field_name.strip().lower()
        for field_name in contract.conflict_field_names
        if field_name.strip()
    )
    supported_field_names.update(
        field_name.strip().lower()
        for field_name in settings.required_fields
        if field_name.strip()
    )
    supported_field_names.update(
        _load_required_fields_from_classification_result(classification_result)
    )
    return supported_field_names


def _build_recommendation_safety_issue(
    *,
    code: ReviewReason,
    message: str,
) -> SafetyIssue:
    """Build one blocking recommendation guardrail issue."""

    return SafetyIssue(
        code=code.value,
        message=message,
        severity=SafetyIssueSeverity.BLOCKING,
        stage_name=ProcessingStageName.REVIEW,
    )


def _resolve_recommendation_safety_issues(
    *,
    classification_result: ClassificationResultRecord | None,
    contract: Any,
    confidence: float,
    evidence_items: tuple[RecommendationEvidenceItem, ...],
    extracted_fields: tuple[ExtractedField, ...],
    packet_document_types: set[str],
    packet_field_values_by_name: dict[str, set[str]],
    settings: AppSettings,
    supported_recommendation_field_names: set[str],
) -> tuple[SafetyIssue, ...]:
    """Return blocking recommendation issues that require operator review."""

    issues_by_code: dict[str, SafetyIssue] = {}
    evidence_kinds = {item.evidence_kind for item in evidence_items}
    required_evidence_kinds = set(contract.required_evidence_kinds)

    if not required_evidence_kinds.issubset(evidence_kinds):
        issues_by_code[ReviewReason.RECOMMENDATION_GUARDRAIL.value] = (
            _build_recommendation_safety_issue(
                code=ReviewReason.RECOMMENDATION_GUARDRAIL,
                message=(
                    "The recommendation is missing one or more required evidence "
                    "items and was routed to operator review."
                ),
            )
        )

    if confidence < settings.recommendation_guardrail_confidence_threshold:
        issues_by_code[ReviewReason.RECOMMENDATION_GUARDRAIL.value] = (
            _build_recommendation_safety_issue(
                code=ReviewReason.RECOMMENDATION_GUARDRAIL,
                message=(
                    "The recommendation confidence fell below the configured "
                    "guardrail threshold and requires operator review."
                ),
            )
        )

    conflicting_fields = sorted(
        {
            field.name.strip().lower()
            for field in extracted_fields
            if field.name.strip().lower() in contract.conflict_field_names
            and len(packet_field_values_by_name.get(field.name.strip().lower(), set()))
            > 1
        }
    )
    if conflicting_fields:
        issues_by_code[ReviewReason.CONFLICTING_PACKET_EVIDENCE.value] = (
            _build_recommendation_safety_issue(
                code=ReviewReason.CONFLICTING_PACKET_EVIDENCE,
                message=(
                    "Packet documents disagree on key evidence fields "
                    f"({', '.join(conflicting_fields)}) and require operator "
                    "review before recommendation acceptance."
                ),
            )
        )

    unsupported_fields = sorted(
        {
            field.name.strip().lower()
            for field in extracted_fields
            if field.name.strip().lower()
            and field.name.strip().lower()
            not in supported_recommendation_field_names
        }
    )
    if unsupported_fields:
        issues_by_code[ReviewReason.HALLUCINATED_RECOMMENDATION_FIELD.value] = (
            _build_recommendation_safety_issue(
                code=ReviewReason.HALLUCINATED_RECOMMENDATION_FIELD,
                message=(
                    "Recommendation inputs included unsupported extracted fields "
                    f"({', '.join(unsupported_fields)}) and require operator "
                    "review before AI guidance can be used."
                ),
            )
        )

    if len(packet_document_types) > 1:
        issues_by_code[ReviewReason.MIXED_CONTENT_PACKET.value] = (
            _build_recommendation_safety_issue(
                code=ReviewReason.MIXED_CONTENT_PACKET,
                message=(
                    "Packet documents span multiple managed document types "
                    f"({', '.join(sorted(packet_document_types))}) and require "
                    "operator review before recommendation acceptance."
                ),
            )
        )

    return tuple(issues_by_code.values())


def _resolve_extracted_field_summary(
    extracted_fields: tuple[ExtractedField, ...],
) -> str:
    """Build a short human-readable field summary."""

    if not extracted_fields:
        return "No structured fields were extracted."

    summary_parts = [
        f"{field.name}={field.value}"
        for field in extracted_fields[:4]
    ]
    return ", ".join(summary_parts)


def _build_recommendation_evidence(
    *,
    document: PacketDocumentRecord,
    extracted_fields: tuple[ExtractedField, ...],
    extraction_result: ExtractionResultRecord,
    ocr_result: OcrResultRecord | None,
    source_asset: DocumentAssetRecord | None,
) -> tuple[RecommendationEvidenceItem, ...]:
    """Build the stored evidence items required by recommendation contracts."""

    storage_uri = (
        source_asset.storage_uri if source_asset is not None else document.source_uri
    )
    evidence_items: list[RecommendationEvidenceItem] = []

    if extracted_fields:
        for field in extracted_fields[:5]:
            evidence_items.append(
                RecommendationEvidenceItem(
                    evidence_kind="extracted_field",
                    field_name=field.name,
                    source_document_id=document.document_id,
                    source_excerpt=field.value,
                    storage_uri=storage_uri,
                )
            )
    else:
        evidence_items.append(
            RecommendationEvidenceItem(
                evidence_kind="extracted_field",
                field_name="summary",
                source_document_id=document.document_id,
                source_excerpt=(
                    extraction_result.summary
                    or (ocr_result.text_excerpt if ocr_result is not None else None)
                    or document.document_text
                    or document.file_name
                ),
                storage_uri=storage_uri,
            )
        )

    excerpt = None
    if ocr_result is not None and ocr_result.text_excerpt:
        excerpt = ocr_result.text_excerpt
    elif document.document_text:
        excerpt = document.document_text[:600]

    evidence_items.append(
        RecommendationEvidenceItem(
            evidence_kind="ocr_excerpt",
            source_document_id=document.document_id,
            source_excerpt=excerpt or extraction_result.summary or document.file_name,
            storage_uri=storage_uri,
        )
    )
    evidence_items.append(
        RecommendationEvidenceItem(
            evidence_kind="source_document_link",
            source_document_id=document.document_id,
            source_excerpt=document.file_name,
            storage_uri=storage_uri,
        )
    )
    return tuple(evidence_items)


def _resolve_recommendation_confidence(
    *,
    account_match_run: AccountMatchRunRecord | None,
    classification_result: ClassificationResultRecord | None,
    document: PacketDocumentRecord,
    extracted_fields: tuple[ExtractedField, ...],
    ocr_result: OcrResultRecord | None,
) -> float:
    """Calculate a stable recommendation confidence score."""

    field_confidence = (
        sum(field.confidence for field in extracted_fields) / len(extracted_fields)
        if extracted_fields
        else 0.5
    )
    classification_confidence = (
        classification_result.confidence
        if classification_result is not None
        else 0.5
    )
    ocr_confidence = ocr_result.ocr_confidence if ocr_result is not None else 0.5
    if account_match_run is not None and account_match_run.selected_account_id:
        match_confidence = 0.95
    elif len(document.account_candidates) == 1:
        match_confidence = 0.85
    elif account_match_run is not None and account_match_run.candidates:
        match_confidence = 0.65
    else:
        match_confidence = 0.5

    confidence = (
        classification_confidence + field_confidence + ocr_confidence + match_confidence
    ) / 4
    return max(0.0, min(1.0, round(confidence, 4)))


def _build_recommendation_summary(
    *,
    classification_result: ClassificationResultRecord | None,
    document: PacketDocumentRecord,
    extraction_result: ExtractionResultRecord,
    field_lookup: dict[str, str],
    selected_account_id: str | None,
) -> str:
    """Build the top-level recommendation summary."""

    classification_key = None
    if classification_result is not None:
        raw_execution = classification_result.result_payload.get(
            "classificationExecution"
        )
        if isinstance(raw_execution, dict):
            raw_classification_key = raw_execution.get("classificationKey")
            if (
                isinstance(raw_classification_key, str)
                and raw_classification_key.strip()
            ):
                classification_key = raw_classification_key.strip()

    summary_parts = [document.file_name]
    if extraction_result.document_type:
        summary_parts.append(extraction_result.document_type)
    elif classification_key:
        summary_parts.append(classification_key)

    if selected_account_id:
        summary_parts.append(f"linked to {selected_account_id}")

    balance_value = field_lookup.get("balance") or field_lookup.get("amount_due")
    if balance_value:
        summary_parts.append(f"balance {balance_value}")

    return "Recommendation-ready evidence: " + ", ".join(summary_parts)


def _build_recommendation_advisory(
    *,
    confidence: float,
    document: PacketDocumentRecord,
    extracted_fields: tuple[ExtractedField, ...],
    extraction_result: ExtractionResultRecord,
    selected_account_id: str | None,
) -> str:
    """Build the advisory text stored alongside the recommendation result."""

    field_summary = _resolve_extracted_field_summary(extracted_fields)
    account_line = (
        f"The packet is currently anchored to account {selected_account_id}."
        if selected_account_id
        else "No single account was attached at recommendation time."
    )
    return (
        f"{account_line} "
        f"Use the extracted {extraction_result.document_type or 'document'} evidence "
        f"from {document.file_name} as advisory-only guidance. "
        f"Key evidence: {field_summary}. "
        f"Recommendation confidence is {confidence:.2f}."
    )


def _resolve_recommendation(
    *,
    account_match_run: AccountMatchRunRecord | None,
    classification_result: ClassificationResultRecord | None,
    document: PacketDocumentRecord,
    extraction_result: ExtractionResultRecord,
    ocr_result: OcrResultRecord | None,
    packet_document_types: set[str],
    packet_field_values_by_name: dict[str, set[str]],
    source_asset: DocumentAssetRecord | None,
    settings: AppSettings,
) -> _ResolvedRecommendation:
    """Resolve one document recommendation without external dependencies."""

    contract = build_recommendation_contract()
    extracted_fields = _extract_fields_from_result(extraction_result)
    field_lookup = _build_field_lookup(extracted_fields)
    selected_account_id = _resolve_selected_account_id(document, account_match_run)
    confidence = _resolve_recommendation_confidence(
        account_match_run=account_match_run,
        classification_result=classification_result,
        document=document,
        extracted_fields=extracted_fields,
        ocr_result=ocr_result,
    )
    supported_recommendation_field_names = _build_supported_recommendation_field_names(
        classification_result=classification_result,
        contract=contract,
        settings=settings,
    )
    evidence_items = _build_recommendation_evidence(
        document=document,
        extracted_fields=extracted_fields,
        extraction_result=extraction_result,
        ocr_result=ocr_result,
        source_asset=source_asset,
    )
    safety_issues = _resolve_recommendation_safety_issues(
        classification_result=classification_result,
        contract=contract,
        confidence=confidence,
        evidence_items=evidence_items,
        extracted_fields=extracted_fields,
        packet_document_types=packet_document_types,
        packet_field_values_by_name=packet_field_values_by_name,
        settings=settings,
        supported_recommendation_field_names=supported_recommendation_field_names,
    )
    return _ResolvedRecommendation(
        advisory_text=_build_recommendation_advisory(
            confidence=confidence,
            document=document,
            extracted_fields=extracted_fields,
            extraction_result=extraction_result,
            selected_account_id=selected_account_id,
        ),
        confidence=confidence,
        disposition=contract.disposition_values[0],
        evidence_items=evidence_items,
        recommendation_kind=(
            extraction_result.document_type or "document_advisory"
        ),
        rationale_payload={
            "classificationResultId": (
                classification_result.classification_result_id
                if classification_result is not None
                else None
            ),
            "evidenceKinds": [
                evidence_item.evidence_kind for evidence_item in evidence_items
            ],
            "extractionResultId": extraction_result.extraction_result_id,
            "fieldSummary": _resolve_extracted_field_summary(extracted_fields),
            "matchRunId": (
                account_match_run.match_run_id
                if account_match_run is not None
                else None
            ),
            "ocrResultId": (
                ocr_result.ocr_result_id if ocr_result is not None else None
            ),
            "requiredEvidenceKinds": list(contract.required_evidence_kinds),
            "safetyIssues": serialize_safety_issues(safety_issues),
            "selectedAccountId": selected_account_id,
        },
        safety_issues=safety_issues,
        summary=_build_recommendation_summary(
            classification_result=classification_result,
            document=document,
            extraction_result=extraction_result,
            field_lookup=field_lookup,
            selected_account_id=selected_account_id,
        ),
    )


def _resolve_classification_prior_id(
    *,
    classification_result: ClassificationResultRecord | None,
    document: PacketDocumentRecord,
    packet_source_fingerprint: str | None,
) -> str | None:
    """Return the new classification-prior id when recommendation can learn."""

    if classification_result is None:
        return None
    if classification_result.result_source == ClassificationResultSource.PRIOR_REUSE:
        return None
    if classification_result.classification_id is None:
        return None
    if classification_result.document_type_id is None:
        return None
    if classification_result.prompt_profile_id is None:
        return None
    if document.file_hash_sha256 is None and packet_source_fingerprint is None:
        return None

    return f"prior_{uuid4().hex}"


def _build_pending_recommendation_execution(
    *,
    account_match_run: AccountMatchRunRecord | None,
    classification_result: ClassificationResultRecord | None,
    document: PacketDocumentRecord,
    extraction_result: ExtractionResultRecord,
    latest_job: ProcessingJobRecord,
    ocr_result: OcrResultRecord | None,
    packet_document_types: set[str],
    packet_source_fingerprint: str | None,
    packet_field_values_by_name: dict[str, set[str]],
    source_asset: DocumentAssetRecord | None,
    settings: AppSettings,
) -> _PendingRecommendationExecution:
    """Resolve one queued recommendation execution before persistence."""

    resolved_recommendation = _resolve_recommendation(
        account_match_run=account_match_run,
        classification_result=classification_result,
        document=document,
        extraction_result=extraction_result,
        ocr_result=ocr_result,
        packet_document_types=packet_document_types,
        packet_field_values_by_name=packet_field_values_by_name,
        source_asset=source_asset,
        settings=settings,
    )
    return _PendingRecommendationExecution(
        account_match_run=account_match_run,
        classification_prior_id=_resolve_classification_prior_id(
            classification_result=classification_result,
            document=document,
            packet_source_fingerprint=packet_source_fingerprint,
        ),
        classification_result=classification_result,
        document=document,
        extraction_result=extraction_result,
        ocr_result=ocr_result,
        recommendation_job_id=latest_job.job_id,
        recommendation_result_id=f"recres_{uuid4().hex}",
        recommendation_run_id=f"recrun_{uuid4().hex}",
        resolved_recommendation=resolved_recommendation,
        review_task_id=(
            f"task_{uuid4().hex}"
            if resolved_recommendation.safety_issues
            else None
        ),
        source_asset=source_asset,
    )


def _resolve_packet_handoff(
    *,
    processed_statuses: dict[str, PacketStatus],
    snapshot: PacketWorkspaceSnapshot,
) -> tuple[PacketStatus, ProcessingStageName]:
    """Return the packet status after recommendation has completed."""

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
        == ProcessingStageName.RECOMMENDATION
        and latest_jobs[document.document_id].status != ProcessingJobStatus.SUCCEEDED
        and document.document_id not in processed_statuses
        for document in snapshot.documents
    ):
        return PacketStatus.READY_FOR_RECOMMENDATION, ProcessingStageName.RECOMMENDATION

    if any(
        status == PacketStatus.AWAITING_REVIEW
        for status in effective_statuses.values()
    ):
        return PacketStatus.AWAITING_REVIEW, ProcessingStageName.REVIEW

    if any(
        status == PacketStatus.READY_FOR_RECOMMENDATION
        for document_id, status in effective_statuses.items()
        if document_id not in processed_statuses
    ):
        return PacketStatus.READY_FOR_RECOMMENDATION, ProcessingStageName.RECOMMENDATION

    if processed_statuses:
        return PacketStatus.COMPLETED, ProcessingStageName.RECOMMENDATION

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
    *,
    document_id: str,
    status: PacketStatus,
) -> None:
    """Persist the latest packet-document state after recommendation."""

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


def _insert_review_task(
    cursor: Any,
    *,
    execution: _PendingRecommendationExecution,
    packet_id: str,
) -> None:
    """Persist one recommendation-driven review task when guardrails trigger."""

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
            %s,
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
            _resolve_selected_account_id(
                execution.document,
                execution.account_match_run,
            ),
            json.dumps(
                [issue.code for issue in execution.resolved_recommendation.safety_issues]
            ),
            " ".join(
                issue.message for issue in execution.resolved_recommendation.safety_issues
            ),
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


def _insert_recommendation_run(
    cursor: Any,
    *,
    execution: _PendingRecommendationExecution,
    packet_id: str,
) -> None:
    """Persist one recommendation run in running state."""

    cursor.execute(
        """
        INSERT INTO dbo.RecommendationRuns (
            recommendationRunId,
            packetId,
            documentId,
            reviewTaskId,
            promptProfileId,
            status,
            requestedByUserId,
            requestedByEmail,
            inputJson,
            completedAtUtc,
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
            NULL,
            NULL,
            %s,
            NULL,
            SYSUTCDATETIME(),
            SYSUTCDATETIME()
        )
        """,
        (
            execution.recommendation_run_id,
            packet_id,
            execution.document.document_id,
            execution.review_task_id,
            (
                execution.classification_result.prompt_profile_id.value
                if execution.classification_result is not None
                and execution.classification_result.prompt_profile_id is not None
                else execution.extraction_result.prompt_profile_id.value
                if execution.extraction_result.prompt_profile_id is not None
                else None
            ),
            RecommendationRunStatus.RUNNING.value,
            json.dumps(
                {
                    "classificationResultId": (
                        execution.classification_result.classification_result_id
                        if execution.classification_result is not None
                        else None
                    ),
                    "documentId": execution.document.document_id,
                    "extractionResultId": (
                        execution.extraction_result.extraction_result_id
                    ),
                    "matchRunId": (
                        execution.account_match_run.match_run_id
                        if execution.account_match_run is not None
                        else None
                    ),
                    "ocrResultId": (
                        execution.ocr_result.ocr_result_id
                        if execution.ocr_result is not None
                        else None
                    ),
                }
            ),
        ),
    )


def _insert_recommendation_result(
    cursor: Any,
    *,
    execution: _PendingRecommendationExecution,
    packet_id: str,
) -> None:
    """Persist one recommendation result row."""

    cursor.execute(
        """
        INSERT INTO dbo.RecommendationResults (
            recommendationResultId,
            recommendationRunId,
            packetId,
            documentId,
            recommendationKind,
            summary,
            rationaleJson,
            evidenceJson,
            confidence,
            advisoryText,
            disposition,
            reviewedByUserId,
            reviewedByEmail,
            reviewedAtUtc,
            createdAtUtc,
            updatedAtUtc
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, NULL, NULL, NULL, SYSUTCDATETIME(), SYSUTCDATETIME()
        )
        """,
        (
            execution.recommendation_result_id,
            execution.recommendation_run_id,
            packet_id,
            execution.document.document_id,
            execution.resolved_recommendation.recommendation_kind,
            execution.resolved_recommendation.summary,
            json.dumps(execution.resolved_recommendation.rationale_payload),
            json.dumps(
                [
                    evidence_item.model_dump(mode="json")
                    for evidence_item in (
                        execution.resolved_recommendation.evidence_items
                    )
                ]
            ),
            execution.resolved_recommendation.confidence,
            execution.resolved_recommendation.advisory_text,
            execution.resolved_recommendation.disposition.value,
        ),
    )


def _complete_recommendation_run(
    cursor: Any,
    recommendation_run_id: str,
) -> None:
    """Move a recommendation run into ready-for-review state."""

    cursor.execute(
        """
        UPDATE dbo.RecommendationRuns
        SET
            status = %s,
            completedAtUtc = SYSUTCDATETIME(),
            updatedAtUtc = SYSUTCDATETIME()
        WHERE recommendationRunId = %s
        """,
        (RecommendationRunStatus.READY_FOR_REVIEW.value, recommendation_run_id),
    )


def _insert_classification_prior(
    cursor: Any,
    *,
    execution: _PendingRecommendationExecution,
    packet_id: str,
    packet_source_fingerprint: str | None,
) -> None:
    """Persist a future-run classification prior when enough evidence exists."""

    prior_id = execution.classification_prior_id
    classification_result = execution.classification_result
    if prior_id is None or classification_result is None:
        return
    if classification_result.classification_id is None:
        return
    if classification_result.document_type_id is None:
        return
    if classification_result.prompt_profile_id is None:
        return

    selected_account_id = _resolve_selected_account_id(
        execution.document,
        execution.account_match_run,
    )
    cursor.execute(
        """
        INSERT INTO dbo.ClassificationPriors (
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
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, NULL, NULL, SYSUTCDATETIME(), %s,
            SYSUTCDATETIME(), SYSUTCDATETIME()
        )
        """,
        (
            prior_id,
            packet_id,
            execution.document.document_id,
            execution.document.file_hash_sha256,
            packet_source_fingerprint,
            _normalize_text(execution.document.issuer_name),
            selected_account_id,
            classification_result.classification_id,
            classification_result.document_type_id,
            classification_result.prompt_profile_id.value,
            execution.resolved_recommendation.confidence,
            True,
        ),
    )


def _build_recommendation_started_event_payload(
    execution: _PendingRecommendationExecution,
) -> dict[str, Any]:
    """Return the event payload for a started recommendation job."""

    return {
        "classificationResultId": (
            execution.classification_result.classification_result_id
            if execution.classification_result is not None
            else None
        ),
        "recommendationJobId": execution.recommendation_job_id,
        "recommendationRunId": execution.recommendation_run_id,
        "stageName": ProcessingStageName.RECOMMENDATION.value,
        "status": ProcessingJobStatus.RUNNING.value,
    }


def _build_recommendation_completed_event_payload(
    execution: _PendingRecommendationExecution,
) -> dict[str, Any]:
    """Return the event payload for a completed recommendation job."""

    return {
        "classificationPriorId": execution.classification_prior_id,
        "confidence": execution.resolved_recommendation.confidence,
        "disposition": execution.resolved_recommendation.disposition.value,
        "recommendationJobId": execution.recommendation_job_id,
        "recommendationKind": execution.resolved_recommendation.recommendation_kind,
        "recommendationResultId": execution.recommendation_result_id,
        "recommendationRunId": execution.recommendation_run_id,
        "reviewTaskId": execution.review_task_id,
        "safetyIssues": serialize_safety_issues(
            execution.resolved_recommendation.safety_issues
        ),
        "selectedAccountId": _resolve_selected_account_id(
            execution.document,
            execution.account_match_run,
        ),
        "status": (
            PacketStatus.AWAITING_REVIEW.value
            if execution.review_task_id is not None
            else PacketStatus.COMPLETED.value
        ),
        "summary": execution.resolved_recommendation.summary,
    }


def _build_review_task_created_event_payload(
    execution: _PendingRecommendationExecution,
) -> dict[str, Any]:
    """Return the event payload for a recommendation-created review task."""

    return {
        "priority": ReviewTaskPriority.HIGH.value,
        "reasonCodes": [
            issue.code for issue in execution.resolved_recommendation.safety_issues
        ],
        "reviewTaskId": execution.review_task_id,
        "safetyIssues": serialize_safety_issues(
            execution.resolved_recommendation.safety_issues
        ),
        "stageName": ProcessingStageName.REVIEW.value,
        "status": PacketStatus.AWAITING_REVIEW.value,
        "summary": " ".join(
            issue.message for issue in execution.resolved_recommendation.safety_issues
        ),
    }


def _persist_document_recommendation_execution(
    cursor: Any,
    *,
    execution: _PendingRecommendationExecution,
    packet_id: str,
    packet_source_fingerprint: str | None,
) -> None:
    """Persist one recommendation execution and completion path."""

    _set_job_running(cursor, execution.recommendation_job_id)
    _insert_packet_event(
        cursor,
        document_id=execution.document.document_id,
        event_payload=_build_recommendation_started_event_payload(execution),
        event_type="document.recommendation.started",
        packet_id=packet_id,
    )
    _insert_review_task(cursor, execution=execution, packet_id=packet_id)
    _insert_recommendation_run(cursor, execution=execution, packet_id=packet_id)
    _insert_recommendation_result(cursor, execution=execution, packet_id=packet_id)
    _insert_classification_prior(
        cursor,
        execution=execution,
        packet_id=packet_id,
        packet_source_fingerprint=packet_source_fingerprint,
    )
    _complete_recommendation_run(cursor, execution.recommendation_run_id)
    _set_job_succeeded(cursor, execution.recommendation_job_id)
    _update_document_state(
        cursor,
        document_id=execution.document.document_id,
        status=(
            PacketStatus.AWAITING_REVIEW
            if execution.review_task_id is not None
            else PacketStatus.COMPLETED
        ),
    )
    _insert_packet_event(
        cursor,
        document_id=execution.document.document_id,
        event_payload=_build_recommendation_completed_event_payload(execution),
        event_type="document.recommendation.completed",
        packet_id=packet_id,
    )
    if execution.review_task_id is not None:
        _insert_packet_event(
            cursor,
            document_id=execution.document.document_id,
            event_payload=_build_review_task_created_event_payload(execution),
            event_type="document.review_task.created",
            packet_id=packet_id,
        )


def _persist_recommendation_execution(
    *,
    packet_id: str,
    packet_source_fingerprint: str | None,
    packet_status: PacketStatus,
    pending_executions: tuple[_PendingRecommendationExecution, ...],
    settings: AppSettings,
) -> None:
    """Persist recommendation completion for the packet."""

    if not pending_executions:
        return

    first_packet_id = pending_executions[0].document.packet_id
    if packet_id != first_packet_id:
        raise RuntimeError(
            "Pending recommendation packet ids do not match the target packet."
        )

    connection_string = settings.sql_connection_string
    if not connection_string:
        raise PacketRecommendationConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    with open_sql_connection(connection_string, autocommit=False) as connection:
        try:
            with connection.cursor() as cursor:
                for execution in pending_executions:
                    _persist_document_recommendation_execution(
                        cursor,
                        execution=execution,
                        packet_id=packet_id,
                        packet_source_fingerprint=packet_source_fingerprint,
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
                        ),
                        "status": packet_status.value,
                    },
                    event_type="packet.recommendation.executed",
                    packet_id=packet_id,
                )

            connection.commit()
        except Exception:
            connection.rollback()
            raise


def execute_packet_recommendation_stage(
    packet_id: str,
    settings: AppSettings,
) -> PacketRecommendationExecutionResponse:
    """Execute queued packet recommendation work and persist results."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        raise PacketRecommendationConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    snapshot = repository.get_packet_workspace_snapshot(packet_id)
    latest_jobs = _select_latest_jobs_by_document(snapshot.processing_jobs)
    latest_classification_results = _select_latest_classification_results_by_document(
        snapshot.classification_results
    )
    latest_extraction_results = _select_latest_extraction_results_by_document(
        snapshot.extraction_results
    )
    latest_ocr_results = _select_latest_ocr_results_by_document(snapshot.ocr_results)
    latest_account_match_runs = _select_latest_account_match_runs_by_document(
        snapshot.account_match_runs
    )
    asset_by_document_id = _select_primary_asset_by_document(snapshot.document_assets)
    packet_document_types = _build_packet_document_types(snapshot.extraction_results)
    packet_field_values_by_name = _build_packet_field_values_by_name(
        snapshot.extraction_results
    )
    pending_executions: list[_PendingRecommendationExecution] = []
    skipped_document_ids: list[str] = []

    for document in snapshot.documents:
        latest_job = latest_jobs.get(document.document_id)
        extraction_result = latest_extraction_results.get(document.document_id)
        if latest_job is None or extraction_result is None:
            skipped_document_ids.append(document.document_id)
            continue

        if latest_job.stage_name != ProcessingStageName.RECOMMENDATION:
            skipped_document_ids.append(document.document_id)
            continue

        if latest_job.status != ProcessingJobStatus.QUEUED:
            skipped_document_ids.append(document.document_id)
            continue

        if document.status != PacketStatus.READY_FOR_RECOMMENDATION:
            skipped_document_ids.append(document.document_id)
            continue

        pending_executions.append(
            _build_pending_recommendation_execution(
                account_match_run=latest_account_match_runs.get(document.document_id),
                classification_result=latest_classification_results.get(
                    document.document_id
                ),
                document=document,
                extraction_result=extraction_result,
                latest_job=latest_job,
                ocr_result=latest_ocr_results.get(document.document_id),
                packet_document_types=packet_document_types,
                packet_source_fingerprint=snapshot.packet.source_fingerprint,
                packet_field_values_by_name=packet_field_values_by_name,
                source_asset=asset_by_document_id.get(document.document_id),
                settings=settings,
            )
        )

    packet_status, next_stage = _resolve_packet_handoff(
        processed_statuses={
            execution.document.document_id: (
                PacketStatus.AWAITING_REVIEW
                if execution.review_task_id is not None
                else PacketStatus.COMPLETED
            )
            for execution in pending_executions
        },
        snapshot=snapshot,
    )
    _persist_recommendation_execution(
        packet_id=packet_id,
        packet_source_fingerprint=snapshot.packet.source_fingerprint,
        packet_status=packet_status,
        pending_executions=tuple(pending_executions),
        settings=settings,
    )

    return PacketRecommendationExecutionResponse(
        executed_document_count=len(pending_executions),
        next_stage=next_stage,
        packet_id=packet_id,
        processed_documents=tuple(
            PacketRecommendationExecutionDocumentResult(
                classification_prior_id=execution.classification_prior_id,
                classification_result_id=(
                    execution.classification_result.classification_result_id
                    if execution.classification_result is not None
                    else None
                ),
                confidence=execution.resolved_recommendation.confidence,
                disposition=execution.resolved_recommendation.disposition,
                document_id=execution.document.document_id,
                packet_id=packet_id,
                recommendation_job_id=execution.recommendation_job_id,
                recommendation_kind=execution.resolved_recommendation.recommendation_kind,
                recommendation_result_id=execution.recommendation_result_id,
                recommendation_run_id=execution.recommendation_run_id,
                review_task_id=execution.review_task_id,
                selected_account_id=_resolve_selected_account_id(
                    execution.document,
                    execution.account_match_run,
                ),
                status=(
                    PacketStatus.AWAITING_REVIEW
                    if execution.review_task_id is not None
                    else PacketStatus.COMPLETED
                ),
                summary=execution.resolved_recommendation.summary,
            )
            for execution in pending_executions
        ),
        skipped_document_ids=tuple(skipped_document_ids),
        status=packet_status,
    )