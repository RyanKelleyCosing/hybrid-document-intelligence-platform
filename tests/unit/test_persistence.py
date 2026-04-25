"""Unit tests for manual-intake SQL persistence helpers."""

from __future__ import annotations

import base64
import json
from contextlib import contextmanager
from types import TracebackType

from pytest import MonkeyPatch

import document_intelligence.persistence as persistence
from document_intelligence.models import (
    ArchiveDocumentLineage,
    ArchivePreflightDisposition,
    ArchivePreflightResult,
    DocumentSource,
    DuplicateDetectionResult,
    ManualPacketDocumentInput,
    ManualPacketIntakeRequest,
    ManualPacketStagedDocument,
    PacketStatus,
    ProcessingJobStatus,
    ProcessingStageName,
    SafetyIssue,
    SafetyIssueSeverity,
)
from document_intelligence.settings import AppSettings


def build_settings() -> AppSettings:
    """Build app settings for SQL persistence tests."""

    return AppSettings.model_validate(
        {
            "sql_connection_string": (
                "Server=tcp:test-sql.database.windows.net,1433;"
                "Database=docintel;User ID=docintel;Password=Password123!"
            )
        }
    )


def build_request() -> ManualPacketIntakeRequest:
    """Build a minimal manual-intake request for persistence tests."""

    return ManualPacketIntakeRequest(
        packet_name="archive packet",
        source=DocumentSource.SCANNED_UPLOAD,
        submitted_by="operator@example.com",
        documents=(
            ManualPacketDocumentInput(
                file_name="archive.zip",
                content_type="application/zip",
                document_content_base64=base64.b64encode(b"PK\x03\x04stub").decode(
                    "ascii"
                ),
            ),
        ),
    )


class FakeCursor:
    """A DB-API cursor stub that records executed statements."""

    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback

    def execute(
        self,
        statement: str,
        params: tuple[object, ...] | None = None,
    ) -> None:
        normalized_statement = " ".join(statement.split())
        self._connection.executed_statements.append((normalized_statement, params))


class FakeConnection:
    """A DB-API connection stub that records executed statements."""

    def __init__(self) -> None:
        self.committed = False
        self.executed_statements: list[tuple[str, tuple[object, ...] | None]] = []
        self.rolled_back = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_create_manual_packet_intake_persists_lineage_and_review_tasks(
    monkeypatch: MonkeyPatch,
) -> None:
    """Archive child documents should persist lineage and blocked-review tasks."""

    connection = FakeConnection()

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(persistence, "open_sql_connection", fake_open_sql_connection)

    repository = persistence.SqlOperatorWorkspaceRepository(build_settings())
    response = repository.create_manual_packet_intake(
        duplicate_detection=DuplicateDetectionResult(),
        packet_id="pkt_archive_001",
        packet_fingerprint="a" * 64,
        request=build_request(),
        source_fingerprint="b" * 64,
        staged_documents=(
            ManualPacketStagedDocument(
                asset_role="original_upload",
                archive_preflight=ArchivePreflightResult(
                    archive_format="zip",
                    disposition=ArchivePreflightDisposition.READY_FOR_EXPANSION,
                    entry_count=1,
                    is_archive=True,
                ),
                document_id="doc_archive_parent",
                file_name="archive.zip",
                content_type="application/zip",
                blob_container_name="raw-documents",
                blob_name="archive.zip",
                blob_uri="https://storage.example/archive.zip",
                content_length_bytes=128,
                file_hash_sha256="c" * 64,
                initial_processing_job_status=ProcessingJobStatus.SUCCEEDED,
                initial_processing_stage=ProcessingStageName.ARCHIVE_EXPANSION,
                status=PacketStatus.COMPLETED,
            ),
            ManualPacketStagedDocument(
                asset_role="archive_extracted_member",
                archive_preflight=ArchivePreflightResult(
                    archive_format="rar",
                    disposition=ArchivePreflightDisposition.UNSUPPORTED_ARCHIVE,
                    is_archive=True,
                    message="Unsupported child archive.",
                ),
                document_id="doc_archive_child",
                file_name="unsupported.rar",
                content_type="application/vnd.rar",
                lineage=ArchiveDocumentLineage(
                    archive_depth=1,
                    archive_member_path="nested/unsupported.rar",
                    parent_document_id="doc_archive_parent",
                ),
                blob_container_name="raw-documents",
                blob_name="unsupported.rar",
                blob_uri="https://storage.example/unsupported.rar",
                content_length_bytes=64,
                file_hash_sha256="d" * 64,
                initial_processing_job_status=ProcessingJobStatus.SUCCEEDED,
                initial_processing_stage=ProcessingStageName.QUARANTINE,
                status=PacketStatus.QUARANTINED,
            ),
        ),
    )

    assert connection.committed is True
    assert connection.rolled_back is False
    assert response.status == PacketStatus.QUARANTINED
    assert response.next_stage == ProcessingStageName.QUARANTINE
    assert response.documents[1].lineage.parent_document_id == "doc_archive_parent"
    assert response.documents[1].lineage.archive_member_path == "nested/unsupported.rar"
    assert response.documents[1].lineage.source_asset_id is not None
    assert response.documents[1].review_task_id is not None

    review_task_statement = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.ReviewTasks" in statement[0]
    )
    assert review_task_statement[1] is not None
    assert review_task_statement[1][3] == "awaiting_review"
    assert review_task_statement[1][4] == "high"
    assert review_task_statement[1][5] == '["archive_unsupported"]'

    child_document_statement = next(
        statement
        for statement in connection.executed_statements
        if (
            "INSERT INTO dbo.PacketDocuments" in statement[0]
            and statement[1] is not None
            and statement[1][0] == "doc_archive_child"
        )
    )
    assert child_document_statement[1] is not None
    assert child_document_statement[1][15] == "doc_archive_parent"
    assert str(child_document_statement[1][16]).startswith("asset_")


