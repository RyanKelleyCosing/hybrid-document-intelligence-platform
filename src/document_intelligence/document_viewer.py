"""Protected packet-document preview helpers for the operator viewer."""

from __future__ import annotations

from dataclasses import dataclass

from document_intelligence.inspection import parse_blob_source_uri
from document_intelligence.models import PacketStatus
from document_intelligence.operator_state import SqlOperatorStateRepository
from document_intelligence.settings import AppSettings
from document_intelligence.utils.blob_storage import download_blob_bytes


class DocumentPreviewConfigurationError(RuntimeError):
    """Raised when the protected document-preview route is not configured."""


class DocumentPreviewPolicyError(RuntimeError):
    """Raised when preview policy blocks access to one packet document."""


@dataclass(frozen=True)
class PacketDocumentPreview:
    """Binary preview payload returned for one packet document."""

    content: bytes
    content_type: str
    file_name: str


@dataclass(frozen=True)
class _ResolvedPreviewAsset:
    """Persisted preview asset selected for one packet document."""

    blob_name: str
    container_name: str
    content_type: str
    file_name: str


def _resolve_preview_asset(
    packet_id: str,
    document_id: str,
    settings: AppSettings,
) -> _ResolvedPreviewAsset:
    """Return the blob container, blob name, and preview content type."""

    repository = SqlOperatorStateRepository(settings)
    if not repository.is_configured():
        raise DocumentPreviewConfigurationError(
            "Azure SQL operator-state storage is not configured."
        )

    snapshot = repository.get_packet_workspace_snapshot(packet_id)
    document = next(
        (candidate for candidate in snapshot.documents if candidate.document_id == document_id),
        None,
    )
    if document is None:
        raise RuntimeError(
            f"Packet document '{document_id}' was not found in packet '{packet_id}'."
        )

    if (
        document.status == PacketStatus.QUARANTINED
        and not settings.allow_quarantined_document_previews
    ):
        raise DocumentPreviewPolicyError(
            f"Packet document '{document_id}' is quarantined and cannot be previewed."
        )

    selected_asset = None
    selected_priority = 99
    for asset in snapshot.document_assets:
        if asset.document_id != document_id:
            continue

        candidate_priority = {
            "original_upload": 0,
            "archive_extracted_member": 1,
        }.get(asset.asset_role, 99)
        if selected_asset is None or candidate_priority < selected_priority:
            selected_asset = asset
            selected_priority = candidate_priority

    if selected_asset is not None:
        return _ResolvedPreviewAsset(
            blob_name=selected_asset.blob_name,
            container_name=selected_asset.container_name,
            content_type=selected_asset.content_type,
            file_name=document.file_name,
        )

    if document.source_uri:
        blob_reference = parse_blob_source_uri(document.source_uri)
        if blob_reference is not None:
            container_name, blob_name = blob_reference
            return _ResolvedPreviewAsset(
                blob_name=blob_name,
                container_name=container_name,
                content_type=document.content_type,
                file_name=document.file_name,
            )

    raise RuntimeError(
        f"Packet document '{document_id}' could not be previewed because no Blob asset is stored."
    )


def get_packet_document_preview(
    packet_id: str,
    document_id: str,
    settings: AppSettings,
) -> PacketDocumentPreview:
    """Return the protected binary preview for one packet document."""

    if not settings.storage_connection_string:
        raise DocumentPreviewConfigurationError(
            "Azure Blob storage is not configured for document previews."
        )

    resolved_asset = _resolve_preview_asset(
        packet_id,
        document_id,
        settings,
    )
    return PacketDocumentPreview(
        content=download_blob_bytes(
            blob_name=resolved_asset.blob_name,
            container_name=resolved_asset.container_name,
            storage_connection_string=settings.storage_connection_string,
        ),
        content_type=resolved_asset.content_type,
        file_name=resolved_asset.file_name,
    )