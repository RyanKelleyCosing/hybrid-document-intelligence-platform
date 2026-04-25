"""Persistence and queue publishing for manual review workflows."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import cached_property
from typing import Any
from uuid import uuid4

from azure.cosmos import CosmosClient, PartitionKey
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from document_intelligence.models import (
    ArchiveDocumentLineage,
    ArchivePreflightDisposition,
    ArchivePreflightResult,
    ClassificationResultCreateRequest,
    ClassificationResultSource,
    DocumentIngestionRequest,
    DocumentSource,
    DuplicateDetectionResult,
    DuplicateDetectionSignal,
    DuplicateDetectionStatus,
    DuplicateSignalType,
    IntakeSourceCreateRequest,
    IntakeSourceDeleteResponse,
    IntakeSourceEnablementRequest,
    IntakeSourceListResponse,
    IntakeSourceRecord,
    IntakeSourceUpdateRequest,
    ManualPacketDocumentRecord,
    ManualPacketIntakeRequest,
    ManualPacketIntakeResponse,
    ManualPacketStagedDocument,
    PacketStatus,
    ProcessingJobStatus,
    ProcessingStageName,
    ProfileSelectionMode,
    ReviewDecisionUpdate,
    ReviewItemListResponse,
    ReviewQueueItem,
    ReviewStatus,
    ReviewTaskPriority,
    SafetyIssueSeverity,
    validate_intake_source_configuration,
)
from document_intelligence.profiles import select_prompt_profile
from document_intelligence.safety import serialize_safety_issues
from document_intelligence.settings import AppSettings
from document_intelligence.utils.sql import open_sql_connection


def _as_optional_datetime(value: object) -> datetime | None:
    """Return the datetime value when the database row contains one."""

    return value if isinstance(value, datetime) else None


def _as_optional_int(value: object) -> int | None:
    """Return the integer value when the database row contains one."""

    if value is None:
        return None

    if isinstance(value, int):
        return value

    return int(str(value))


def _as_optional_str(value: object) -> str | None:
    """Return a string value or None from a database row."""

    return str(value) if value is not None else None


def _require_row_str(value: object, *, field_name: str) -> str:
    """Return a required string value from a database row."""

    if value is None:
        raise ValueError(f"SQL row field '{field_name}' is required")

    return str(value)


def _as_str_tuple_from_json(value: object) -> tuple[str, ...]:
    """Return a string tuple from a JSON array column."""

    if value is None:
        return ()

    payload = json.loads(str(value))
    if not isinstance(payload, list):
        return ()

    return tuple(str(item) for item in payload if item is not None)


def _build_duplicate_detection_result(value: object) -> DuplicateDetectionResult:
    """Hydrate a stored duplicate-detection payload from SQL."""

    if value is None:
        return DuplicateDetectionResult()

    payload = json.loads(str(value))
    if not isinstance(payload, dict):
        return DuplicateDetectionResult()

    return DuplicateDetectionResult.model_validate(payload)


def _build_archive_preflight_result(value: object) -> ArchivePreflightResult:
    """Hydrate a stored archive-preflight payload from a packet event."""

    if value is None:
        return ArchivePreflightResult()

    payload = json.loads(str(value))
    if not isinstance(payload, dict):
        return ArchivePreflightResult()

    archive_preflight_payload = payload.get("archivePreflight")
    if not isinstance(archive_preflight_payload, dict):
        return ArchivePreflightResult()

    return ArchivePreflightResult.model_validate(archive_preflight_payload)


def _build_archive_document_lineage(
    *,
    archive_depth: object,
    archive_member_path: object,
    parent_document_id: object,
    source_asset_id: object,
) -> ArchiveDocumentLineage:
    """Hydrate archive lineage metadata from SQL row values."""

    return ArchiveDocumentLineage(
        archive_depth=_as_optional_int(archive_depth) or 0,
        archive_member_path=_as_optional_str(archive_member_path),
        parent_document_id=_as_optional_str(parent_document_id),
        source_asset_id=_as_optional_str(source_asset_id),
    )


def _build_parameter_placeholders(item_count: int) -> str:
    """Return a DB-API placeholder list for an IN clause."""

    return ", ".join(["%s"] * item_count)


def _resolve_packet_status_from_processing_values(
    *,
    stage_status_pairs: tuple[tuple[ProcessingStageName, PacketStatus], ...],
) -> PacketStatus:
    """Return the packet status implied by the initial document stages."""

    if any(
        status == PacketStatus.QUARANTINED
        or stage == ProcessingStageName.QUARANTINE
        for stage, status in stage_status_pairs
    ):
        return PacketStatus.QUARANTINED

    if any(
        status == PacketStatus.ARCHIVE_EXPANDING
        or (
            stage == ProcessingStageName.ARCHIVE_EXPANSION
            and status != PacketStatus.COMPLETED
        )
        for stage, status in stage_status_pairs
    ):
        return PacketStatus.ARCHIVE_EXPANDING

    if any(
        status == PacketStatus.CLASSIFYING
        or stage == ProcessingStageName.CLASSIFICATION
        for stage, status in stage_status_pairs
    ):
        return PacketStatus.CLASSIFYING

    return PacketStatus.RECEIVED


def _resolve_next_stage_from_processing_values(
    *,
    stage_status_pairs: tuple[tuple[ProcessingStageName, PacketStatus], ...],
) -> ProcessingStageName:
    """Return the next packet stage implied by the initial document stages."""

    if any(
        status == PacketStatus.QUARANTINED
        or stage == ProcessingStageName.QUARANTINE
        for stage, status in stage_status_pairs
    ):
        return ProcessingStageName.QUARANTINE

    if any(
        status == PacketStatus.ARCHIVE_EXPANDING
        or (
            stage == ProcessingStageName.ARCHIVE_EXPANSION
            and status != PacketStatus.COMPLETED
        )
        for stage, status in stage_status_pairs
    ):
        return ProcessingStageName.ARCHIVE_EXPANSION

    if any(
        status == PacketStatus.CLASSIFYING
        or stage == ProcessingStageName.CLASSIFICATION
        for stage, status in stage_status_pairs
    ):
        return ProcessingStageName.CLASSIFICATION

    return ProcessingStageName.OCR


def _resolve_quarantine_review_reason_codes(
    staged_document: ManualPacketStagedDocument,
) -> tuple[str, ...]:
    """Return review reason codes for quarantined archive and input issues."""

    if staged_document.initial_processing_stage != ProcessingStageName.QUARANTINE:
        return ()

    blocking_safety_codes = tuple(
        issue.code
        for issue in staged_document.safety_issues
        if issue.severity == SafetyIssueSeverity.BLOCKING
    )
    if blocking_safety_codes:
        return blocking_safety_codes

    disposition = staged_document.archive_preflight.disposition
    if disposition == ArchivePreflightDisposition.CORRUPT_ARCHIVE:
        return ("archive_corrupt",)

    if disposition == ArchivePreflightDisposition.ENCRYPTED_ARCHIVE:
        return ("archive_encrypted",)

    if disposition == ArchivePreflightDisposition.UNSAFE_ARCHIVE:
        return ("archive_unsafe",)

    if disposition == ArchivePreflightDisposition.UNSUPPORTED_ARCHIVE:
        return ("archive_unsupported",)

    if staged_document.lineage.parent_document_id is not None:
        return ("archive_member_unsupported",)

    return ("archive_quarantined",)


def _resolve_quarantine_notes_summary(
    staged_document: ManualPacketStagedDocument,
) -> str | None:
    """Return the operator-visible quarantine summary for a staged document."""

    if staged_document.safety_issues:
        return " ".join(issue.message for issue in staged_document.safety_issues)

    return staged_document.archive_preflight.message


def _resolve_manual_intake_event_type(
    staged_document: ManualPacketStagedDocument,
) -> str:
    """Return the packet-event type emitted for the staged document."""

    if staged_document.initial_processing_stage == ProcessingStageName.QUARANTINE:
        return "document.manual_intake.quarantined"

    if (
        staged_document.initial_processing_stage
        == ProcessingStageName.ARCHIVE_EXPANSION
    ):
        return "document.manual_intake.archive_detected"

    return "document.manual_intake.staged"


def _resolve_prompt_profile_seed_confidence(
    *,
    selection_mode: ProfileSelectionMode,
    top_candidate_score: int,
) -> float:
    """Return a conservative confidence score for intake-time routing hints."""

    if selection_mode == ProfileSelectionMode.EXPLICIT:
        return 1.0

    if selection_mode == ProfileSelectionMode.HEURISTIC:
        return max(0.55, min(top_candidate_score / 100, 0.9))

    return 0.25


def _build_manual_intake_classification_request(
    *,
    packet_id: str,
    packet_source_uri: str,
    request: ManualPacketIntakeRequest,
    staged_document: ManualPacketStagedDocument,
) -> ClassificationResultCreateRequest:
    """Create the first-pass classification seed for an expanded child document."""

    normalized_request = DocumentIngestionRequest(
        account_candidates=staged_document.account_candidates,
        content_type=staged_document.content_type,
        document_id=staged_document.document_id,
        document_text=staged_document.document_text,
        file_name=staged_document.file_name,
        issuer_category=staged_document.issuer_category,
        issuer_name=staged_document.issuer_name,
        received_at_utc=request.received_at_utc,
        requested_prompt_profile_id=staged_document.requested_prompt_profile_id,
        source=request.source,
        source_summary=staged_document.source_summary,
        source_tags=staged_document.source_tags,
        source_uri=staged_document.source_uri or packet_source_uri,
    )
    prompt_profile = select_prompt_profile(normalized_request)
    top_candidate_score = (
        prompt_profile.candidate_profiles[0].score
        if prompt_profile.candidate_profiles
        else 0
    )
    return ClassificationResultCreateRequest(
        classification_result_id=f"clsr_{uuid4().hex}",
        confidence=_resolve_prompt_profile_seed_confidence(
            selection_mode=prompt_profile.selection_mode,
            top_candidate_score=top_candidate_score,
        ),
        document_id=staged_document.document_id,
        packet_id=packet_id,
        prompt_profile_id=prompt_profile.primary_profile_id,
        result_payload={
            "archiveLineage": staged_document.lineage.model_dump(mode="json"),
            "classificationState": "seeded_from_manual_intake",
            "documentTypeHints": list(prompt_profile.document_type_hints),
            "keywordHints": list(prompt_profile.keyword_hints),
            "promptFocus": list(prompt_profile.prompt_focus),
            "promptProfileSelection": {
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
            },
            "sourceHints": {
                "accountCandidates": list(staged_document.account_candidates),
                "issuerCategory": staged_document.issuer_category.value,
                "issuerName": staged_document.issuer_name,
                "requestedPromptProfileId": (
                    staged_document.requested_prompt_profile_id.value
                    if staged_document.requested_prompt_profile_id is not None
                    else None
                ),
                "sourceSummary": staged_document.source_summary,
                "sourceTags": list(staged_document.source_tags),
            },
        },
        result_source=ClassificationResultSource.RULE,
    )


def _build_manual_packet_document_record_from_row(
    row: tuple[object, ...],
) -> ManualPacketDocumentRecord:
    """Build a manual-intake document response row from SQL."""

    (
        document_id,
        file_name,
        content_type,
        blob_uri,
        processing_job_id,
        processing_stage,
        processing_job_status,
        status,
        file_hash_sha256,
        parent_document_id,
        source_asset_id,
        archive_member_path,
        archive_depth,
        event_payload_json,
        review_task_id,
    ) = row

    return ManualPacketDocumentRecord(
        archive_preflight=_build_archive_preflight_result(event_payload_json),
        document_id=_require_row_str(document_id, field_name="documentId"),
        file_name=_require_row_str(file_name, field_name="fileName"),
        content_type=_require_row_str(content_type, field_name="contentType"),
        blob_uri=_require_row_str(blob_uri, field_name="storageUri"),
        file_hash_sha256=_require_row_str(
            file_hash_sha256,
            field_name="fileHashSha256",
        ),
        lineage=_build_archive_document_lineage(
            archive_depth=archive_depth,
            archive_member_path=archive_member_path,
            parent_document_id=parent_document_id,
            source_asset_id=source_asset_id,
        ),
        processing_job_id=_require_row_str(
            processing_job_id,
            field_name="jobId",
        ),
        processing_stage=ProcessingStageName(
            _require_row_str(processing_stage, field_name="stageName")
        ),
        processing_job_status=ProcessingJobStatus(
            _require_row_str(processing_job_status, field_name="jobStatus")
        ),
        review_task_id=_as_optional_str(review_task_id),
        status=PacketStatus(_require_row_str(status, field_name="status")),
    )


def _build_intake_source_record_from_row(
    row: tuple[object, ...],
) -> IntakeSourceRecord:
    """Build an intake-source record from a SQL result row."""

    (
        source_id,
        source_name,
        description,
        is_enabled,
        owner_email,
        polling_interval_minutes,
        credentials_reference,
        source_kind,
        settings_json,
        last_seen_at_utc,
        last_success_at_utc,
        last_error_at_utc,
        last_error_message,
        created_at_utc,
        updated_at_utc,
    ) = row
    configuration_payload = json.loads(
        _require_row_str(settings_json, field_name="settingsJson")
    )
    if not isinstance(configuration_payload, dict):
        raise ValueError("SQL intake-source configuration payload must be an object")

    configuration_payload.setdefault(
        "source_kind",
        _require_row_str(source_kind, field_name="sourceKind"),
    )
    return IntakeSourceRecord(
        source_id=_require_row_str(source_id, field_name="sourceId"),
        source_name=_require_row_str(source_name, field_name="sourceName"),
        description=_as_optional_str(description),
        is_enabled=bool(is_enabled),
        owner_email=_as_optional_str(owner_email),
        polling_interval_minutes=_as_optional_int(polling_interval_minutes),
        credentials_reference=_as_optional_str(credentials_reference),
        configuration=validate_intake_source_configuration(configuration_payload),
        last_seen_at_utc=_as_optional_datetime(last_seen_at_utc),
        last_success_at_utc=_as_optional_datetime(last_success_at_utc),
        last_error_at_utc=_as_optional_datetime(last_error_at_utc),
        last_error_message=_as_optional_str(last_error_message),
        created_at_utc=_as_optional_datetime(created_at_utc) or datetime.now(UTC),
        updated_at_utc=_as_optional_datetime(updated_at_utc) or datetime.now(UTC),
    )


class CosmosReviewRepository:
    """Store and query review items in Cosmos DB."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def is_configured(self) -> bool:
        """Return whether Cosmos DB settings are present."""
        return bool(
            self._settings.cosmos_endpoint
            and self._settings.cosmos_key
            and self._settings.cosmos_database_name
            and self._settings.cosmos_review_container_name
        )

    @cached_property
    def _container(self) -> Any:
        """Return the configured Cosmos DB container client."""
        if not self.is_configured():
            raise RuntimeError("Cosmos DB review storage is not configured")

        endpoint = self._settings.cosmos_endpoint
        key = self._settings.cosmos_key
        if endpoint is None or key is None:
            raise RuntimeError("Cosmos DB review storage is not configured")

        client = CosmosClient(
            url=endpoint,
            credential=key,
        )
        database = client.create_database_if_not_exists(
            id=self._settings.cosmos_database_name
        )
        return database.create_container_if_not_exists(
            id=self._settings.cosmos_review_container_name,
            partition_key=PartitionKey(path="/status"),
        )

    def upsert_review_item(self, review_item: ReviewQueueItem) -> ReviewQueueItem:
        """Upsert a review item into Cosmos DB."""
        payload = review_item.model_dump(mode="json")
        payload["id"] = review_item.document_id
        stored_item = self._container.upsert_item(payload)
        return ReviewQueueItem.model_validate(stored_item)

    def list_review_items(
        self,
        status: ReviewStatus,
        limit: int,
    ) -> ReviewItemListResponse:
        """List review items by workflow status."""
        query = (
            f"SELECT TOP {limit} * FROM c WHERE c.status = @status "
            "ORDER BY c.updated_at_utc DESC"
        )
        items = self._container.query_items(
            query=query,
            parameters=[{"name": "@status", "value": status.value}],
            enable_cross_partition_query=True,
        )
        return ReviewItemListResponse(
            items=tuple(ReviewQueueItem.model_validate(item) for item in items)
        )

    def get_review_item(self, document_id: str) -> ReviewQueueItem | None:
        """Get a persisted review item by document id."""
        query = "SELECT * FROM c WHERE c.document_id = @document_id"
        items = list(
            self._container.query_items(
                query=query,
                parameters=[{"name": "@document_id", "value": document_id}],
                enable_cross_partition_query=True,
            )
        )
        if not items:
            return None

        return ReviewQueueItem.model_validate(items[0])

    def apply_review_decision(
        self,
        document_id: str,
        update: ReviewDecisionUpdate,
    ) -> ReviewQueueItem | None:
        """Apply a reviewer decision to a stored review item."""
        existing_item = self.get_review_item(document_id)
        if existing_item is None:
            return None

        account_match = existing_item.account_match
        if account_match is not None and update.selected_account_id:
            account_match = account_match.model_copy(
                update={"selected_account_id": update.selected_account_id}
            )

        updated_item = existing_item.model_copy(
            update={
                "account_match": account_match,
                "review_notes": update.review_notes,
                "reviewed_at_utc": datetime.now(UTC),
                "reviewer_name": update.reviewer_name,
                "selected_account_id": (
                    update.selected_account_id or existing_item.selected_account_id
                ),
                "status": ReviewStatus(update.status),
                "updated_at_utc": datetime.now(UTC),
            }
        )
        return self.upsert_review_item(updated_item)


