"""Unit tests for the manual packet-intake service."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from io import BytesIO
from typing import cast
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pytest import MonkeyPatch

from document_intelligence import manual_intake
from document_intelligence.models import (
    ArchivePreflightDisposition,
    ArchivePreflightResult,
    DocumentSource,
    DuplicateDetectionResult,
    DuplicateDetectionStatus,
    ManualPacketDocumentInput,
    ManualPacketDocumentRecord,
    ManualPacketIntakeRequest,
    ManualPacketIntakeResponse,
    ManualPacketStagedDocument,
    PacketStatus,
    ProcessingJobStatus,
    ProcessingStageName,
)
from document_intelligence.settings import AppSettings
from document_intelligence.utils.archive_expansion import UnsafeArchiveExpansionError
from document_intelligence.utils.blob_storage import BlobAsset


def build_settings(**overrides: object) -> AppSettings:
    """Build settings for the manual-intake tests."""
    values: dict[str, object] = {
        "raw_container_name": "raw-documents",
        "sql_connection_string": (
            "Server=tcp:test-sql.database.windows.net,1433;"
            "Database=docintel;User ID=docintel;Password=Password123!"
        ),
        "storage_connection_string": "UseDevelopmentStorage=true",
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def build_pdf_bytes(*, body: bytes = b"demo") -> bytes:
    """Build a small but structurally valid PDF fixture."""

    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n" + body + b"\n%%EOF"


def build_request() -> ManualPacketIntakeRequest:
    """Build a representative manual-intake request payload."""
    return ManualPacketIntakeRequest(
        packet_name="demo packet",
        source=DocumentSource.SCANNED_UPLOAD,
        submitted_by="operator@example.com",
        documents=(
            ManualPacketDocumentInput(
                file_name="sample.pdf",
                content_type="application/pdf",
                document_content_base64=base64.b64encode(build_pdf_bytes()).decode(
                    "ascii"
                ),
            ),
        ),
    )


def build_zip_bytes() -> bytes:
    """Build a minimal ZIP payload for archive-preflight tests."""

    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "supporting-document.pdf",
            build_pdf_bytes(body=b"archive test"),
        )
    return buffer.getvalue()


def build_zip_request() -> ManualPacketIntakeRequest:
    """Build a manual-intake request that uploads a ZIP archive."""

    return ManualPacketIntakeRequest(
        packet_name="archive packet",
        source=DocumentSource.SCANNED_UPLOAD,
        submitted_by="operator@example.com",
        documents=(
            ManualPacketDocumentInput(
                file_name="archive-batch.zip",
                content_type="application/zip",
                document_content_base64=base64.b64encode(build_zip_bytes()).decode(
                    "ascii"
                ),
            ),
        ),
    )


def build_nested_zip_bytes() -> bytes:
    """Build a nested ZIP payload for recursive archive-expansion tests."""

    nested_buffer = BytesIO()
    with ZipFile(nested_buffer, mode="w", compression=ZIP_DEFLATED) as nested_zip:
        nested_zip.writestr(
            "evidence/statement.pdf",
            build_pdf_bytes(body=b"nested archive"),
        )

    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("archive-child.zip", nested_buffer.getvalue())
    return buffer.getvalue()


def build_nested_zip_request() -> ManualPacketIntakeRequest:
    """Build a manual-intake request that uploads a nested ZIP archive."""

    return ManualPacketIntakeRequest(
        packet_name="nested archive packet",
        source=DocumentSource.SCANNED_UPLOAD,
        submitted_by="operator@example.com",
        documents=(
            ManualPacketDocumentInput(
                account_candidates=("acct_123",),
                file_name="nested-archive.zip",
                content_type="application/zip",
                document_content_base64=base64.b64encode(
                    build_nested_zip_bytes()
                ).decode("ascii"),
            ),
        ),
    )


def build_duplicate_member_zip_bytes() -> bytes:
    """Build a ZIP payload that contains the same archive member path twice."""

    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "duplicate/statement.pdf",
            build_pdf_bytes(body=b"archive first"),
        )
        archive.writestr(
            "duplicate/statement.pdf",
            build_pdf_bytes(body=b"archive second"),
        )
    return buffer.getvalue()


def build_duplicate_member_zip_request() -> ManualPacketIntakeRequest:
    """Build a manual-intake request with duplicate archive member paths."""

    return ManualPacketIntakeRequest(
        packet_name="duplicate archive packet",
        source=DocumentSource.SCANNED_UPLOAD,
        submitted_by="operator@example.com",
        documents=(
            ManualPacketDocumentInput(
                file_name="duplicate-archive.zip",
                content_type="application/zip",
                document_content_base64=base64.b64encode(
                    build_duplicate_member_zip_bytes()
                ).decode("ascii"),
            ),
        ),
    )


def build_corrupt_archive_request() -> ManualPacketIntakeRequest:
    """Build a manual-intake request that uploads a corrupt ZIP archive."""

    return ManualPacketIntakeRequest(
        packet_name="corrupt archive packet",
        source=DocumentSource.SCANNED_UPLOAD,
        submitted_by="operator@example.com",
        documents=(
            ManualPacketDocumentInput(
                file_name="broken-batch.zip",
                content_type="application/zip",
                document_content_base64=base64.b64encode(
                    b"PK\x03\x04broken-archive"
                ).decode("ascii"),
            ),
        ),
    )


def test_prepare_documents_rejects_packets_over_total_size_limit() -> None:
    """Manual intake should reject packets that exceed the configured size cap."""

    pdf_bytes = build_pdf_bytes(body=b"oversized-packet")
    request = ManualPacketIntakeRequest(
        packet_name="oversized packet",
        source=DocumentSource.SCANNED_UPLOAD,
        submitted_by="operator@example.com",
        documents=(
            ManualPacketDocumentInput(
                file_name="first.pdf",
                content_type="application/pdf",
                document_content_base64=base64.b64encode(pdf_bytes).decode("ascii"),
            ),
            ManualPacketDocumentInput(
                file_name="second.pdf",
                content_type="application/pdf",
                document_content_base64=base64.b64encode(pdf_bytes).decode("ascii"),
            ),
        ),
    )

    with pytest.raises(ValueError, match="total size limit"):
        manual_intake._prepare_documents(
            request,
            build_settings(packet_max_total_bytes=len(pdf_bytes) + 1),
        )


def test_prepare_documents_quarantines_password_protected_pdfs() -> None:
    """Password-protected PDFs should be quarantined before downstream OCR."""

    request = ManualPacketIntakeRequest(
        packet_name="protected pdf",
        source=DocumentSource.SCANNED_UPLOAD,
        submitted_by="operator@example.com",
        documents=(
            ManualPacketDocumentInput(
                file_name="protected.pdf",
                content_type="application/pdf",
                document_content_base64=base64.b64encode(
                    build_pdf_bytes(body=b"<< /Encrypt 5 0 R >>")
                ).decode("ascii"),
            ),
        ),
    )

    prepared_documents = manual_intake._prepare_documents(request, build_settings())

    assert prepared_documents[0].initial_processing_stage == (
        ProcessingStageName.QUARANTINE
    )
    assert prepared_documents[0].status == PacketStatus.QUARANTINED
    assert prepared_documents[0].safety_issues[0].code == "password_protected_pdf"


def test_prepare_documents_quarantines_malformed_openxml_files() -> None:
    """Malformed Office payloads should never reach archive expansion or OCR."""

    request = ManualPacketIntakeRequest(
        packet_name="malformed office",
        source=DocumentSource.SCANNED_UPLOAD,
        submitted_by="operator@example.com",
        documents=(
            ManualPacketDocumentInput(
                file_name="broken.docx",
                content_type=(
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
                document_content_base64=base64.b64encode(b"not-a-valid-docx").decode(
                    "ascii"
                ),
            ),
        ),
    )

    prepared_documents = manual_intake._prepare_documents(request, build_settings())

    assert prepared_documents[0].initial_processing_stage == (
        ProcessingStageName.QUARANTINE
    )
    assert prepared_documents[0].status == PacketStatus.QUARANTINED
    assert prepared_documents[0].safety_issues[0].code == "malformed_office_file"


def test_create_manual_packet_intake_requires_configured_storage() -> None:
    """Manual intake should fail fast when Blob storage is unavailable."""
    with pytest.raises(
        manual_intake.ManualIntakeConfigurationError,
        match="Blob storage is not configured",
    ):
        manual_intake.create_manual_packet_intake(
            build_request(),
            build_settings(storage_connection_string=None),
        )


def test_create_manual_packet_intake_rolls_back_staged_blobs_on_sql_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    """Blob assets should be deleted when SQL persistence fails after upload."""
    deleted_blob_names: list[str] = []

    class FailingRepository:
        """Repository stub that simulates a SQL persistence failure."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def detect_duplicate_packet(
            self,
            *,
            account_hint_ids: tuple[str, ...],
            file_hashes: tuple[str, ...],
            packet_fingerprint: str,
            source_fingerprint: str,
        ) -> DuplicateDetectionResult:
            del account_hint_ids, file_hashes, packet_fingerprint, source_fingerprint
            return DuplicateDetectionResult()

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
            del (
                duplicate_detection,
                packet_id,
                packet_fingerprint,
                request,
                source_fingerprint,
                staged_documents,
            )
            raise RuntimeError("sql insert failed")

    monkeypatch.setattr(
        manual_intake,
        "SqlOperatorWorkspaceRepository",
        FailingRepository,
    )
    monkeypatch.setattr(
        manual_intake,
        "upload_blob_bytes",
        lambda **kwargs: BlobAsset(
            blob_name=str(kwargs["blob_name"]),
            container_name=str(kwargs["container_name"]),
            content_length_bytes=len(kwargs["data"]),
            storage_uri=f"https://storage.example/{kwargs['blob_name']}",
        ),
    )
    monkeypatch.setattr(
        manual_intake,
        "delete_blob_asset",
        lambda **kwargs: deleted_blob_names.append(str(kwargs["blob_name"])),
    )

    with pytest.raises(RuntimeError, match="sql insert failed"):
        manual_intake.create_manual_packet_intake(build_request(), build_settings())

    assert len(deleted_blob_names) == 1
    assert deleted_blob_names[0].endswith("sample.pdf")


