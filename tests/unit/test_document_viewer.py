"""Unit tests for protected document viewer helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pytest import MonkeyPatch

from document_intelligence import document_viewer
from document_intelligence.models import (
    DocumentAssetRecord,
    DocumentSource,
    PacketDocumentRecord,
    PacketRecord,
    PacketStatus,
    PacketWorkspaceSnapshot,
)
from document_intelligence.settings import AppSettings


def build_settings(**overrides: object) -> AppSettings:
    """Build app settings for document viewer tests."""

    values: dict[str, object] = {
        "sql_connection_string": "Server=tcp:test.database.windows.net;",
        "storage_connection_string": "UseDevelopmentStorage=true",
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def create_snapshot(
    *,
    assets: tuple[DocumentAssetRecord, ...] = (),
    document_status: PacketStatus = PacketStatus.RECEIVED,
    source_uri: str = "az://raw-documents/fallback/doc-3001.pdf",
) -> PacketWorkspaceSnapshot:
    """Build a representative packet workspace snapshot for preview tests."""

    timestamp = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
    return PacketWorkspaceSnapshot(
        packet=PacketRecord(
            created_at_utc=timestamp,
            packet_id="pkt-3001",
            packet_name="demo packet",
            received_at_utc=timestamp,
            source=DocumentSource.SCANNED_UPLOAD,
            source_uri=source_uri,
            status=PacketStatus.RECEIVED,
            updated_at_utc=timestamp,
        ),
        documents=(
            PacketDocumentRecord(
                content_type="application/pdf",
                created_at_utc=timestamp,
                document_id="doc-3001",
                file_name="statement.pdf",
                packet_id="pkt-3001",
                received_at_utc=timestamp,
                source=DocumentSource.SCANNED_UPLOAD,
                source_uri=source_uri,
                status=document_status,
                updated_at_utc=timestamp,
            ),
        ),
        document_assets=assets,
    )


def test_resolve_preview_asset_raises_when_sql_is_unconfigured(
    monkeypatch: MonkeyPatch,
) -> None:
    """Preview resolution should fail fast when SQL-backed operator state is absent."""

    class FakeRepository:
        """Repository stub that simulates an unconfigured SQL environment."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return False

    monkeypatch.setattr(document_viewer, "SqlOperatorStateRepository", FakeRepository)

    with pytest.raises(
        document_viewer.DocumentPreviewConfigurationError,
        match="Azure SQL operator-state storage is not configured",
    ):
        document_viewer._resolve_preview_asset(
            "pkt-3001",
            "doc-3001",
            build_settings(),
        )


def test_resolve_preview_asset_blocks_quarantined_documents(
    monkeypatch: MonkeyPatch,
) -> None:
    """Quarantined documents should stay blocked unless the override is enabled."""

    snapshot = create_snapshot(document_status=PacketStatus.QUARANTINED)

    class FakeRepository:
        """Repository stub that returns one packet workspace snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(self, packet_id: str) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt-3001"
            return snapshot

    monkeypatch.setattr(document_viewer, "SqlOperatorStateRepository", FakeRepository)

    with pytest.raises(
        document_viewer.DocumentPreviewPolicyError,
        match="is quarantined and cannot be previewed",
    ):
        document_viewer._resolve_preview_asset(
            "pkt-3001",
            "doc-3001",
            build_settings(),
        )


def test_resolve_preview_asset_prefers_original_upload_asset(
    monkeypatch: MonkeyPatch,
) -> None:
    """Preview selection should prefer the original upload over derived assets."""

    timestamp = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
    snapshot = create_snapshot(
        assets=(
            DocumentAssetRecord(
                asset_id="asset-archive",
                asset_role="archive_extracted_member",
                blob_name="archive/member.pdf",
                container_name="processed-documents",
                content_length_bytes=512,
                content_type="application/pdf",
                created_at_utc=timestamp,
                document_id="doc-3001",
                packet_id="pkt-3001",
                storage_uri="https://storage.example/processed-documents/archive/member.pdf",
            ),
            DocumentAssetRecord(
                asset_id="asset-original",
                asset_role="original_upload",
                blob_name="originals/statement.pdf",
                container_name="raw-documents",
                content_length_bytes=1024,
                content_type="application/pdf",
                created_at_utc=timestamp,
                document_id="doc-3001",
                packet_id="pkt-3001",
                storage_uri="https://storage.example/raw-documents/originals/statement.pdf",
            ),
        )
    )

    class FakeRepository:
        """Repository stub that returns a snapshot with multiple preview assets."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(self, packet_id: str) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt-3001"
            return snapshot

    monkeypatch.setattr(document_viewer, "SqlOperatorStateRepository", FakeRepository)

    resolved_asset = document_viewer._resolve_preview_asset(
        "pkt-3001",
        "doc-3001",
        build_settings(),
    )

    assert resolved_asset.container_name == "raw-documents"
    assert resolved_asset.blob_name == "originals/statement.pdf"
    assert resolved_asset.content_type == "application/pdf"
    assert resolved_asset.file_name == "statement.pdf"


def test_resolve_preview_asset_falls_back_to_blob_source_uri(
    monkeypatch: MonkeyPatch,
) -> None:
    """Preview selection should fall back to the persisted blob-style source URI."""

    snapshot = create_snapshot(source_uri="az://raw-documents/fallback/doc-3001.pdf")

    class FakeRepository:
        """Repository stub that returns a snapshot without document assets."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(self, packet_id: str) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt-3001"
            return snapshot

    monkeypatch.setattr(document_viewer, "SqlOperatorStateRepository", FakeRepository)

    resolved_asset = document_viewer._resolve_preview_asset(
        "pkt-3001",
        "doc-3001",
        build_settings(),
    )

    assert resolved_asset.container_name == "raw-documents"
    assert resolved_asset.blob_name == "fallback/doc-3001.pdf"
    assert resolved_asset.content_type == "application/pdf"


def test_get_packet_document_preview_downloads_selected_blob(
    monkeypatch: MonkeyPatch,
) -> None:
    """Preview downloads should use the resolved asset and storage connection."""

    captured: dict[str, str] = {}

    monkeypatch.setattr(
        document_viewer,
        "_resolve_preview_asset",
        lambda packet_id, document_id, settings: document_viewer._ResolvedPreviewAsset(
            blob_name="originals/statement.pdf",
            container_name="raw-documents",
            content_type="application/pdf",
            file_name="statement.pdf",
        ),
    )

    def fake_download_blob_bytes(
        *,
        blob_name: str,
        container_name: str,
        storage_connection_string: str,
    ) -> bytes:
        captured["blob_name"] = blob_name
        captured["container_name"] = container_name
        captured["storage_connection_string"] = storage_connection_string
        return b"pdf-bytes"

    monkeypatch.setattr(document_viewer, "download_blob_bytes", fake_download_blob_bytes)

    preview = document_viewer.get_packet_document_preview(
        "pkt-3001",
        "doc-3001",
        build_settings(),
    )

    assert preview.content == b"pdf-bytes"
    assert preview.content_type == "application/pdf"
    assert preview.file_name == "statement.pdf"
    assert captured == {
        "blob_name": "originals/statement.pdf",
        "container_name": "raw-documents",
        "storage_connection_string": "UseDevelopmentStorage=true",
    }