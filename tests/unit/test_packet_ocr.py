"""Unit tests for packet OCR execution and extraction handoff."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from types import TracebackType

from pytest import MonkeyPatch

import document_intelligence.packet_ocr as packet_ocr
from document_intelligence.models import (
    ArchivePreflightResult,
    ClassificationResultRecord,
    ClassificationResultSource,
    DocumentAssetRecord,
    DocumentSource,
    IssuerCategory,
    ManagedDocumentTypeDefinitionRecord,
    PacketDocumentRecord,
    PacketRecord,
    PacketStatus,
    PacketWorkspaceSnapshot,
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStageName,
    PromptProfileId,
)
from document_intelligence.settings import AppSettings
from document_intelligence.utils.blob_storage import BlobAsset


def build_settings(**overrides: object) -> AppSettings:
    """Build settings for packet OCR tests."""

    values: dict[str, object] = {
        "processed_container_name": "processed-documents",
        "sql_connection_string": (
            "Server=tcp:test-sql.database.windows.net,1433;"
            "Database=docintel;User ID=docintel;Password=Password123!"
        ),
        "storage_connection_string": "UseDevelopmentStorage=true",
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


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
    """A DB-API connection stub that records OCR SQL statements."""

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


def build_snapshot(
    *,
    classification_results: tuple[ClassificationResultRecord, ...] = (),
    document_status: PacketStatus,
    packet_status: PacketStatus,
) -> PacketWorkspaceSnapshot:
    """Build a packet workspace snapshot with one queued OCR document."""

    packet = PacketRecord(
        created_at_utc=datetime(2026, 4, 6, 17, 0, tzinfo=UTC),
        packet_id="pkt_archive_001",
        packet_name="ocr packet",
        packet_tags=(),
        received_at_utc=datetime(2026, 4, 6, 17, 0, tzinfo=UTC),
        source=DocumentSource.SCANNED_UPLOAD,
        source_uri="manual://packets/pkt_archive_001",
        status=packet_status,
        submitted_by="operator@example.com",
        updated_at_utc=datetime(2026, 4, 6, 17, 0, tzinfo=UTC),
    )
    document = PacketDocumentRecord(
        account_candidates=("acct_123",),
        archive_preflight=ArchivePreflightResult(),
        content_type="application/pdf",
        created_at_utc=datetime(2026, 4, 6, 17, 1, tzinfo=UTC),
        document_id="doc_child_001",
        document_text="Statement page one",
        file_name="statement.pdf",
        issuer_category=IssuerCategory.BANK,
        issuer_name="Fabrikam Bank",
        packet_id=packet.packet_id,
        received_at_utc=datetime(2026, 4, 6, 17, 1, tzinfo=UTC),
        source=DocumentSource.SCANNED_UPLOAD,
        source_summary="Monthly statement",
        source_tags=("bank", "statement"),
        source_uri=packet.source_uri,
        status=document_status,
        updated_at_utc=datetime(2026, 4, 6, 17, 1, tzinfo=UTC),
    )
    asset = DocumentAssetRecord(
        asset_id="asset_child_001",
        asset_role="archive_extracted_member",
        blob_name="statement.pdf",
        container_name="raw-documents",
        content_length_bytes=64,
        content_type="application/pdf",
        created_at_utc=datetime(2026, 4, 6, 17, 1, tzinfo=UTC),
        document_id=document.document_id,
        packet_id=packet.packet_id,
        storage_uri="https://storage.example/raw/statement.pdf",
    )
    ocr_job = ProcessingJobRecord(
        attempt_number=1,
        created_at_utc=datetime(2026, 4, 6, 17, 1, tzinfo=UTC),
        document_id=document.document_id,
        job_id="job_ocr_001",
        packet_id=packet.packet_id,
        queued_at_utc=datetime(2026, 4, 6, 17, 1, tzinfo=UTC),
        stage_name=ProcessingStageName.OCR,
        status=ProcessingJobStatus.QUEUED,
        updated_at_utc=datetime(2026, 4, 6, 17, 1, tzinfo=UTC),
    )
    return PacketWorkspaceSnapshot(
        packet=packet,
        documents=(document,),
        document_assets=(asset,),
        packet_events=(),
        processing_jobs=(ocr_job,),
        ocr_results=(),
        extraction_results=(),
        classification_results=classification_results,
        account_match_runs=(),
        review_tasks=(),
        review_decisions=(),
        operator_notes=(),
        audit_events=(),
        recommendation_runs=(),
        recommendation_results=(),
    )


def build_document_type_definitions(
) -> tuple[ManagedDocumentTypeDefinitionRecord, ...]:
    """Build one managed document-type contract for OCR strategy resolution."""

    return (
        ManagedDocumentTypeDefinitionRecord(
            classification_id="cls_bank_correspondence",
            created_at_utc=datetime(2026, 4, 6, 16, 0, tzinfo=UTC),
            default_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
            display_name="Bank Statement",
            document_type_id="doc_bank_statement",
            document_type_key="bank_statement",
            required_fields=("account_number", "statement_date"),
            updated_at_utc=datetime(2026, 4, 6, 16, 0, tzinfo=UTC),
        ),
    )


def test_execute_packet_ocr_stage_persists_ocr_and_queues_extraction(
    monkeypatch: MonkeyPatch,
) -> None:
    """OCR execution should persist OCR results and queue extraction work."""

    connection = FakeConnection()
    classification_result = ClassificationResultRecord(
        classification_id="cls_bank_correspondence",
        classification_result_id="clsr_001",
        confidence=0.91,
        created_at_utc=datetime(2026, 4, 6, 17, 0, tzinfo=UTC),
        document_id="doc_child_001",
        document_type_id="doc_bank_statement",
        packet_id="pkt_archive_001",
        prompt_profile_id=PromptProfileId.BANK_STATEMENT,
        result_payload={},
        result_source=ClassificationResultSource.RULE,
    )
    snapshot = build_snapshot(
        classification_results=(classification_result,),
        document_status=PacketStatus.OCR_RUNNING,
        packet_status=PacketStatus.OCR_RUNNING,
    )
    document_type_definitions = build_document_type_definitions()

    class FakeRepository:
        """Repository stub that returns one packet snapshot and doctype contracts."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self, packet_id: str
        ) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

        def list_document_type_definitions(
            self,
        ) -> tuple[ManagedDocumentTypeDefinitionRecord, ...]:
            return document_type_definitions

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(packet_ocr, "SqlOperatorStateRepository", FakeRepository)
    monkeypatch.setattr(
        packet_ocr,
        "extract_ocr_text",
        lambda request, settings: (
            "Statement for account 1234",
            0.93,
            2,
            ("used test OCR",),
            "azure_document_intelligence",
        ),
    )
    monkeypatch.setattr(
        packet_ocr,
        "upload_blob_bytes",
        lambda **kwargs: BlobAsset(
            blob_name=str(kwargs["blob_name"]),
            container_name=str(kwargs["container_name"]),
            content_length_bytes=len(kwargs["data"]),
            storage_uri=f"https://storage.example/{kwargs['blob_name']}",
        ),
    )
    monkeypatch.setattr(packet_ocr, "open_sql_connection", fake_open_sql_connection)

    response = packet_ocr.execute_packet_ocr_stage("pkt_archive_001", build_settings())

    assert response.executed_document_count == 1
    assert response.status == PacketStatus.EXTRACTING
    assert response.next_stage == ProcessingStageName.EXTRACTION
    assert response.processed_documents[0].ocr_job_id == "job_ocr_001"
    assert response.processed_documents[0].provider == "azure_document_intelligence"
    assert response.processed_documents[0].extraction_strategy.strategy_source == (
        "classification_contract"
    )
    assert response.processed_documents[0].extraction_strategy.document_type_id == (
        "doc_bank_statement"
    )
    assert response.processed_documents[0].extraction_strategy.required_fields == (
        "account_number",
        "statement_date",
    )
    assert response.processed_documents[0].text_storage_uri is not None
    assert connection.committed is True
    assert connection.rolled_back is False
    assert any(
        "INSERT INTO dbo.OcrResults" in statement[0]
        and statement[1] is not None
        and statement[1][3] == "azure_document_intelligence"
        for statement in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.ProcessingJobs" in statement[0]
        and statement[1] is not None
        and statement[1][3] == "extraction"
        for statement in connection.executed_statements
    )
    assert any(
        "UPDATE dbo.Packets" in statement[0]
        and statement[1] is not None
        and statement[1][0] == "extracting"
        for statement in connection.executed_statements
    )


