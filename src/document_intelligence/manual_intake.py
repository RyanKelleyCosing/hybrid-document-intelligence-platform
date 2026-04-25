"""Manual packet-intake service for the first operator workflow slice."""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from document_intelligence.models import (
    ArchiveDocumentLineage,
    ArchivePreflightDisposition,
    ArchivePreflightResult,
    IssuerCategory,
    ManualPacketDocumentInput,
    ManualPacketIntakeRequest,
    ManualPacketIntakeResponse,
    ManualPacketStagedDocument,
    PacketStatus,
    ProcessingJobStatus,
    ProcessingStageName,
    PromptProfileId,
    SafetyIssue,
    SafetyIssueSeverity,
)
from document_intelligence.persistence import SqlOperatorWorkspaceRepository
from document_intelligence.safety import inspect_document_safety
from document_intelligence.settings import AppSettings
from document_intelligence.utils.archive_expansion import (
    UnsafeArchiveExpansionError,
    expand_zip_archive,
)
from document_intelligence.utils.archive_preflight import (
    inspect_document_archive_preflight,
)
from document_intelligence.utils.blob_storage import (
    delete_blob_asset,
    upload_blob_bytes,
)

MAX_MANUAL_INTAKE_DOCUMENT_BYTES = 15 * 1024 * 1024
SUPPORTED_MANUAL_INTAKE_CONTENT_TYPES = frozenset(
    {
        "application/msword",
        "application/pdf",
        "application/x-zip-compressed",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    }
)


class ManualIntakeConfigurationError(RuntimeError):
    """Raised when the operator manual-intake path is not fully configured."""


@dataclass(frozen=True)
class PreparedManualDocument:
    """Validated manual-intake content prepared before Blob upload."""

    account_candidates: tuple[str, ...]
    asset_role: str
    archive_preflight: ArchivePreflightResult
    content_type: str
    document_bytes: bytes
    document_id: str
    file_hash_sha256: str
    file_name: str
    initial_processing_job_status: ProcessingJobStatus
    initial_processing_stage: ProcessingStageName
    issuer_category: IssuerCategory
    issuer_name: str | None
    lineage: ArchiveDocumentLineage
    requested_prompt_profile_id: PromptProfileId | None
    safety_issues: tuple[SafetyIssue, ...]
    document_text: str | None
    source_summary: str | None
    source_tags: tuple[str, ...]
    status: PacketStatus


def _generate_packet_id(request: ManualPacketIntakeRequest) -> str:
    return request.packet_id or f"pkt_{uuid4().hex}"


def _generate_document_id(document: ManualPacketDocumentInput) -> str:
    return document.document_id or f"doc_{uuid4().hex}"


def _normalize_content_type(content_type: str) -> str:
    return content_type.split(";", maxsplit=1)[0].strip().lower()


def _hash_document_bytes(document_bytes: bytes) -> str:
    return hashlib.sha256(document_bytes).hexdigest()


def _build_prepared_document(
    *,
    account_candidates: tuple[str, ...] = (),
    archive_preflight: ArchivePreflightResult,
    asset_role: str = "original_upload",
    content_type: str,
    document_bytes: bytes,
    document_id: str,
    file_name: str,
    issuer_category: IssuerCategory = IssuerCategory.UNKNOWN,
    issuer_name: str | None = None,
    lineage: ArchiveDocumentLineage | None = None,
    requested_prompt_profile_id: PromptProfileId | None = None,
    safety_issues: tuple[SafetyIssue, ...] = (),
    document_text: str | None = None,
    source_summary: str | None = None,
    source_tags: tuple[str, ...] = (),
) -> PreparedManualDocument:
    """Build one prepared document with the derived initial processing route."""

    (
        initial_processing_stage,
        initial_processing_job_status,
        initial_status,
    ) = _resolve_initial_processing_route(archive_preflight, safety_issues)
    return PreparedManualDocument(
        account_candidates=account_candidates,
        asset_role=asset_role,
        archive_preflight=archive_preflight,
        content_type=content_type,
        document_bytes=document_bytes,
        document_id=document_id,
        file_hash_sha256=_hash_document_bytes(document_bytes),
        file_name=file_name,
        initial_processing_job_status=initial_processing_job_status,
        initial_processing_stage=initial_processing_stage,
        issuer_category=issuer_category,
        issuer_name=issuer_name,
        lineage=lineage or ArchiveDocumentLineage(),
        requested_prompt_profile_id=requested_prompt_profile_id,
        safety_issues=safety_issues,
        document_text=document_text,
        source_summary=source_summary,
        source_tags=source_tags,
        status=initial_status,
    )