def test_create_manual_packet_intake_stages_files_before_persisting(
    monkeypatch: MonkeyPatch,
) -> None:
    """Manual intake should upload assets and forward staged metadata to SQL."""
    captured: dict[str, object] = {}

    class RecordingRepository:
        """Repository stub that captures the staged SQL payload."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def detect_duplicate_packet(
            self,
            *,
            account_hint_ids: tuple[str, ...],
            file_hashes: tuple[str, ...],
            packet_fingerprint: str,
            source_fingerprint: str,
        ) -> DuplicateDetectionResult:
            captured["account_hint_ids"] = account_hint_ids
            captured["file_hashes"] = file_hashes
            captured["packet_fingerprint"] = packet_fingerprint
            captured["source_fingerprint"] = source_fingerprint
            return DuplicateDetectionResult()

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
            captured["duplicate_detection"] = duplicate_detection
            captured["packet_id"] = packet_id
            captured["packet_name"] = request.packet_name
            captured["packet_fingerprint"] = packet_fingerprint
            captured["source_fingerprint"] = source_fingerprint
            captured["staged_documents"] = staged_documents
            first_staged_document = staged_documents[0]
            return ManualPacketIntakeResponse(
                packet_id=packet_id,
                packet_name=request.packet_name,
                source=request.source,
                source_uri=request.source_uri or f"manual://packets/{packet_id}",
                submitted_by=request.submitted_by,
                packet_fingerprint=packet_fingerprint,
                source_fingerprint=source_fingerprint,
                document_count=len(staged_documents),
                received_at_utc=request.received_at_utc,
                documents=(
                    ManualPacketDocumentRecord(
                        document_id=first_staged_document.document_id,
                        file_name=first_staged_document.file_name,
                        content_type=first_staged_document.content_type,
                        blob_uri=first_staged_document.blob_uri,
                        file_hash_sha256=first_staged_document.file_hash_sha256,
                        processing_job_id="job_demo_001",
                    ),
                ),
            )

    monkeypatch.setattr(
        manual_intake,
        "SqlOperatorWorkspaceRepository",
        RecordingRepository,
    )
    monkeypatch.setattr(
        manual_intake,
        "upload_blob_bytes",
        lambda **kwargs: BlobAsset(
            blob_name=str(kwargs["blob_name"]),
            container_name=str(kwargs["container_name"]),
            content_length_bytes=len(kwargs["data"]),
            storage_uri=f"https://storage.example/{kwargs['blob_name']}",
        ),
    )

    response = manual_intake.create_manual_packet_intake(
        build_request(),
        build_settings(),
    )

    assert response.document_count == 1
    assert str(captured["packet_id"]).startswith("pkt_")
    staged_documents = captured["staged_documents"]
    assert isinstance(staged_documents, tuple)
    first_staged_document = staged_documents[0]
    assert first_staged_document.archive_preflight.is_archive is False
    assert first_staged_document.content_type == "application/pdf"
    assert first_staged_document.blob_container_name == "raw-documents"
    assert first_staged_document.blob_uri.startswith("https://storage.example/")
    assert len(first_staged_document.file_hash_sha256) == 64
    assert first_staged_document.initial_processing_stage == ProcessingStageName.OCR
    assert first_staged_document.status == PacketStatus.RECEIVED


def test_create_manual_packet_intake_reuses_existing_packet_on_exact_duplicate(
    monkeypatch: MonkeyPatch,
) -> None:
    """Manual intake should return the prior packet response for exact duplicates."""

    class DuplicateRepository:
        """Repository stub that returns an exact duplicate before upload."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def detect_duplicate_packet(
            self,
            *,
            account_hint_ids: tuple[str, ...],
            file_hashes: tuple[str, ...],
            packet_fingerprint: str,
            source_fingerprint: str,
        ) -> DuplicateDetectionResult:
            del account_hint_ids, file_hashes, packet_fingerprint, source_fingerprint
            return DuplicateDetectionResult(
                reused_existing_packet_id="pkt_existing_001",
                should_skip_ingestion=True,
                status=DuplicateDetectionStatus.EXACT_DUPLICATE,
            )

        def get_manual_packet_intake_response(
            self,
            *,
            duplicate_detection: DuplicateDetectionResult | None,
            packet_id: str,
        ) -> ManualPacketIntakeResponse:
            assert duplicate_detection is not None
            return ManualPacketIntakeResponse(
                packet_id=packet_id,
                packet_name="existing packet",
                source=DocumentSource.SCANNED_UPLOAD,
                source_uri=f"manual://packets/{packet_id}",
                submitted_by="operator@example.com",
                packet_fingerprint=(
                    "5d71d766b5c276d48f749a4c1e4d233dde485feb34c0af62c2fbca4d1ca95e50"
                ),
                source_fingerprint=(
                    "d86d3f2c0214f31f9f19fe5f4d1f4c6b0f9bdb7612cd2925976ec965bbf64b0e"
                ),
                document_count=1,
                duplicate_detection=duplicate_detection,
                idempotency_reused_existing_packet=True,
                received_at_utc=datetime(2026, 4, 5, 16, 0, tzinfo=UTC),
                documents=(
                    ManualPacketDocumentRecord(
                        document_id="doc_existing_001",
                        file_name="sample.pdf",
                        content_type="application/pdf",
                        blob_uri="https://storage.example/raw/sample.pdf",
                        file_hash_sha256=(
                            "8d74e7eed6a76016ff7858d11d2f74c07a814e3cd3f81c4b6cf2e5f0376ea9d4"
                        ),
                        processing_job_id="job_existing_001",
                    ),
                ),
            )

    upload_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        manual_intake,
        "SqlOperatorWorkspaceRepository",
        DuplicateRepository,
    )

    def fake_upload_blob_bytes(**kwargs: object) -> BlobAsset:
        upload_calls.append(kwargs)
        data = kwargs["data"]
        return BlobAsset(
            blob_name=str(kwargs["blob_name"]),
            container_name=str(kwargs["container_name"]),
            content_length_bytes=len(cast(bytes, data)),
            storage_uri=f"https://storage.example/{kwargs['blob_name']}",
        )

    monkeypatch.setattr(
        manual_intake,
        "upload_blob_bytes",
        fake_upload_blob_bytes,
    )

    response = manual_intake.create_manual_packet_intake(
        build_request(),
        build_settings(),
    )

    assert response.packet_id == "pkt_existing_001"
    assert response.idempotency_reused_existing_packet is True
    assert response.duplicate_detection.status == (
        DuplicateDetectionStatus.EXACT_DUPLICATE
    )
    assert upload_calls == []