def test_execute_packet_ocr_stage_falls_back_to_request_routing(
    monkeypatch: MonkeyPatch,
) -> None:
    """Direct OCR packets should still queue extraction from request heuristics."""

    connection = FakeConnection()
    snapshot = build_snapshot(
        document_status=PacketStatus.RECEIVED,
        packet_status=PacketStatus.RECEIVED,
    )

    class FakeRepository:
        """Repository stub that returns one direct-OCR packet snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self, packet_id: str
        ) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

        def list_document_type_definitions(
            self,
        ) -> tuple[ManagedDocumentTypeDefinitionRecord, ...]:
            return ()

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(packet_ocr, "SqlOperatorStateRepository", FakeRepository)
    monkeypatch.setattr(
        packet_ocr,
        "extract_ocr_text",
        lambda request, settings: (
            request.document_text or "",
            1.0,
            0,
            ("used request document text",),
            "request_document_text",
        ),
    )
    monkeypatch.setattr(
        packet_ocr,
        "upload_blob_bytes",
        lambda **kwargs: BlobAsset(
            blob_name=str(kwargs["blob_name"]),
            container_name=str(kwargs["container_name"]),
            content_length_bytes=len(kwargs["data"]),
            storage_uri=f"https://storage.example/{kwargs['blob_name']}",
        ),
    )
    monkeypatch.setattr(packet_ocr, "open_sql_connection", fake_open_sql_connection)

    response = packet_ocr.execute_packet_ocr_stage("pkt_archive_001", build_settings())

    assert response.executed_document_count == 1
    assert response.status == PacketStatus.EXTRACTING
    assert response.processed_documents[0].provider == "request_document_text"
    assert response.processed_documents[0].extraction_strategy.strategy_source == (
        "request_heuristics"
    )
    assert response.processed_documents[0].extraction_strategy.document_type_id is None
    assert response.processed_documents[0].extraction_strategy.prompt_profile_id == (
        PromptProfileId.BANK_STATEMENT
    )
    assert response.processed_documents[0].extraction_strategy.required_fields == (
        "account_number",
        "statement_date",
    )


def test_execute_packet_ocr_stage_routes_quality_warnings_to_review(
    monkeypatch: MonkeyPatch,
) -> None:
    """OCR page-quality warnings should pause extraction for operator review."""

    connection = FakeConnection()
    classification_result = ClassificationResultRecord(
        classification_id="cls_bank_correspondence",
        classification_result_id="clsr_001",
        confidence=0.91,
        created_at_utc=datetime(2026, 4, 6, 17, 0, tzinfo=UTC),
        document_id="doc_child_001",
        document_type_id="doc_bank_statement",
        packet_id="pkt_archive_001",
        prompt_profile_id=PromptProfileId.BANK_STATEMENT,
        result_payload={},
        result_source=ClassificationResultSource.RULE,
    )
    snapshot = build_snapshot(
        classification_results=(classification_result,),
        document_status=PacketStatus.OCR_RUNNING,
        packet_status=PacketStatus.OCR_RUNNING,
    )
    document_type_definitions = build_document_type_definitions()

    class FakeRepository:
        """Repository stub that returns one packet snapshot and contracts."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self, packet_id: str
        ) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

        def list_document_type_definitions(
            self,
        ) -> tuple[ManagedDocumentTypeDefinitionRecord, ...]:
            return document_type_definitions

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(packet_ocr, "SqlOperatorStateRepository", FakeRepository)
    monkeypatch.setattr(
        packet_ocr,
        "extract_ocr_text",
        lambda request, settings: (
            "Statement for account 1234",
            0.93,
            1,
            (
                "ocr_quality_warning: Page 1 rotation angle 12.0 degrees exceeded the warning threshold of 5.0.",
                "ocr_quality_warning: Page 1 shorter pixel edge 800 was below the minimum threshold of 1000.",
            ),
            "azure_document_intelligence",
        ),
    )
    monkeypatch.setattr(
        packet_ocr,
        "upload_blob_bytes",
        lambda **kwargs: BlobAsset(
            blob_name=str(kwargs["blob_name"]),
            container_name=str(kwargs["container_name"]),
            content_length_bytes=len(kwargs["data"]),
            storage_uri=f"https://storage.example/{kwargs['blob_name']}",
        ),
    )
    monkeypatch.setattr(packet_ocr, "open_sql_connection", fake_open_sql_connection)

    response = packet_ocr.execute_packet_ocr_stage("pkt_archive_001", build_settings())

    assert response.executed_document_count == 1
    assert response.status == PacketStatus.AWAITING_REVIEW
    assert response.next_stage == ProcessingStageName.REVIEW
    assert response.processed_documents[0].status == PacketStatus.AWAITING_REVIEW
    assert response.processed_documents[0].review_task_id is not None
    assert response.processed_documents[0].extraction_job_id is None
    assert connection.committed is True
    assert connection.rolled_back is False
    assert any(
        "INSERT INTO dbo.ReviewTasks" in statement[0]
        and statement[1] is not None
        and statement[1][5] == '["ocr_quality_warning"]'
        for statement in connection.executed_statements
    )
    assert not any(
        "INSERT INTO dbo.ProcessingJobs" in statement[0]
        and statement[1] is not None
        and statement[1][3] == "extraction"
        for statement in connection.executed_statements
    )
    assert any(
        "UPDATE dbo.Packets" in statement[0]
        and statement[1] is not None
        and statement[1][0] == "awaiting_review"
        for statement in connection.executed_statements
    )

    review_required_event = next(
        params
        for statement, params in connection.executed_statements
        if "INSERT INTO dbo.PacketEvents" in statement
        and params is not None
        and params[2] == "document.ocr.review_required"
    )
    review_required_payload = json.loads(str(review_required_event[3]))
    assert review_required_payload["reasonCodes"] == ["ocr_quality_warning"]
    assert review_required_payload["reviewTaskId"] == (
        response.processed_documents[0].review_task_id
    )
    assert review_required_payload["status"] == "awaiting_review"
    assert any(
        issue["code"] == "ocr_quality_warning"
        for issue in review_required_payload["safetyIssues"]
    )
    assert any(
        "rotation angle" in warning
        for warning in review_required_payload["warnings"]
    )