def _is_supported_upload(
    *,
    archive_preflight: ArchivePreflightResult,
    content_type: str,
) -> bool:
    return content_type.startswith("image/") or (
        content_type in SUPPORTED_MANUAL_INTAKE_CONTENT_TYPES
    ) or archive_preflight.is_archive


def _resolve_initial_processing_route(
    archive_preflight: ArchivePreflightResult,
    safety_issues: tuple[SafetyIssue, ...],
) -> tuple[ProcessingStageName, ProcessingJobStatus, PacketStatus]:
    """Return the first persisted stage for the uploaded document."""

    if any(
        issue.severity == SafetyIssueSeverity.BLOCKING for issue in safety_issues
    ):
        return (
            ProcessingStageName.QUARANTINE,
            ProcessingJobStatus.SUCCEEDED,
            PacketStatus.QUARANTINED,
        )

    if (
        archive_preflight.disposition
        == ArchivePreflightDisposition.READY_FOR_EXPANSION
    ):
        return (
            ProcessingStageName.ARCHIVE_EXPANSION,
            ProcessingJobStatus.QUEUED,
            PacketStatus.ARCHIVE_EXPANDING,
        )

    if archive_preflight.is_archive:
        return (
            ProcessingStageName.QUARANTINE,
            ProcessingJobStatus.SUCCEEDED,
            PacketStatus.QUARANTINED,
        )

    return (
        ProcessingStageName.OCR,
        ProcessingJobStatus.QUEUED,
        PacketStatus.RECEIVED,
    )


def _decode_document_bytes(document: ManualPacketDocumentInput) -> bytes:
    try:
        decoded_bytes = base64.b64decode(
            document.document_content_base64,
            validate=True,
        )
    except (ValueError, binascii.Error) as error:
        raise ValueError(
            f"Manual intake document '{document.file_name}' is not valid base64."
        ) from error

    if not decoded_bytes:
        raise ValueError(
            f"Manual intake document '{document.file_name}' was empty after decoding."
        )

    if len(decoded_bytes) > MAX_MANUAL_INTAKE_DOCUMENT_BYTES:
        raise ValueError(
            f"Manual intake document '{document.file_name}' exceeds the 15 MB limit."
        )

    return decoded_bytes


def _prepare_documents(
    request: ManualPacketIntakeRequest,
    settings: AppSettings,
) -> tuple[PreparedManualDocument, ...]:
    """Validate incoming documents and compute their deterministic hashes."""

    prepared_documents: list[PreparedManualDocument] = []
    packet_total_bytes = 0
    for document in request.documents:
        document_bytes = _decode_document_bytes(document)
        packet_total_bytes += len(document_bytes)
        if packet_total_bytes > settings.packet_max_total_bytes:
            max_megabytes = settings.packet_max_total_bytes // (1024 * 1024)
            raise ValueError(
                f"Manual intake packet '{request.packet_name}' exceeds the "
                f"{max_megabytes} MB total size limit."
            )

        normalized_content_type = _normalize_content_type(document.content_type)
        archive_preflight = inspect_document_archive_preflight(
            content_type=normalized_content_type,
            document_bytes=document_bytes,
            file_name=document.file_name,
        )
        safety_issues = inspect_document_safety(
            content_type=normalized_content_type,
            document_bytes=document_bytes,
            file_name=document.file_name,
        )
        if not _is_supported_upload(
            archive_preflight=archive_preflight,
            content_type=normalized_content_type,
        ):
            raise ValueError(
                "Manual intake only supports PDF, image, Office, and archive "
                "documents."
            )
        prepared_documents.append(
            _build_prepared_document(
                account_candidates=document.account_candidates,
                archive_preflight=archive_preflight,
                content_type=normalized_content_type,
                document_bytes=document_bytes,
                document_id=_generate_document_id(document),
                file_name=document.file_name,
                document_text=document.document_text,
                issuer_category=document.issuer_category,
                issuer_name=document.issuer_name,
                requested_prompt_profile_id=(
                    document.requested_prompt_profile_id
                ),
                safety_issues=safety_issues,
                source_summary=document.source_summary,
                source_tags=document.source_tags,
            )
        )

    return tuple(prepared_documents)