def test_create_manual_packet_intake_flags_unsupported_archive_members_for_review(
    monkeypatch: MonkeyPatch,
) -> None:
    """Unsupported extracted members should create archive-member review reasons."""

    connection = FakeConnection()

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(persistence, "open_sql_connection", fake_open_sql_connection)

    repository = persistence.SqlOperatorWorkspaceRepository(build_settings())
    response = repository.create_manual_packet_intake(
        duplicate_detection=DuplicateDetectionResult(),
        packet_id="pkt_archive_member_001",
        packet_fingerprint="9" * 64,
        request=build_request(),
        source_fingerprint="8" * 64,
        staged_documents=(
            ManualPacketStagedDocument(
                asset_role="original_upload",
                archive_preflight=ArchivePreflightResult(
                    archive_format="zip",
                    disposition=ArchivePreflightDisposition.READY_FOR_EXPANSION,
                    entry_count=1,
                    is_archive=True,
                ),
                document_id="doc_archive_parent",
                file_name="archive.zip",
                content_type="application/zip",
                blob_container_name="raw-documents",
                blob_name="archive.zip",
                blob_uri="https://storage.example/archive.zip",
                content_length_bytes=128,
                file_hash_sha256="7" * 64,
                initial_processing_job_status=ProcessingJobStatus.SUCCEEDED,
                initial_processing_stage=ProcessingStageName.ARCHIVE_EXPANSION,
                status=PacketStatus.COMPLETED,
            ),
            ManualPacketStagedDocument(
                asset_role="archive_extracted_member",
                archive_preflight=ArchivePreflightResult(
                    disposition=ArchivePreflightDisposition.NOT_ARCHIVE,
                    is_archive=False,
                    message=(
                        "The extracted archive member type is not supported by the "
                        "current intake path and was routed to quarantine."
                    ),
                ),
                document_id="doc_archive_member",
                file_name="payload.exe",
                content_type="application/octet-stream",
                lineage=ArchiveDocumentLineage(
                    archive_depth=1,
                    archive_member_path="attachments/payload.exe",
                    parent_document_id="doc_archive_parent",
                ),
                blob_container_name="raw-documents",
                blob_name="payload.exe",
                blob_uri="https://storage.example/payload.exe",
                content_length_bytes=64,
                file_hash_sha256="6" * 64,
                initial_processing_job_status=ProcessingJobStatus.SUCCEEDED,
                initial_processing_stage=ProcessingStageName.QUARANTINE,
                status=PacketStatus.QUARANTINED,
            ),
        ),
    )

    assert connection.committed is True
    assert response.status == PacketStatus.QUARANTINED
    assert response.documents[1].lineage.parent_document_id == "doc_archive_parent"
    assert response.documents[1].review_task_id is not None

    review_task_statement = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.ReviewTasks" in statement[0]
    )
    assert review_task_statement[1] is not None
    assert review_task_statement[1][5] == '["archive_member_unsupported"]'
    assert review_task_statement[1][6] == (
        "The extracted archive member type is not supported by the current "
        "intake path and was routed to quarantine."
    )