class SqlOperatorWorkspaceRepository:
    """Persist packet, asset, and job state for the operator workspace in SQL."""

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

    def detect_duplicate_packet(
        self,
        *,
        account_hint_ids: tuple[str, ...],
        file_hashes: tuple[str, ...],
        packet_fingerprint: str,
        source_fingerprint: str,
    ) -> DuplicateDetectionResult:
        """Inspect packet-level duplicate signals before new intake is persisted."""

        signals: list[DuplicateDetectionSignal] = []
        connection_string = self._get_connection_string()

        with open_sql_connection(connection_string, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT TOP 1 packetId
                    FROM dbo.Packets
                    WHERE packetFingerprint = %s
                    ORDER BY createdAtUtc DESC
                    """,
                    (packet_fingerprint,),
                )
                packet_fingerprint_row = cursor.fetchone()
                if packet_fingerprint_row is not None:
                    matched_packet_id = _require_row_str(
                        packet_fingerprint_row[0],
                        field_name="packetId",
                    )
                    signals.append(
                        DuplicateDetectionSignal(
                            description=(
                                "An existing packet matches the packet "
                                "fingerprint."
                            ),
                            matched_packet_id=matched_packet_id,
                            signal_type=DuplicateSignalType.PACKET_FINGERPRINT,
                            signal_value=packet_fingerprint,
                        )
                    )

                cursor.execute(
                    """
                    SELECT TOP 1 packetId
                    FROM dbo.Packets
                    WHERE sourceFingerprint = %s
                    ORDER BY createdAtUtc DESC
                    """,
                    (source_fingerprint,),
                )
                source_fingerprint_row = cursor.fetchone()
                if source_fingerprint_row is not None:
                    matched_packet_id = _require_row_str(
                        source_fingerprint_row[0],
                        field_name="packetId",
                    )
                    signals.append(
                        DuplicateDetectionSignal(
                            description=(
                                "An existing packet matches the source "
                                "fingerprint."
                            ),
                            matched_packet_id=matched_packet_id,
                            signal_type=DuplicateSignalType.SOURCE_FINGERPRINT,
                            signal_value=source_fingerprint,
                        )
                    )

                if file_hashes:
                    placeholder_list = _build_parameter_placeholders(len(file_hashes))
                    cursor.execute(
                        f"""
                        SELECT TOP 10 packetId, documentId, fileHashSha256
                        FROM dbo.PacketDocuments
                        WHERE fileHashSha256 IN ({placeholder_list})
                        ORDER BY receivedAtUtc DESC
                        """,
                        tuple(file_hashes),
                    )
                    for row in cursor.fetchall():
                        signals.append(
                            DuplicateDetectionSignal(
                                description=(
                                    "An existing document shares the same file hash."
                                ),
                                matched_packet_id=_require_row_str(
                                    row[0], field_name="packetId"
                                ),
                                matched_document_id=_require_row_str(
                                    row[1], field_name="documentId"
                                ),
                                signal_type=DuplicateSignalType.FILE_HASH,
                                signal_value=_require_row_str(
                                    row[2], field_name="fileHashSha256"
                                ),
                            )
                        )

                if account_hint_ids:
                    placeholder_list = _build_parameter_placeholders(
                        len(account_hint_ids)
                    )
                    account_params = tuple(account_hint_ids) + tuple(account_hint_ids)
                    cursor.execute(
                        f"""
                        SELECT TOP 10
                            amr.packetId,
                            amr.documentId,
                            COALESCE(amr.selectedAccountId, amc.accountId) AS accountId
                        FROM dbo.AccountMatchRuns AS amr
                        LEFT JOIN dbo.AccountMatchCandidates AS amc
                            ON amc.matchRunId = amr.matchRunId
                        WHERE amr.selectedAccountId IN ({placeholder_list})
                            OR amc.accountId IN ({placeholder_list})
                        ORDER BY amr.createdAtUtc DESC
                        """,
                        account_params,
                    )
                    for row in cursor.fetchall():
                        signals.append(
                            DuplicateDetectionSignal(
                                description=(
                                    "An existing match run references one of the "
                                    "same account hints."
                                ),
                                matched_packet_id=_require_row_str(
                                    row[0], field_name="packetId"
                                ),
                                matched_document_id=_require_row_str(
                                    row[1], field_name="documentId"
                                ),
                                matched_account_id=_require_row_str(
                                    row[2], field_name="accountId"
                                ),
                                signal_type=DuplicateSignalType.ACCOUNT_LINKED_HINT,
                                signal_value=_require_row_str(
                                    row[2], field_name="accountId"
                                ),
                            )
                        )

        unique_signals = tuple(
            {
                (
                    signal.signal_type,
                    signal.matched_packet_id,
                    signal.matched_document_id,
                    signal.matched_account_id,
                    signal.signal_value,
                ): signal
                for signal in signals
            }.values()
        )
        exact_duplicate_signal = next(
            (
                signal
                for signal in unique_signals
                if signal.signal_type
                in {
                    DuplicateSignalType.PACKET_FINGERPRINT,
                    DuplicateSignalType.SOURCE_FINGERPRINT,
                }
            ),
            None,
        )
        if exact_duplicate_signal is not None:
            return DuplicateDetectionResult(
                reused_existing_packet_id=exact_duplicate_signal.matched_packet_id,
                should_skip_ingestion=True,
                signals=unique_signals,
                status=DuplicateDetectionStatus.EXACT_DUPLICATE,
            )

        if unique_signals:
            return DuplicateDetectionResult(
                signals=unique_signals,
                status=DuplicateDetectionStatus.POSSIBLE_DUPLICATE,
            )

        return DuplicateDetectionResult()

    def get_manual_packet_intake_response(
        self,
        *,
        duplicate_detection: DuplicateDetectionResult | None,
        packet_id: str,
    ) -> ManualPacketIntakeResponse:
        """Load a previously persisted packet into the manual-intake response shape."""

        connection_string = self._get_connection_string()

        with open_sql_connection(connection_string, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        packetName,
                        source,
                        sourceUri,
                        submittedBy,
                        status,
                        receivedAtUtc,
                        packetFingerprint,
                        sourceFingerprint,
                        duplicateSignalsJson
                    FROM dbo.Packets
                    WHERE packetId = %s
                    """,
                    (packet_id,),
                )
                packet_row = cursor.fetchone()
                if packet_row is None:
                    raise RuntimeError(
                        f"Persisted packet '{packet_id}' could not be loaded."
                    )

                cursor.execute(
                    """
                    SELECT
                        d.documentId,
                        d.fileName,
                        d.contentType,
                        a.storageUri,
                        j.jobId,
                        j.stageName,
                        j.status,
                        d.status,
                        d.fileHashSha256,
                        d.parentDocumentId,
                        d.sourceAssetId,
                        d.archiveMemberPath,
                        d.archiveDepth,
                        e.eventPayloadJson,
                        r.reviewTaskId
                    FROM dbo.PacketDocuments AS d
                    OUTER APPLY (
                        SELECT TOP 1 storageUri
                        FROM dbo.DocumentAssets
                        WHERE documentId = d.documentId
                        ORDER BY CASE assetRole
                            WHEN 'original_upload' THEN 0
                            WHEN 'archive_extracted_member' THEN 1
                            ELSE 2
                        END,
                        createdAtUtc ASC
                    ) AS a
                    OUTER APPLY (
                        SELECT TOP 1 jobId, stageName, status
                        FROM dbo.ProcessingJobs
                        WHERE documentId = d.documentId
                        ORDER BY createdAtUtc DESC
                    ) AS j
                    OUTER APPLY (
                        SELECT TOP 1 eventPayloadJson
                        FROM dbo.PacketEvents
                        WHERE documentId = d.documentId
                            AND eventType IN (
                                'document.manual_intake.archive_detected',
                                'document.manual_intake.quarantined',
                                'document.manual_intake.staged'
                            )
                        ORDER BY createdAtUtc DESC
                    ) AS e
                    OUTER APPLY (
                        SELECT TOP 1 reviewTaskId
                        FROM dbo.ReviewTasks
                        WHERE documentId = d.documentId
                        ORDER BY createdAtUtc DESC
                    ) AS r
                    WHERE d.packetId = %s
                    ORDER BY d.createdAtUtc ASC
                    """,
                    (packet_id,),
                )
                document_rows = cursor.fetchall()

        documents = tuple(
            _build_manual_packet_document_record_from_row(row)
            for row in document_rows
        )
        stored_duplicate_detection = _build_duplicate_detection_result(packet_row[8])
        effective_duplicate_detection = (
            duplicate_detection or stored_duplicate_detection
        )
        return ManualPacketIntakeResponse(
            packet_id=packet_id,
            packet_name=_require_row_str(packet_row[0], field_name="packetName"),
            source=DocumentSource(_require_row_str(packet_row[1], field_name="source")),
            source_uri=_require_row_str(packet_row[2], field_name="sourceUri"),
            submitted_by=_as_optional_str(packet_row[3]),
            packet_fingerprint=_as_optional_str(packet_row[6]),
            source_fingerprint=_as_optional_str(packet_row[7]),
            status=PacketStatus(_require_row_str(packet_row[4], field_name="status")),
            next_stage=_resolve_next_stage_from_processing_values(
                stage_status_pairs=tuple(
                    (document.processing_stage, document.status)
                    for document in documents
                ),
            ),
            document_count=len(document_rows),
            duplicate_detection=effective_duplicate_detection,
            idempotency_reused_existing_packet=(
                effective_duplicate_detection.should_skip_ingestion
            ),
            received_at_utc=_as_optional_datetime(packet_row[5]) or datetime.now(UTC),
            documents=documents,
        )

    def create_manual_packet_intake(
        self,
        *,
        duplicate_detection: DuplicateDetectionResult,
        packet_id: str,
        packet_fingerprint: str,
        request: ManualPacketIntakeRequest,
        source_fingerprint: str,
        staged_documents: tuple[ManualPacketStagedDocument, ...],
    ) -> ManualPacketIntakeResponse:
        """Persist a newly staged packet and queue its documents for OCR."""
        connection_string = self._get_connection_string()

        packet_source_uri = request.source_uri or f"manual://packets/{packet_id}"
        packet_tags_json = json.dumps(list(request.packet_tags))
        duplicate_detection_json = duplicate_detection.model_dump_json()
        created_documents: list[ManualPacketDocumentRecord] = []
        asset_ids_by_document_id = {
            staged_document.document_id: f"asset_{uuid4().hex}"
            for staged_document in staged_documents
        }
        job_ids_by_document_id = {
            staged_document.document_id: f"job_{uuid4().hex}"
            for staged_document in staged_documents
        }
        packet_status = _resolve_packet_status_from_processing_values(
            stage_status_pairs=tuple(
                (
                    staged_document.initial_processing_stage,
                    staged_document.status,
                )
                for staged_document in staged_documents
            ),
        )
        next_stage = _resolve_next_stage_from_processing_values(
            stage_status_pairs=tuple(
                (
                    staged_document.initial_processing_stage,
                    staged_document.status,
                )
                for staged_document in staged_documents
            ),
        )

        with open_sql_connection(connection_string, autocommit=False) as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO dbo.Packets (
                            packetId,
                            packetName,
                            source,
                            sourceUri,
                            status,
                            submittedBy,
                            packetTagsJson,
                            packetFingerprint,
                            sourceFingerprint,
                            duplicateOfPacketId,
                            duplicateSignalsJson,
                            receivedAtUtc,
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
                            %s,
                            %s,
                            SYSUTCDATETIME(),
                            SYSUTCDATETIME()
                        )
                        """,
                        (
                            packet_id,
                            request.packet_name,
                            request.source.value,
                            packet_source_uri,
                            packet_status.value,
                            request.submitted_by,
                            packet_tags_json,
                            packet_fingerprint,
                            source_fingerprint,
                            duplicate_detection.reused_existing_packet_id,
                            duplicate_detection_json,
                            request.received_at_utc,
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
                        VALUES (
                            %s,
                            NULL,
                            %s,
                            %s,
                            SYSUTCDATETIME()
                        )
                        """,
                        (
                            packet_id,
                            "packet.manual_intake.created",
                            json.dumps(
                                {
                                    "documentCount": len(staged_documents),
                                    "nextStage": next_stage.value,
                                    "packetTags": list(request.packet_tags),
                                    "status": packet_status.value,
                                    "submittedBy": request.submitted_by,
                                }
                            ),
                        ),
                    )
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
                        VALUES (
                            NULL,
                            %s,
                            %s,
                            NULL,
                            NULL,
                            %s,
                            %s,
                            SYSUTCDATETIME()
                        )
                        """,
                        (
                            request.submitted_by,
                            packet_id,
                            "packet.manual_intake.created",
                            json.dumps(
                                {
                                    "packetName": request.packet_name,
                                    "source": request.source.value,
                                }
                            ),
                        ),
                    )

                    for staged_document in staged_documents:
                        asset_id = asset_ids_by_document_id[
                            staged_document.document_id
                        ]
                        job_id = job_ids_by_document_id[
                            staged_document.document_id
                        ]
                        source_asset_id = staged_document.lineage.source_asset_id
                        if (
                            source_asset_id is None
                            and staged_document.lineage.parent_document_id is not None
                        ):
                            source_asset_id = asset_ids_by_document_id.get(
                                staged_document.lineage.parent_document_id
                            )
                        cursor.execute(
                            """
                            INSERT INTO dbo.PacketDocuments (
                                documentId,
                                packetId,
                                fileName,
                                contentType,
                                source,
                                sourceUri,
                                status,
                                issuerName,
                                issuerCategory,
                                requestedPromptProfileId,
                                sourceSummary,
                                sourceTagsJson,
                                accountCandidatesJson,
                                documentText,
                                fileHashSha256,
                                parentDocumentId,
                                sourceAssetId,
                                archiveMemberPath,
                                archiveDepth,
                                receivedAtUtc,
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
                                SYSUTCDATETIME(),
                                SYSUTCDATETIME()
                            )
                            """,
                            (
                                staged_document.document_id,
                                packet_id,
                                staged_document.file_name,
                                staged_document.content_type,
                                request.source.value,
                                staged_document.source_uri or packet_source_uri,
                                staged_document.status.value,
                                staged_document.issuer_name,
                                staged_document.issuer_category.value,
                                (
                                    staged_document.requested_prompt_profile_id.value
                                    if (
                                        staged_document.requested_prompt_profile_id
                                        is not None
                                    )
                                    else None
                                ),
                                staged_document.source_summary,
                                json.dumps(list(staged_document.source_tags)),
                                json.dumps(list(staged_document.account_candidates)),
                                staged_document.document_text,
                                staged_document.file_hash_sha256,
                                staged_document.lineage.parent_document_id,
                                source_asset_id,
                                staged_document.lineage.archive_member_path,
                                staged_document.lineage.archive_depth,
                                request.received_at_utc,
                            ),
                        )
                        cursor.execute(
                            """
                            INSERT INTO dbo.DocumentAssets (
                                assetId,
                                packetId,
                                documentId,
                                assetRole,
                                containerName,
                                blobName,
                                contentType,
                                contentLengthBytes,
                                storageUri,
                                createdAtUtc
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
                                SYSUTCDATETIME()
                            )
                            """,
                            (
                                asset_id,
                                packet_id,
                                staged_document.document_id,
                                staged_document.asset_role,
                                staged_document.blob_container_name,
                                staged_document.blob_name,
                                staged_document.content_type,
                                staged_document.content_length_bytes,
                                staged_document.blob_uri,
                            ),
                        )
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
                                job_id,
                                packet_id,
                                staged_document.document_id,
                                staged_document.initial_processing_stage.value,
                                staged_document.initial_processing_job_status.value,
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
                            VALUES (
                                %s,
                                %s,
                                %s,
                                %s,
                                SYSUTCDATETIME()
                            )
                            """,
                            (
                                packet_id,
                                staged_document.document_id,
                                _resolve_manual_intake_event_type(staged_document),
                                json.dumps(
                                    {
                                        "archivePreflight": (
                                            staged_document.archive_preflight.model_dump(
                                                mode="json"
                                            )
                                        ),
                                        "blobUri": staged_document.blob_uri,
                                        "fileHashSha256": (
                                            staged_document.file_hash_sha256
                                        ),
                                        "lineage": staged_document.lineage.model_dump(
                                            mode="json"
                                        ),
                                        "safetyIssues": serialize_safety_issues(
                                            staged_document.safety_issues
                                        ),
                                        "processingJobId": job_id,
                                        "stageName": (
                                            staged_document.initial_processing_stage.value
                                        ),
                                        "status": staged_document.status.value,
                                    }
                                ),
                            ),
                        )
                        if (
                            staged_document.initial_processing_stage
                            == ProcessingStageName.CLASSIFICATION
                        ):
                            classification_request = (
                                _build_manual_intake_classification_request(
                                    packet_id=packet_id,
                                    packet_source_uri=packet_source_uri,
                                    request=request,
                                    staged_document=staged_document,
                                )
                            )
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
                                    SYSUTCDATETIME()
                                )
                                """,
                                (
                                    classification_request.classification_result_id,
                                    packet_id,
                                    staged_document.document_id,
                                    classification_request.classification_id,
                                    classification_request.document_type_id,
                                    classification_request.result_source.value,
                                    classification_request.confidence,
                                    json.dumps(
                                        classification_request.result_payload
                                    ),
                                    (
                                        classification_request.prompt_profile_id.value
                                        if (
                                            classification_request.prompt_profile_id
                                            is not None
                                        )
                                        else None
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
                                VALUES (
                                    %s,
                                    %s,
                                    %s,
                                    %s,
                                    SYSUTCDATETIME()
                                )
                                """,
                                (
                                    packet_id,
                                    staged_document.document_id,
                                    "document.classification.seeded",
                                    json.dumps(
                                        {
                                            **classification_request.result_payload,
                                            "classificationResultId": (
                                                classification_request
                                                .classification_result_id
                                            ),
                                            "confidence": (
                                                classification_request.confidence
                                            ),
                                            "promptProfileId": (
                                                classification_request
                                                .prompt_profile_id.value
                                                if (
                                                    classification_request
                                                    .prompt_profile_id
                                                    is not None
                                                )
                                                else None
                                            ),
                                            "stageName": (
                                                staged_document
                                                .initial_processing_stage.value
                                            ),
                                            "status": staged_document.status.value,
                                        }
                                    ),
                                ),
                            )
                        review_task_id: str | None = None
                        review_reason_codes = _resolve_quarantine_review_reason_codes(
                            staged_document
                        )
                        if review_reason_codes:
                            review_task_id = f"task_{uuid4().hex}"
                            review_task_payload = {
                                "archivePreflight": (
                                    staged_document.archive_preflight.model_dump(
                                        mode="json"
                                    )
                                ),
                                "lineage": staged_document.lineage.model_dump(
                                    mode="json"
                                ),
                                "reasonCodes": list(review_reason_codes),
                                "safetyIssues": serialize_safety_issues(
                                    staged_document.safety_issues
                                ),
                            }
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
                                    review_task_id,
                                    packet_id,
                                    staged_document.document_id,
                                    PacketStatus.AWAITING_REVIEW.value,
                                    ReviewTaskPriority.HIGH.value,
                                    json.dumps(list(review_reason_codes)),
                                    _resolve_quarantine_notes_summary(staged_document),
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
                                VALUES (
                                    %s,
                                    %s,
                                    %s,
                                    %s,
                                    SYSUTCDATETIME()
                                )
                                """,
                                (
                                    packet_id,
                                    staged_document.document_id,
                                    "document.review_task.created",
                                    json.dumps(
                                        {
                                            **review_task_payload,
                                            "priority": ReviewTaskPriority.HIGH.value,
                                            "reviewTaskId": review_task_id,
                                        }
                                    ),
                                ),
                            )
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
                                VALUES (
                                    NULL,
                                    %s,
                                    %s,
                                    %s,
                                    %s,
                                    %s,
                                    %s,
                                    SYSUTCDATETIME()
                                )
                                """,
                                (
                                    request.submitted_by,
                                    packet_id,
                                    staged_document.document_id,
                                    review_task_id,
                                    "review.task.created",
                                    json.dumps(review_task_payload),
                                ),
                            )
                        created_documents.append(
                            ManualPacketDocumentRecord(
                                archive_preflight=staged_document.archive_preflight,
                                document_id=staged_document.document_id,
                                file_name=staged_document.file_name,
                                content_type=staged_document.content_type,
                                blob_uri=staged_document.blob_uri,
                                file_hash_sha256=staged_document.file_hash_sha256,
                                lineage=_build_archive_document_lineage(
                                    archive_depth=staged_document.lineage.archive_depth,
                                    archive_member_path=(
                                        staged_document.lineage.archive_member_path
                                    ),
                                    parent_document_id=(
                                        staged_document.lineage.parent_document_id
                                    ),
                                    source_asset_id=source_asset_id,
                                ),
                                processing_job_id=job_id,
                                processing_stage=(
                                    staged_document.initial_processing_stage
                                ),
                                processing_job_status=(
                                    staged_document.initial_processing_job_status
                                ),
                                review_task_id=review_task_id,
                                status=staged_document.status,
                            )
                        )

                connection.commit()
            except Exception:
                connection.rollback()
                raise

        return ManualPacketIntakeResponse(
            packet_id=packet_id,
            packet_name=request.packet_name,
            source=request.source,
            source_uri=packet_source_uri,
            submitted_by=request.submitted_by,
            packet_fingerprint=packet_fingerprint,
            source_fingerprint=source_fingerprint,
            status=packet_status,
            next_stage=next_stage,
            document_count=len(created_documents),
            duplicate_detection=duplicate_detection,
            received_at_utc=request.received_at_utc,
            documents=tuple(created_documents),
        )