def _build_archive_member_prepared_document(
    *,
    archive_depth: int,
    archive_preflight: ArchivePreflightResult | None = None,
    parent_document_id: str,
    parent_document: PreparedManualDocument,
    member_content_type: str,
    member_file_name: str,
    member_path: str,
    member_bytes: bytes,
) -> PreparedManualDocument:
    """Build one prepared child document extracted from an archive."""

    if archive_preflight is None:
        archive_preflight = inspect_document_archive_preflight(
            content_type=member_content_type,
            document_bytes=member_bytes,
            file_name=member_file_name,
        )
    safety_issues = inspect_document_safety(
        content_type=member_content_type,
        document_bytes=member_bytes,
        file_name=member_file_name,
    )
    lineage = ArchiveDocumentLineage(
        archive_depth=archive_depth,
        archive_member_path=member_path,
        parent_document_id=parent_document_id,
    )
    if not _is_supported_upload(
        archive_preflight=archive_preflight,
        content_type=member_content_type,
    ):
        archive_preflight = ArchivePreflightResult(
            disposition=ArchivePreflightDisposition.NOT_ARCHIVE,
            is_archive=False,
            message=(
                "The extracted archive member type is not supported by the "
                "current intake path and was routed to quarantine."
            ),
        )

    child_document = _build_prepared_document(
        account_candidates=parent_document.account_candidates,
        archive_preflight=archive_preflight,
        asset_role="archive_extracted_member",
        content_type=member_content_type,
        document_bytes=member_bytes,
        document_id=f"doc_{uuid4().hex}",
        file_name=member_file_name,
        issuer_category=parent_document.issuer_category,
        issuer_name=parent_document.issuer_name,
        lineage=lineage,
        requested_prompt_profile_id=parent_document.requested_prompt_profile_id,
        safety_issues=safety_issues,
        source_summary=parent_document.source_summary,
        source_tags=parent_document.source_tags,
    )
    if child_document.initial_processing_stage == ProcessingStageName.QUARANTINE:
        return child_document

    if archive_preflight.message and not archive_preflight.is_archive:
        return replace(
            child_document,
            initial_processing_job_status=ProcessingJobStatus.SUCCEEDED,
            initial_processing_stage=ProcessingStageName.QUARANTINE,
            status=PacketStatus.QUARANTINED,
        )

    if not archive_preflight.is_archive:
        return replace(
            child_document,
            initial_processing_stage=ProcessingStageName.CLASSIFICATION,
            status=PacketStatus.CLASSIFYING,
        )

    return child_document