def test_create_manual_packet_intake_seeds_classification_for_archive_children(
    monkeypatch: MonkeyPatch,
) -> None:
    """Classification-stage archive children should persist seed metadata."""

    connection = FakeConnection()

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(persistence, "open_sql_connection", fake_open_sql_connection)

    repository = persistence.SqlOperatorWorkspaceRepository(build_settings())
    response = repository.create_manual_packet_intake(
        duplicate_detection=DuplicateDetectionResult(),
        packet_id="pkt_archive_classification_001",
        packet_fingerprint="e" * 64,
        request=build_request(),
        source_fingerprint="f" * 64,
        staged_documents=(
            ManualPacketStagedDocument(
                asset_role="original_upload",
                archive_preflight=ArchivePreflightResult(
                    archive_format="zip",
                    disposition=ArchivePreflightDisposition.READY_FOR_EXPANSION,
                    entry_count=1,
                    is_archive=True,
                ),
                document_id="doc_archive_parent",
                file_name="archive.zip",
                content_type="application/zip",
                blob_container_name="raw-documents",
                blob_name="archive.zip",
                blob_uri="https://storage.example/archive.zip",
                content_length_bytes=128,
                file_hash_sha256="1" * 64,
                initial_processing_job_status=ProcessingJobStatus.SUCCEEDED,
                initial_processing_stage=ProcessingStageName.ARCHIVE_EXPANSION,
                status=PacketStatus.COMPLETED,
            ),
            ManualPacketStagedDocument(
                asset_role="archive_extracted_member",
                archive_preflight=ArchivePreflightResult(),
                document_id="doc_archive_child",
                file_name="supporting-document.pdf",
                content_type="application/pdf",
                lineage=ArchiveDocumentLineage(
                    archive_depth=1,
                    archive_member_path="supporting-document.pdf",
                    parent_document_id="doc_archive_parent",
                ),
                blob_container_name="raw-documents",
                blob_name="supporting-document.pdf",
                blob_uri="https://storage.example/supporting-document.pdf",
                content_length_bytes=64,
                file_hash_sha256="2" * 64,
                initial_processing_job_status=ProcessingJobStatus.QUEUED,
                initial_processing_stage=ProcessingStageName.CLASSIFICATION,
                source_summary="Archive child seed",
                source_tags=("bank", "statement"),
                status=PacketStatus.CLASSIFYING,
            ),
        ),
    )

    assert connection.committed is True
    assert response.status == PacketStatus.CLASSIFYING
    assert response.next_stage == ProcessingStageName.CLASSIFICATION

    classification_statement = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.ClassificationResults" in statement[0]
    )
    assert classification_statement[1] is not None
    assert classification_statement[1][1] == "pkt_archive_classification_001"
    assert classification_statement[1][2] == "doc_archive_child"
    assert classification_statement[1][5] == "rule"

    classification_event_statement = next(
        statement
        for statement in connection.executed_statements
        if (
            "INSERT INTO dbo.PacketEvents" in statement[0]
            and statement[1] is not None
            and statement[1][2] == "document.classification.seeded"
        )
    )
    assert classification_event_statement[1] is not None
    assert "seeded_from_manual_intake" in str(classification_event_statement[1][3])


def test_create_manual_packet_intake_persists_blocking_safety_issues(
    monkeypatch: MonkeyPatch,
) -> None:
    """Safety-triggered quarantine should persist reason codes and payload metadata."""

    connection = FakeConnection()

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(persistence, "open_sql_connection", fake_open_sql_connection)

    repository = persistence.SqlOperatorWorkspaceRepository(build_settings())
    response = repository.create_manual_packet_intake(
        duplicate_detection=DuplicateDetectionResult(),
        packet_id="pkt_safety_001",
        packet_fingerprint="1" * 64,
        request=build_request(),
        source_fingerprint="2" * 64,
        staged_documents=(
            ManualPacketStagedDocument(
                asset_role="original_upload",
                archive_preflight=ArchivePreflightResult(),
                safety_issues=(
                    SafetyIssue(
                        code="malformed_office_file",
                        message="The uploaded Office file could not be opened.",
                        severity=SafetyIssueSeverity.BLOCKING,
                        stage_name=ProcessingStageName.QUARANTINE,
                    ),
                ),
                document_id="doc_safety_001",
                file_name="broken.docx",
                content_type=(
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
                blob_container_name="raw-documents",
                blob_name="broken.docx",
                blob_uri="https://storage.example/broken.docx",
                content_length_bytes=128,
                file_hash_sha256="3" * 64,
                initial_processing_job_status=ProcessingJobStatus.SUCCEEDED,
                initial_processing_stage=ProcessingStageName.QUARANTINE,
                status=PacketStatus.QUARANTINED,
            ),
        ),
    )

    assert response.status == PacketStatus.QUARANTINED
    review_task_statement = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.ReviewTasks" in statement[0]
    )
    assert review_task_statement[1] is not None
    assert review_task_statement[1][5] == '["malformed_office_file"]'
    assert review_task_statement[1][6] == (
        "The uploaded Office file could not be opened."
    )

    manual_event_statement = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.PacketEvents" in statement[0]
        and statement[1] is not None
        and statement[1][2] == "document.manual_intake.quarantined"
    )
    assert manual_event_statement[1] is not None
    manual_event_payload = json.loads(str(manual_event_statement[1][3]))
    assert manual_event_payload["safetyIssues"][0]["code"] == "malformed_office_file"

    audit_event_statement = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.AuditEvents" in statement[0]
        and statement[1] is not None
        and len(statement[1]) > 4
        and statement[1][4] == "review.task.created"
    )
    assert audit_event_statement[1] is not None
    audit_event_payload = json.loads(str(audit_event_statement[1][5]))
    assert audit_event_payload["safetyIssues"][0]["code"] == "malformed_office_file"