class SqlIntakeSourceRepository:
    """Persist and query durable intake-source definitions in Azure SQL."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def is_configured(self) -> bool:
        """Return whether Azure SQL source storage is configured."""

        return bool(self._settings.sql_connection_string)

    def list_intake_sources(self) -> IntakeSourceListResponse:
        """Return the configured intake sources ordered by name."""

        connection_string = self._settings.sql_connection_string
        if not connection_string:
            raise RuntimeError("Azure SQL source storage is not configured")

        with open_sql_connection(connection_string, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        sourceId,
                        sourceName,
                        description,
                        isEnabled,
                        ownerEmail,
                        pollingIntervalMinutes,
                        credentialsReference,
                        sourceKind,
                        settingsJson,
                        lastSeenAtUtc,
                        lastSuccessAtUtc,
                        lastErrorAtUtc,
                        lastErrorMessage,
                        createdAtUtc,
                        updatedAtUtc
                    FROM dbo.IntakeSources
                    ORDER BY sourceName ASC
                    """
                )
                rows = cursor.fetchall()

        return IntakeSourceListResponse(
            items=tuple(_build_intake_source_record_from_row(row) for row in rows)
        )

    def get_intake_source(self, source_id: str) -> IntakeSourceRecord:
        """Return one configured intake source by id."""

        connection_string = self._settings.sql_connection_string
        if not connection_string:
            raise RuntimeError("Azure SQL source storage is not configured")

        with open_sql_connection(connection_string, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        sourceId,
                        sourceName,
                        description,
                        isEnabled,
                        ownerEmail,
                        pollingIntervalMinutes,
                        credentialsReference,
                        sourceKind,
                        settingsJson,
                        lastSeenAtUtc,
                        lastSuccessAtUtc,
                        lastErrorAtUtc,
                        lastErrorMessage,
                        createdAtUtc,
                        updatedAtUtc
                    FROM dbo.IntakeSources
                    WHERE sourceId = %s
                    """,
                    (source_id,),
                )
                row = cursor.fetchone()

        if row is None:
            raise RuntimeError(f"Intake source '{source_id}' was not found.")

        return _build_intake_source_record_from_row(row)

    def create_intake_source(
        self,
        request: IntakeSourceCreateRequest,
    ) -> IntakeSourceRecord:
        """Create one durable intake-source definition."""

        connection_string = self._settings.sql_connection_string
        if not connection_string:
            raise RuntimeError("Azure SQL source storage is not configured")

        source_id = request.source_id or f"src_{uuid4().hex}"
        now = datetime.now(UTC)
        record = IntakeSourceRecord(
            source_id=source_id,
            source_name=request.source_name,
            description=request.description,
            is_enabled=request.is_enabled,
            owner_email=request.owner_email,
            polling_interval_minutes=request.polling_interval_minutes,
            credentials_reference=request.credentials_reference,
            configuration=request.configuration,
            created_at_utc=now,
            updated_at_utc=now,
        )

        with open_sql_connection(connection_string, autocommit=False) as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO dbo.IntakeSources (
                            sourceId,
                            sourceName,
                            sourceKind,
                            description,
                            isEnabled,
                            ownerEmail,
                            pollingIntervalMinutes,
                            credentialsReference,
                            settingsJson,
                            createdAtUtc,
                            updatedAtUtc
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            record.source_id,
                            record.source_name,
                            record.configuration.source_kind.value,
                            record.description,
                            record.is_enabled,
                            record.owner_email,
                            record.polling_interval_minutes,
                            record.credentials_reference,
                            record.configuration.model_dump_json(),
                            record.created_at_utc,
                            record.updated_at_utc,
                        ),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        return record

    def update_intake_source(
        self,
        source_id: str,
        request: IntakeSourceUpdateRequest,
    ) -> IntakeSourceRecord:
        """Replace one durable intake-source definition."""

        connection_string = self._settings.sql_connection_string
        if not connection_string:
            raise RuntimeError("Azure SQL source storage is not configured")

        existing_record = self.get_intake_source(source_id)
        now = datetime.now(UTC)
        updated_record = IntakeSourceRecord(
            source_id=existing_record.source_id,
            source_name=request.source_name,
            description=request.description,
            is_enabled=request.is_enabled,
            owner_email=request.owner_email,
            polling_interval_minutes=request.polling_interval_minutes,
            credentials_reference=request.credentials_reference,
            configuration=request.configuration,
            last_seen_at_utc=existing_record.last_seen_at_utc,
            last_success_at_utc=existing_record.last_success_at_utc,
            last_error_at_utc=existing_record.last_error_at_utc,
            last_error_message=existing_record.last_error_message,
            created_at_utc=existing_record.created_at_utc,
            updated_at_utc=now,
        )

        with open_sql_connection(connection_string, autocommit=False) as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE dbo.IntakeSources
                        SET
                            sourceName = %s,
                            sourceKind = %s,
                            description = %s,
                            isEnabled = %s,
                            ownerEmail = %s,
                            pollingIntervalMinutes = %s,
                            credentialsReference = %s,
                            settingsJson = %s,
                            updatedAtUtc = %s
                        WHERE sourceId = %s
                        """,
                        (
                            updated_record.source_name,
                            updated_record.configuration.source_kind.value,
                            updated_record.description,
                            updated_record.is_enabled,
                            updated_record.owner_email,
                            updated_record.polling_interval_minutes,
                            updated_record.credentials_reference,
                            updated_record.configuration.model_dump_json(),
                            updated_record.updated_at_utc,
                            updated_record.source_id,
                        ),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        return updated_record

    def set_intake_source_enablement(
        self,
        source_id: str,
        request: IntakeSourceEnablementRequest,
    ) -> IntakeSourceRecord:
        """Pause or resume one durable intake-source definition."""

        connection_string = self._settings.sql_connection_string
        if not connection_string:
            raise RuntimeError("Azure SQL source storage is not configured")

        existing_record = self.get_intake_source(source_id)
        updated_at_utc = datetime.now(UTC)

        with open_sql_connection(connection_string, autocommit=False) as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE dbo.IntakeSources
                        SET
                            isEnabled = %s,
                            updatedAtUtc = %s
                        WHERE sourceId = %s
                        """,
                        (
                            request.is_enabled,
                            updated_at_utc,
                            source_id,
                        ),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        return existing_record.model_copy(
            update={
                "is_enabled": request.is_enabled,
                "updated_at_utc": updated_at_utc,
            }
        )

    def delete_intake_source(
        self,
        source_id: str,
    ) -> IntakeSourceDeleteResponse:
        """Delete one durable intake-source definition."""

        connection_string = self._settings.sql_connection_string
        if not connection_string:
            raise RuntimeError("Azure SQL source storage is not configured")

        existing_record = self.get_intake_source(source_id)

        with open_sql_connection(connection_string, autocommit=False) as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM dbo.IntakeSources
                        WHERE sourceId = %s
                        """,
                        (source_id,),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        return IntakeSourceDeleteResponse(
            source_id=existing_record.source_id,
            source_name=existing_record.source_name,
        )

    def record_intake_source_execution(
        self,
        source_id: str,
        *,
        last_error_message: str | None,
        last_seen_at_utc: datetime,
        last_success_at_utc: datetime | None,
    ) -> None:
        """Persist the latest source execution timestamps and error state."""

        connection_string = self._settings.sql_connection_string
        if not connection_string:
            raise RuntimeError("Azure SQL source storage is not configured")

        with open_sql_connection(connection_string, autocommit=False) as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE dbo.IntakeSources
                        SET
                            lastSeenAtUtc = %s,
                            lastSuccessAtUtc = COALESCE(%s, lastSuccessAtUtc),
                            lastErrorAtUtc = %s,
                            lastErrorMessage = %s,
                            updatedAtUtc = %s
                        WHERE sourceId = %s
                        """,
                        (
                            last_seen_at_utc,
                            last_success_at_utc,
                            last_seen_at_utc if last_error_message else None,
                            last_error_message,
                            last_seen_at_utc,
                            source_id,
                        ),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise


class ServiceBusReviewQueuePublisher:
    """Publish review items to the manual review queue."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def is_configured(self) -> bool:
        """Return whether Service Bus connectivity is configured."""
        return bool(self._settings.service_bus_connection_string)

    def publish_review_item(self, review_item: ReviewQueueItem) -> None:
        """Publish a review item to the manual review queue."""
        if not self.is_configured():
            return

        connection_string = self._settings.service_bus_connection_string
        if connection_string is None:
            return

        message = ServiceBusMessage(json.dumps(review_item.model_dump(mode="json")))
        with ServiceBusClient.from_connection_string(
            connection_string
        ) as service_bus_client:
            with service_bus_client.get_queue_sender(
                queue_name=self._settings.review_queue_name
            ) as queue_sender:
                queue_sender.send_messages(message)