def test_create_manual_packet_intake_routes_zip_uploads_to_archive_expansion(
    monkeypatch: MonkeyPatch,
) -> None:
    """ZIP uploads should expand into a parent archive plus child documents."""

    captured: dict[str, object] = {}

    class ArchiveRepository:
        """Repository stub that returns the expanded archive staging payload."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def detect_duplicate_packet(
            self,
            *,
            account_hint_ids: tuple[str, ...],
            file_hashes: tuple[str, ...],
            packet_fingerprint: str,
            source_fingerprint: str,
        ) -> DuplicateDetectionResult:
            del account_hint_ids, file_hashes, packet_fingerprint, source_fingerprint
            return DuplicateDetectionResult()

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
            del duplicate_detection, packet_fingerprint, source_fingerprint
            captured["staged_documents"] = staged_documents
            return ManualPacketIntakeResponse(
                packet_id=packet_id,
                packet_name=request.packet_name,
                source=request.source,
                source_uri=request.source_uri or f"manual://packets/{packet_id}",
                submitted_by=request.submitted_by,
                status=PacketStatus.CLASSIFYING,
                next_stage=ProcessingStageName.CLASSIFICATION,
                document_count=len(staged_documents),
                received_at_utc=request.received_at_utc,
                documents=tuple(
                    ManualPacketDocumentRecord(
                        archive_preflight=staged_document.archive_preflight,
                        document_id=staged_document.document_id,
                        file_name=staged_document.file_name,
                        content_type=staged_document.content_type,
                        blob_uri=staged_document.blob_uri,
                        file_hash_sha256=staged_document.file_hash_sha256,
                        lineage=staged_document.lineage,
                        processing_job_id=f"job_archive_{index:03d}",
                        processing_stage=staged_document.initial_processing_stage,
                        processing_job_status=(
                            staged_document.initial_processing_job_status
                        ),
                        status=staged_document.status,
                    )
                    for index, staged_document in enumerate(staged_documents, start=1)
                ),
            )

    monkeypatch.setattr(
        manual_intake,
        "SqlOperatorWorkspaceRepository",
        ArchiveRepository,
    )
    monkeypatch.setattr(
        manual_intake,
        "upload_blob_bytes",
        lambda **kwargs: BlobAsset(
            blob_name=str(kwargs["blob_name"]),
            container_name=str(kwargs["container_name"]),
            content_length_bytes=len(kwargs["data"]),
            storage_uri=f"https://storage.example/{kwargs['blob_name']}",
        ),
    )

    response = manual_intake.create_manual_packet_intake(
        build_zip_request(),
        build_settings(),
    )

    staged_documents = cast(
        tuple[ManualPacketStagedDocument, ...],
        captured["staged_documents"],
    )
    parent_document = staged_documents[0]
    child_document = staged_documents[1]
    assert response.status == PacketStatus.CLASSIFYING
    assert response.next_stage == ProcessingStageName.CLASSIFICATION
    assert response.document_count == 2
    assert response.documents[0].processing_stage == (
        ProcessingStageName.ARCHIVE_EXPANSION
    )
    assert response.documents[0].processing_job_status == (
        ProcessingJobStatus.SUCCEEDED
    )
    assert response.documents[1].processing_stage == (
        ProcessingStageName.CLASSIFICATION
    )
    assert parent_document.archive_preflight.is_archive is True
    assert parent_document.archive_preflight.disposition == (
        ArchivePreflightDisposition.READY_FOR_EXPANSION
    )
    assert parent_document.archive_preflight.entry_count == 1
    assert parent_document.initial_processing_job_status == (
        ProcessingJobStatus.SUCCEEDED
    )
    assert parent_document.status == PacketStatus.COMPLETED
    assert child_document.lineage.parent_document_id == parent_document.document_id
    assert child_document.lineage.archive_member_path == "supporting-document.pdf"
    assert child_document.initial_processing_job_status == (
        ProcessingJobStatus.QUEUED
    )
    assert child_document.status == PacketStatus.CLASSIFYING


def test_create_manual_packet_intake_expands_nested_zips_with_lineage(
    monkeypatch: MonkeyPatch,
) -> None:
    """Nested ZIP children should preserve parent-child lineage across levels."""

    captured: dict[str, object] = {}

    class ArchiveRepository:
        """Repository stub that captures recursive archive staging payloads."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def detect_duplicate_packet(
            self,
            *,
            account_hint_ids: tuple[str, ...],
            file_hashes: tuple[str, ...],
            packet_fingerprint: str,
            source_fingerprint: str,
        ) -> DuplicateDetectionResult:
            del account_hint_ids, file_hashes, packet_fingerprint, source_fingerprint
            return DuplicateDetectionResult()

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
            del duplicate_detection, packet_fingerprint, source_fingerprint
            captured["staged_documents"] = staged_documents
            return ManualPacketIntakeResponse(
                packet_id=packet_id,
                packet_name=request.packet_name,
                source=request.source,
                source_uri=request.source_uri or f"manual://packets/{packet_id}",
                submitted_by=request.submitted_by,
                status=PacketStatus.CLASSIFYING,
                next_stage=ProcessingStageName.CLASSIFICATION,
                document_count=len(staged_documents),
                received_at_utc=request.received_at_utc,
                documents=tuple(
                    ManualPacketDocumentRecord(
                        archive_preflight=staged_document.archive_preflight,
                        document_id=staged_document.document_id,
                        file_name=staged_document.file_name,
                        content_type=staged_document.content_type,
                        blob_uri=staged_document.blob_uri,
                        file_hash_sha256=staged_document.file_hash_sha256,
                        lineage=staged_document.lineage,
                        processing_job_id=f"job_nested_{index:03d}",
                        processing_stage=staged_document.initial_processing_stage,
                        processing_job_status=(
                            staged_document.initial_processing_job_status
                        ),
                        status=staged_document.status,
                    )
                    for index, staged_document in enumerate(staged_documents, start=1)
                ),
            )

    monkeypatch.setattr(
        manual_intake,
        "SqlOperatorWorkspaceRepository",
        ArchiveRepository,
    )
    monkeypatch.setattr(
        manual_intake,
        "upload_blob_bytes",
        lambda **kwargs: BlobAsset(
            blob_name=str(kwargs["blob_name"]),
            container_name=str(kwargs["container_name"]),
            content_length_bytes=len(kwargs["data"]),
            storage_uri=f"https://storage.example/{kwargs['blob_name']}",
        ),
    )

    response = manual_intake.create_manual_packet_intake(
        build_nested_zip_request(),
        build_settings(),
    )

    staged_documents = cast(
        tuple[ManualPacketStagedDocument, ...],
        captured["staged_documents"],
    )
    parent_document = staged_documents[0]
    nested_archive_document = staged_documents[1]
    nested_leaf_document = staged_documents[2]
    assert response.document_count == 3
    assert parent_document.status == PacketStatus.COMPLETED
    assert nested_archive_document.file_name == "archive-child.zip"
    assert nested_archive_document.lineage.parent_document_id == (
        parent_document.document_id
    )
    assert nested_archive_document.account_candidates == ("acct_123",)
    assert nested_archive_document.lineage.archive_depth == 1
    assert nested_archive_document.status == PacketStatus.COMPLETED
    assert nested_leaf_document.file_name == "statement.pdf"
    assert nested_leaf_document.account_candidates == ("acct_123",)
    assert nested_leaf_document.lineage.parent_document_id == (
        nested_archive_document.document_id
    )
    assert nested_leaf_document.lineage.archive_depth == 2
    assert nested_leaf_document.lineage.archive_member_path == (
        "archive-child.zip/evidence/statement.pdf"
    )
    assert nested_leaf_document.initial_processing_stage == (
        ProcessingStageName.CLASSIFICATION
    )
    assert nested_leaf_document.status == PacketStatus.CLASSIFYING