def _expand_prepared_documents(
    prepared_documents: tuple[PreparedManualDocument, ...],
) -> tuple[PreparedManualDocument, ...]:
    """Expand supported archive parents into child prepared documents."""

    expanded_documents: list[PreparedManualDocument] = []
    for prepared_document in prepared_documents:
        if (
            prepared_document.archive_preflight.disposition
            != ArchivePreflightDisposition.READY_FOR_EXPANSION
        ):
            expanded_documents.append(prepared_document)
            continue

        try:
            archive_members = expand_zip_archive(prepared_document.document_bytes)
        except UnsafeArchiveExpansionError as error:
            expanded_documents.append(
                replace(
                    prepared_document,
                    archive_preflight=error.archive_preflight,
                    initial_processing_job_status=ProcessingJobStatus.SUCCEEDED,
                    initial_processing_stage=ProcessingStageName.QUARANTINE,
                    status=PacketStatus.QUARANTINED,
                )
            )
            continue

        expanded_documents.append(
            replace(
                prepared_document,
                initial_processing_job_status=ProcessingJobStatus.SUCCEEDED,
                status=PacketStatus.COMPLETED,
            )
        )
        expanded_archive_documents_by_path: dict[str, PreparedManualDocument] = {}
        for archive_member in archive_members:
            parent_document = prepared_document
            if archive_member.parent_archive_member_path is not None:
                parent_document = expanded_archive_documents_by_path[
                    archive_member.parent_archive_member_path
                ]

            child_document = _build_archive_member_prepared_document(
                archive_depth=archive_member.archive_depth,
                archive_preflight=archive_member.archive_preflight,
                member_bytes=archive_member.document_bytes,
                member_content_type=archive_member.content_type,
                member_file_name=archive_member.file_name,
                member_path=archive_member.archive_member_path,
                parent_document=parent_document,
                parent_document_id=parent_document.document_id,
            )

            if (
                child_document.archive_preflight.disposition
                == ArchivePreflightDisposition.READY_FOR_EXPANSION
            ):
                child_document = replace(
                    child_document,
                    initial_processing_job_status=ProcessingJobStatus.SUCCEEDED,
                    status=PacketStatus.COMPLETED,
                )
                expanded_archive_documents_by_path[
                    archive_member.archive_member_path
                ] = child_document

            expanded_documents.append(child_document)

    return tuple(expanded_documents)


def _build_packet_fingerprint(
    request: ManualPacketIntakeRequest,
    prepared_documents: tuple[PreparedManualDocument, ...],
) -> str:
    """Build a deterministic packet fingerprint from the request content."""

    packet_components = [
        request.source.value,
        (request.source_uri or "").strip().lower(),
        request.packet_name.strip().lower(),
        *sorted(document.file_hash_sha256 for document in prepared_documents),
    ]
    return hashlib.sha256("|".join(packet_components).encode("utf-8")).hexdigest()


def _build_source_fingerprint(request: ManualPacketIntakeRequest) -> str:
    """Build a deterministic fingerprint for source-level idempotency checks."""

    source_components = [
        request.source.value,
        (request.source_uri or "").strip().lower(),
        request.packet_name.strip().lower(),
        (request.submitted_by or "").strip().lower(),
    ]
    return hashlib.sha256("|".join(source_components).encode("utf-8")).hexdigest()


def _collect_account_hint_ids(
    request: ManualPacketIntakeRequest,
) -> tuple[str, ...]:
    """Return the unique account hints supplied with a packet intake request."""

    return tuple(
        sorted(
            {
                account_id
                for document in request.documents
                for account_id in document.account_candidates
            }
        )
    )


def _build_blob_name(
    *,
    document_id: str,
    file_name: str,
    packet_id: str,
    request: ManualPacketIntakeRequest,
) -> str:
    normalized_file_name = Path(file_name).name or f"{document_id}.bin"
    received_path = request.received_at_utc.strftime("%Y/%m/%d")
    return (
        f"manual-intake/{received_path}/{packet_id}/{document_id}/"
        f"{normalized_file_name}"
    )


def _validate_settings(settings: AppSettings) -> None:
    if not settings.storage_connection_string:
        raise ManualIntakeConfigurationError(
            "Blob storage is not configured for manual packet intake."
        )

    repository = SqlOperatorWorkspaceRepository(settings)
    if not repository.is_configured():
        raise ManualIntakeConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )


def create_manual_packet_intake(
    request: ManualPacketIntakeRequest,
    settings: AppSettings,
) -> ManualPacketIntakeResponse:
    """Stage a packet upload into Blob storage and persist its SQL state."""
    _validate_settings(settings)

    storage_connection_string = settings.storage_connection_string
    if storage_connection_string is None:
        raise ManualIntakeConfigurationError(
            "Blob storage is not configured for manual packet intake."
        )

    repository = SqlOperatorWorkspaceRepository(settings)
    prepared_documents = _expand_prepared_documents(
        _prepare_documents(request, settings)
    )
    packet_id = _generate_packet_id(request)
    packet_fingerprint = _build_packet_fingerprint(request, prepared_documents)
    source_fingerprint = _build_source_fingerprint(request)
    duplicate_detection = repository.detect_duplicate_packet(
        account_hint_ids=_collect_account_hint_ids(request),
        file_hashes=tuple(
            document.file_hash_sha256 for document in prepared_documents
        ),
        packet_fingerprint=packet_fingerprint,
        source_fingerprint=source_fingerprint,
    )
    if duplicate_detection.should_skip_ingestion:
        existing_packet_id = duplicate_detection.reused_existing_packet_id
        if existing_packet_id is None:
            raise RuntimeError(
                "Duplicate packet detection returned no existing packet id."
            )
        return repository.get_manual_packet_intake_response(
            duplicate_detection=duplicate_detection,
            packet_id=existing_packet_id,
        )

    staged_documents: list[ManualPacketStagedDocument] = []

    try:
        for prepared_document in prepared_documents:
            blob_name = _build_blob_name(
                document_id=prepared_document.document_id,
                file_name=prepared_document.file_name,
                packet_id=packet_id,
                request=request,
            )
            stored_asset = upload_blob_bytes(
                blob_name=blob_name,
                container_name=settings.raw_container_name,
                content_type=prepared_document.content_type,
                data=prepared_document.document_bytes,
                storage_connection_string=storage_connection_string,
            )
            staged_documents.append(
                ManualPacketStagedDocument(
                    asset_role=prepared_document.asset_role,
                    archive_preflight=prepared_document.archive_preflight,
                    safety_issues=prepared_document.safety_issues,
                    document_id=prepared_document.document_id,
                    file_name=prepared_document.file_name,
                    content_type=prepared_document.content_type,
                    lineage=prepared_document.lineage,
                    blob_container_name=stored_asset.container_name,
                    blob_name=stored_asset.blob_name,
                    blob_uri=stored_asset.storage_uri,
                    content_length_bytes=stored_asset.content_length_bytes,
                    file_hash_sha256=prepared_document.file_hash_sha256,
                    initial_processing_job_status=(
                        prepared_document.initial_processing_job_status
                    ),
                    initial_processing_stage=(
                        prepared_document.initial_processing_stage
                    ),
                    issuer_name=prepared_document.issuer_name,
                    issuer_category=prepared_document.issuer_category,
                    requested_prompt_profile_id=(
                        prepared_document.requested_prompt_profile_id
                    ),
                    source_summary=prepared_document.source_summary,
                    source_tags=prepared_document.source_tags,
                    account_candidates=prepared_document.account_candidates,
                    document_text=prepared_document.document_text,
                    source_uri=request.source_uri,
                    status=prepared_document.status,
                )
            )

        return repository.create_manual_packet_intake(
            duplicate_detection=duplicate_detection,
            packet_id=packet_id,
            packet_fingerprint=packet_fingerprint,
            request=request,
            source_fingerprint=source_fingerprint,
            staged_documents=tuple(staged_documents),
        )
    except Exception:
        for staged_document in staged_documents:
            try:
                delete_blob_asset(
                    blob_name=staged_document.blob_name,
                    container_name=staged_document.blob_container_name,
                    storage_connection_string=storage_connection_string,
                )
            except Exception:
                logging.exception(
                    "Unable to roll back staged blob asset for document %s.",
                    staged_document.document_id,
                )
        raise