def test_create_manual_packet_intake_quarantines_duplicate_archive_members(
    monkeypatch: MonkeyPatch,
) -> None:
    """Duplicate archive members should preserve lineage and quarantine the replayed path."""

    captured: dict[str, object] = {}

    class ArchiveRepository:
        """Repository stub that captures duplicate archive member staging."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def detect_duplicate_packet(
            self,
            *,
            account_hint_ids: tuple[str, ...],
            file_hashes: tuple[str, ...],
            packet_fingerprint: str,
            source_fingerprint: str,
        ) -> DuplicateDetectionResult:
            del account_hint_ids, file_hashes, packet_fingerprint, source_fingerprint
            return DuplicateDetectionResult()

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
            del duplicate_detection, packet_fingerprint, source_fingerprint
            captured["staged_documents"] = staged_documents
            return ManualPacketIntakeResponse(
                packet_id=packet_id,
                packet_name=request.packet_name,
                source=request.source,
                source_uri=request.source_uri or f"manual://packets/{packet_id}",
                submitted_by=request.submitted_by,
                status=PacketStatus.QUARANTINED,
                next_stage=ProcessingStageName.QUARANTINE,
                document_count=len(staged_documents),
                received_at_utc=request.received_at_utc,
                documents=tuple(
                    ManualPacketDocumentRecord(
                        archive_preflight=staged_document.archive_preflight,
                        document_id=staged_document.document_id,
                        file_name=staged_document.file_name,
                        content_type=staged_document.content_type,
                        blob_uri=staged_document.blob_uri,
                        file_hash_sha256=staged_document.file_hash_sha256,
                        lineage=staged_document.lineage,
                        processing_job_id=f"job_duplicate_{index:03d}",
                        processing_stage=staged_document.initial_processing_stage,
                        processing_job_status=(
                            staged_document.initial_processing_job_status
                        ),
                        status=staged_document.status,
                    )
                    for index, staged_document in enumerate(staged_documents, start=1)
                ),
            )

    monkeypatch.setattr(
        manual_intake,
        "SqlOperatorWorkspaceRepository",
        ArchiveRepository,
    )
    monkeypatch.setattr(
        manual_intake,
        "upload_blob_bytes",
        lambda **kwargs: BlobAsset(
            blob_name=str(kwargs["blob_name"]),
            container_name=str(kwargs["container_name"]),
            content_length_bytes=len(kwargs["data"]),
            storage_uri=f"https://storage.example/{kwargs['blob_name']}",
        ),
    )

    with pytest.warns(UserWarning, match="Duplicate name"):
        request = build_duplicate_member_zip_request()

    response = manual_intake.create_manual_packet_intake(
        request,
        build_settings(),
    )

    staged_documents = cast(
        tuple[ManualPacketStagedDocument, ...],
        captured["staged_documents"],
    )
    parent_document = staged_documents[0]
    first_child = staged_documents[1]
    duplicate_child = staged_documents[2]

    assert response.document_count == 3
    assert parent_document.status == PacketStatus.COMPLETED
    assert first_child.lineage.parent_document_id == parent_document.document_id
    assert first_child.lineage.archive_member_path == "duplicate/statement.pdf"
    assert first_child.initial_processing_stage == ProcessingStageName.CLASSIFICATION
    assert first_child.status == PacketStatus.CLASSIFYING
    assert duplicate_child.lineage.parent_document_id == parent_document.document_id
    assert duplicate_child.lineage.archive_member_path == "duplicate/statement.pdf"
    assert duplicate_child.archive_preflight.disposition == (
        ArchivePreflightDisposition.UNSAFE_ARCHIVE
    )
    assert "duplicate member path" in (
        duplicate_child.archive_preflight.message or ""
    )
    assert duplicate_child.initial_processing_stage == ProcessingStageName.QUARANTINE
    assert duplicate_child.status == PacketStatus.QUARANTINED


def test_create_manual_packet_intake_quarantines_unsafe_archive_expansion(
    monkeypatch: MonkeyPatch,
) -> None:
    """Archive-bomb guard failures should quarantine the uploaded archive."""

    captured: dict[str, object] = {}

    class QuarantineRepository:
        """Repository stub that captures unsafe archive routing."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def detect_duplicate_packet(
            self,
            *,
            account_hint_ids: tuple[str, ...],
            file_hashes: tuple[str, ...],
            packet_fingerprint: str,
            source_fingerprint: str,
        ) -> DuplicateDetectionResult:
            del account_hint_ids, file_hashes, packet_fingerprint, source_fingerprint
            return DuplicateDetectionResult()

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
            del duplicate_detection, packet_fingerprint, source_fingerprint
            captured["staged_documents"] = staged_documents
            first_document = staged_documents[0]
            return ManualPacketIntakeResponse(
                packet_id=packet_id,
                packet_name=request.packet_name,
                source=request.source,
                source_uri=request.source_uri or f"manual://packets/{packet_id}",
                submitted_by=request.submitted_by,
                status=PacketStatus.QUARANTINED,
                next_stage=ProcessingStageName.QUARANTINE,
                document_count=len(staged_documents),
                received_at_utc=request.received_at_utc,
                documents=(
                    ManualPacketDocumentRecord(
                        archive_preflight=first_document.archive_preflight,
                        document_id=first_document.document_id,
                        file_name=first_document.file_name,
                        content_type=first_document.content_type,
                        blob_uri=first_document.blob_uri,
                        file_hash_sha256=first_document.file_hash_sha256,
                        processing_job_id="job_quarantine_unsafe_001",
                        processing_stage=first_document.initial_processing_stage,
                        processing_job_status=(
                            first_document.initial_processing_job_status
                        ),
                        status=first_document.status,
                    ),
                ),
            )

    monkeypatch.setattr(
        manual_intake,
        "SqlOperatorWorkspaceRepository",
        QuarantineRepository,
    )
    monkeypatch.setattr(
        manual_intake,
        "expand_zip_archive",
        lambda document_bytes: (_ for _ in ()).throw(
            UnsafeArchiveExpansionError(
                ArchivePreflightResult(
                    archive_format="zip",
                    disposition=ArchivePreflightDisposition.UNSAFE_ARCHIVE,
                    entry_count=100,
                    is_archive=True,
                    message=(
                        "Archive expansion stopped because the archive-bomb "
                        "guard fired."
                    ),
                    total_uncompressed_bytes=10_000_000,
                )
            )
        ),
    )
    monkeypatch.setattr(
        manual_intake,
        "upload_blob_bytes",
        lambda **kwargs: BlobAsset(
            blob_name=str(kwargs["blob_name"]),
            container_name=str(kwargs["container_name"]),
            content_length_bytes=len(kwargs["data"]),
            storage_uri=f"https://storage.example/{kwargs['blob_name']}",
        ),
    )

    response = manual_intake.create_manual_packet_intake(
        build_zip_request(),
        build_settings(),
    )

    first_staged_document = cast(
        tuple[ManualPacketStagedDocument, ...],
        captured["staged_documents"],
    )[0]
    assert response.status == PacketStatus.QUARANTINED
    assert response.next_stage == ProcessingStageName.QUARANTINE
    assert first_staged_document.archive_preflight.disposition == (
        ArchivePreflightDisposition.UNSAFE_ARCHIVE
    )
    assert first_staged_document.initial_processing_stage == (
        ProcessingStageName.QUARANTINE
    )
    assert first_staged_document.status == PacketStatus.QUARANTINED


def test_create_manual_packet_intake_routes_corrupt_archive_to_quarantine(
    monkeypatch: MonkeyPatch,
) -> None:
    """Corrupt archives should be quarantined instead of queued for OCR."""

    captured: dict[str, object] = {}

    class QuarantineRepository:
        """Repository stub that returns the quarantine routing payload."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def detect_duplicate_packet(
            self,
            *,
            account_hint_ids: tuple[str, ...],
            file_hashes: tuple[str, ...],
            packet_fingerprint: str,
            source_fingerprint: str,
        ) -> DuplicateDetectionResult:
            del account_hint_ids, file_hashes, packet_fingerprint, source_fingerprint
            return DuplicateDetectionResult()

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
            del duplicate_detection, packet_fingerprint, source_fingerprint
            captured["staged_documents"] = staged_documents
            first_document = staged_documents[0]
            return ManualPacketIntakeResponse(
                packet_id=packet_id,
                packet_name=request.packet_name,
                source=request.source,
                source_uri=request.source_uri or f"manual://packets/{packet_id}",
                submitted_by=request.submitted_by,
                status=PacketStatus.QUARANTINED,
                next_stage=ProcessingStageName.QUARANTINE,
                document_count=len(staged_documents),
                received_at_utc=request.received_at_utc,
                documents=(
                    ManualPacketDocumentRecord(
                        archive_preflight=first_document.archive_preflight,
                        document_id=first_document.document_id,
                        file_name=first_document.file_name,
                        content_type=first_document.content_type,
                        blob_uri=first_document.blob_uri,
                        file_hash_sha256=first_document.file_hash_sha256,
                        processing_job_id="job_quarantine_001",
                        processing_stage=first_document.initial_processing_stage,
                        processing_job_status=(
                            first_document.initial_processing_job_status
                        ),
                        status=first_document.status,
                    ),
                ),
            )

    monkeypatch.setattr(
        manual_intake,
        "SqlOperatorWorkspaceRepository",
        QuarantineRepository,
    )
    monkeypatch.setattr(
        manual_intake,
        "upload_blob_bytes",
        lambda **kwargs: BlobAsset(
            blob_name=str(kwargs["blob_name"]),
            container_name=str(kwargs["container_name"]),
            content_length_bytes=len(kwargs["data"]),
            storage_uri=f"https://storage.example/{kwargs['blob_name']}",
        ),
    )

    response = manual_intake.create_manual_packet_intake(
        build_corrupt_archive_request(),
        build_settings(),
    )

    first_staged_document = cast(
        tuple[ManualPacketStagedDocument, ...],
        captured["staged_documents"],
    )[0]
    assert response.status == PacketStatus.QUARANTINED
    assert response.next_stage == ProcessingStageName.QUARANTINE
    assert response.documents[0].processing_stage == ProcessingStageName.QUARANTINE
    assert first_staged_document.archive_preflight.disposition == (
        ArchivePreflightDisposition.CORRUPT_ARCHIVE
    )
    assert first_staged_document.initial_processing_job_status == (
        ProcessingJobStatus.SUCCEEDED
    )
    assert first_staged_document.status == PacketStatus.QUARANTINED