"""Unit tests for packet recommendation execution and completion."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import TracebackType

from pytest import MonkeyPatch

import document_intelligence.packet_recommendation as packet_recommendation
from document_intelligence.models import (
    AccountMatchCandidate,
    AccountMatchRunRecord,
    AccountMatchStatus,
    ArchivePreflightResult,
    ClassificationResultRecord,
    ClassificationResultSource,
    DocumentAssetRecord,
    DocumentSource,
    ExtractionResultRecord,
    OcrResultRecord,
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


def build_settings(**overrides: object) -> AppSettings:
    """Build settings for packet recommendation tests."""

    values: dict[str, object] = {
        "sql_connection_string": (
            "Server=tcp:test-sql.database.windows.net,1433;"
            "Database=docintel;User ID=docintel;Password=Password123!"
        ),
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


class FakeCursor:
    """A DB-API cursor stub that records recommendation SQL statements."""

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
    """A DB-API connection stub that records recommendation SQL statements."""

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


def build_snapshot() -> PacketWorkspaceSnapshot:
    """Build a packet workspace snapshot with one queued recommendation job."""

    packet = PacketRecord(
        created_at_utc=datetime(2026, 4, 7, 1, 0, tzinfo=UTC),
        packet_id="pkt_archive_001",
        packet_name="recommendation packet",
        packet_tags=(),
        received_at_utc=datetime(2026, 4, 7, 1, 0, tzinfo=UTC),
        source=DocumentSource.SCANNED_UPLOAD,
        source_fingerprint=(
            "b7f1b2362b827cf6aecaba2c4f35ed20fb69eb9577bd48382e9154a1e024982f"
        ),
        source_uri="manual://packets/pkt_archive_001",
        status=PacketStatus.READY_FOR_RECOMMENDATION,
        submitted_by="operator@example.com",
        updated_at_utc=datetime(2026, 4, 7, 1, 0, tzinfo=UTC),
    )
    document = PacketDocumentRecord(
        account_candidates=("acct_123",),
        archive_preflight=ArchivePreflightResult(),
        content_type="application/pdf",
        created_at_utc=datetime(2026, 4, 7, 1, 1, tzinfo=UTC),
        document_id="doc_child_001",
        document_text="Statement for account 1234 dated 2026-03-31",
        file_hash_sha256=(
            "1ab1c490a7f757b76daba32673c30d2a2c6493f7c54dfdeb22725b08da45d141"
        ),
        file_name="statement.pdf",
        packet_id=packet.packet_id,
        received_at_utc=datetime(2026, 4, 7, 1, 1, tzinfo=UTC),
        requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
        source=DocumentSource.SCANNED_UPLOAD,
        source_summary="Monthly statement",
        source_tags=("bank", "statement"),
        source_uri=packet.source_uri,
        status=PacketStatus.READY_FOR_RECOMMENDATION,
        updated_at_utc=datetime(2026, 4, 7, 1, 1, tzinfo=UTC),
    )
    asset = DocumentAssetRecord(
        asset_id="asset_child_001",
        asset_role="archive_extracted_member",
        blob_name="statement.pdf",
        container_name="raw-documents",
        content_length_bytes=64,
        content_type="application/pdf",
        created_at_utc=datetime(2026, 4, 7, 1, 1, tzinfo=UTC),
        document_id=document.document_id,
        packet_id=packet.packet_id,
        storage_uri="https://storage.example/raw/statement.pdf",
    )
    recommendation_job = ProcessingJobRecord(
        attempt_number=1,
        created_at_utc=datetime(2026, 4, 7, 1, 2, tzinfo=UTC),
        document_id=document.document_id,
        job_id="job_rec_001",
        packet_id=packet.packet_id,
        queued_at_utc=datetime(2026, 4, 7, 1, 2, tzinfo=UTC),
        stage_name=ProcessingStageName.RECOMMENDATION,
        status=ProcessingJobStatus.QUEUED,
        updated_at_utc=datetime(2026, 4, 7, 1, 2, tzinfo=UTC),
    )
    classification_result = ClassificationResultRecord(
        classification_id="cls_bank_correspondence",
        classification_result_id="clsr_001",
        confidence=0.89,
        created_at_utc=datetime(2026, 4, 7, 1, 2, tzinfo=UTC),
        document_id=document.document_id,
        document_type_id="doc_bank_statement",
        packet_id=packet.packet_id,
        prompt_profile_id=PromptProfileId.BANK_STATEMENT,
        result_payload={
            "classificationExecution": {
                "classificationKey": "bank_correspondence",
                "documentTypeKey": "bank_statement",
            }
        },
        result_source=ClassificationResultSource.AI,
    )
    extraction_result = ExtractionResultRecord(
        created_at_utc=datetime(2026, 4, 7, 1, 2, tzinfo=UTC),
        document_id=document.document_id,
        document_type="bank_statement",
        extraction_result_id="ext_001",
        model_name="prebuilt-layout+gpt4o-deployment",
        packet_id=packet.packet_id,
        prompt_profile_id=PromptProfileId.BANK_STATEMENT,
        provider="azure_document_intelligence+azure_openai",
        result_payload={
            "extractedFields": [
                {
                    "confidence": 0.96,
                    "name": "account_number",
                    "value": "1234",
                },
                {
                    "confidence": 0.94,
                    "name": "statement_date",
                    "value": "2026-03-31",
                },
            ]
        },
        summary="Bank statement extracted cleanly.",
    )
    ocr_result = OcrResultRecord(
        created_at_utc=datetime(2026, 4, 7, 1, 2, tzinfo=UTC),
        document_id=document.document_id,
        model_name="prebuilt-layout",
        ocr_confidence=0.93,
        ocr_result_id="ocr_001",
        packet_id=packet.packet_id,
        page_count=1,
        provider="azure_document_intelligence",
        text_excerpt="Statement for account 1234 dated 2026-03-31",
        text_storage_uri="https://storage.example/ocr/ocr_001.txt",
    )
    account_match_run = AccountMatchRunRecord(
        candidates=(
            AccountMatchCandidate(
                account_id="acct_123",
                account_number="1234",
                debtor_name="Pat Doe",
                issuer_name="Fabrikam Bank",
                matched_on=("account_number_exact",),
                score=92.0,
            ),
        ),
        created_at_utc=datetime(2026, 4, 7, 1, 2, tzinfo=UTC),
        document_id=document.document_id,
        match_run_id="match_001",
        packet_id=packet.packet_id,
        rationale="Matched to the highest-ranked Azure SQL account candidate.",
        selected_account_id="acct_123",
        status=AccountMatchStatus.MATCHED,
    )
    return PacketWorkspaceSnapshot(
        packet=packet,
        documents=(document,),
        document_assets=(asset,),
        packet_events=(),
        processing_jobs=(recommendation_job,),
        ocr_results=(ocr_result,),
        extraction_results=(extraction_result,),
        classification_results=(classification_result,),
        account_match_runs=(account_match_run,),
        review_tasks=(),
        review_decisions=(),
        operator_notes=(),
        audit_events=(),
        recommendation_runs=(),
        recommendation_results=(),
    )


def test_execute_packet_recommendation_stage_persists_results(
    monkeypatch: MonkeyPatch,
) -> None:
    """Recommendation execution should persist recommendation outputs."""

    connection = FakeConnection()
    snapshot = build_snapshot()

    class FakeRepository:
        """Repository stub that returns one packet snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self, packet_id: str
        ) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_recommendation,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_recommendation,
        "open_sql_connection",
        fake_open_sql_connection,
    )

    response = packet_recommendation.execute_packet_recommendation_stage(
        "pkt_archive_001",
        build_settings(),
    )

    assert response.executed_document_count == 1
    assert response.status == PacketStatus.COMPLETED
    assert response.processed_documents[0].recommendation_job_id == "job_rec_001"
    assert response.processed_documents[0].recommendation_result_id.startswith(
        "recres_"
    )
    assert response.processed_documents[0].classification_prior_id is not None
    assert connection.committed is True
    assert connection.rolled_back is False
    assert any(
        "INSERT INTO dbo.RecommendationRuns" in statement[0]
        for statement in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.RecommendationResults" in statement[0]
        for statement in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.ClassificationPriors" in statement[0]
        for statement in connection.executed_statements
    )
    assert any(
        "UPDATE dbo.Packets" in statement[0]
        and statement[1] is not None
        and statement[1][0] == "completed"
        for statement in connection.executed_statements
    )


def test_execute_packet_recommendation_stage_routes_conflicting_evidence_to_review(
    monkeypatch: MonkeyPatch,
) -> None:
    """Conflicting packet evidence should create review work instead of completing."""

    connection = FakeConnection()
    snapshot = build_snapshot()
    conflicting_document = PacketDocumentRecord(
        account_candidates=("acct_999",),
        archive_preflight=ArchivePreflightResult(),
        content_type="application/pdf",
        created_at_utc=datetime(2026, 4, 7, 1, 3, tzinfo=UTC),
        document_id="doc_child_002",
        document_text="Statement for account 9999 dated 2026-03-31",
        file_name="other-statement.pdf",
        packet_id=snapshot.packet.packet_id,
        received_at_utc=datetime(2026, 4, 7, 1, 3, tzinfo=UTC),
        source=DocumentSource.SCANNED_UPLOAD,
        source_uri=snapshot.packet.source_uri,
        status=PacketStatus.COMPLETED,
        updated_at_utc=datetime(2026, 4, 7, 1, 3, tzinfo=UTC),
    )
    conflicting_extraction = ExtractionResultRecord(
        created_at_utc=datetime(2026, 4, 7, 1, 3, tzinfo=UTC),
        document_id="doc_child_002",
        document_type="bank_statement",
        extraction_result_id="ext_002",
        model_name="prebuilt-layout+gpt4o-deployment",
        packet_id=snapshot.packet.packet_id,
        prompt_profile_id=PromptProfileId.BANK_STATEMENT,
        provider="azure_document_intelligence+azure_openai",
        result_payload={
            "extractedFields": [
                {
                    "confidence": 0.97,
                    "name": "account_number",
                    "value": "9999",
                }
            ]
        },
        summary="Conflicting bank statement.",
    )
    snapshot = snapshot.model_copy(
        update={
            "documents": (*snapshot.documents, conflicting_document),
            "extraction_results": (*snapshot.extraction_results, conflicting_extraction),
        }
    )

    class FakeRepository:
        """Repository stub that returns one conflicting packet snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self, packet_id: str
        ) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_recommendation,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_recommendation,
        "open_sql_connection",
        fake_open_sql_connection,
    )

    response = packet_recommendation.execute_packet_recommendation_stage(
        "pkt_archive_001",
        build_settings(),
    )

    assert response.executed_document_count == 1
    assert response.status == PacketStatus.AWAITING_REVIEW
    assert response.next_stage == ProcessingStageName.REVIEW
    assert response.processed_documents[0].review_task_id is not None
    assert response.processed_documents[0].status == PacketStatus.AWAITING_REVIEW
    assert any(
        "INSERT INTO dbo.ReviewTasks" in statement[0]
        and statement[1] is not None
        and statement[1][5] == "acct_123"
        and statement[1][6] == '["conflicting_packet_evidence"]'
        for statement in connection.executed_statements
    )
    review_event = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.PacketEvents" in statement[0]
        and statement[1] is not None
        and statement[1][2] == "document.review_task.created"
    )
    assert review_event[1] is not None
    review_payload = json.loads(str(review_event[1][3]))
    assert review_payload["reasonCodes"] == ["conflicting_packet_evidence"]


def test_execute_packet_recommendation_stage_routes_low_confidence_to_review(
    monkeypatch: MonkeyPatch,
) -> None:
    """Low-confidence recommendations should stay in manual review."""

    connection = FakeConnection()
    snapshot = build_snapshot()
    weak_classification = snapshot.classification_results[0].model_copy(
        update={"confidence": 0.2}
    )
    weak_extraction = snapshot.extraction_results[0].model_copy(
        update={
            "result_payload": {
                "extractedFields": [
                    {
                        "confidence": 0.2,
                        "name": "account_number",
                        "value": "1234",
                    },
                    {
                        "confidence": 0.2,
                        "name": "statement_date",
                        "value": "2026-03-31",
                    },
                ]
            }
        }
    )
    weak_ocr = snapshot.ocr_results[0].model_copy(update={"ocr_confidence": 0.2})
    snapshot = snapshot.model_copy(
        update={
            "classification_results": (weak_classification,),
            "extraction_results": (weak_extraction,),
            "ocr_results": (weak_ocr,),
        }
    )

    class FakeRepository:
        """Repository stub that returns one low-confidence packet snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self, packet_id: str
        ) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_recommendation,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_recommendation,
        "open_sql_connection",
        fake_open_sql_connection,
    )

    response = packet_recommendation.execute_packet_recommendation_stage(
        "pkt_archive_001",
        build_settings(recommendation_guardrail_confidence_threshold=0.75),
    )

    assert response.executed_document_count == 1
    assert response.status == PacketStatus.AWAITING_REVIEW
    assert response.next_stage == ProcessingStageName.REVIEW
    assert response.processed_documents[0].review_task_id is not None
    assert response.processed_documents[0].status == PacketStatus.AWAITING_REVIEW
    assert any(
        "INSERT INTO dbo.ReviewTasks" in statement[0]
        and statement[1] is not None
        and statement[1][6] == '["recommendation_guardrail"]'
        for statement in connection.executed_statements
    )


def test_execute_packet_recommendation_stage_routes_mixed_content_packets_to_review(
    monkeypatch: MonkeyPatch,
) -> None:
    """Mixed packet document types should pause recommendations for review."""

    connection = FakeConnection()
    snapshot = build_snapshot()
    mixed_document = PacketDocumentRecord(
        account_candidates=("acct_123",),
        archive_preflight=ArchivePreflightResult(),
        content_type="application/pdf",
        created_at_utc=datetime(2026, 4, 7, 1, 3, tzinfo=UTC),
        document_id="doc_child_002",
        document_text="Utility bill for 123 Main St due 2026-04-15",
        file_name="utility-bill.pdf",
        packet_id=snapshot.packet.packet_id,
        received_at_utc=datetime(2026, 4, 7, 1, 3, tzinfo=UTC),
        source=DocumentSource.SCANNED_UPLOAD,
        source_uri=snapshot.packet.source_uri,
        status=PacketStatus.COMPLETED,
        updated_at_utc=datetime(2026, 4, 7, 1, 3, tzinfo=UTC),
    )
    mixed_extraction = ExtractionResultRecord(
        created_at_utc=datetime(2026, 4, 7, 1, 3, tzinfo=UTC),
        document_id="doc_child_002",
        document_type="utility_bill",
        extraction_result_id="ext_002",
        model_name="prebuilt-layout+gpt4o-deployment",
        packet_id=snapshot.packet.packet_id,
        prompt_profile_id=PromptProfileId.UTILITY_BILL,
        provider="azure_document_intelligence+azure_openai",
        result_payload={
            "extractedFields": [
                {
                    "confidence": 0.96,
                    "name": "service_address",
                    "value": "123 Main St",
                }
            ]
        },
        summary="Utility bill included with the packet.",
    )
    snapshot = snapshot.model_copy(
        update={
            "documents": (*snapshot.documents, mixed_document),
            "extraction_results": (*snapshot.extraction_results, mixed_extraction),
        }
    )

    class FakeRepository:
        """Repository stub that returns one mixed-content packet snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self, packet_id: str
        ) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_recommendation,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_recommendation,
        "open_sql_connection",
        fake_open_sql_connection,
    )

    response = packet_recommendation.execute_packet_recommendation_stage(
        "pkt_archive_001",
        build_settings(),
    )

    assert response.executed_document_count == 1
    assert response.status == PacketStatus.AWAITING_REVIEW
    assert response.next_stage == ProcessingStageName.REVIEW
    assert response.processed_documents[0].review_task_id is not None
    assert response.processed_documents[0].status == PacketStatus.AWAITING_REVIEW
    assert any(
        "INSERT INTO dbo.ReviewTasks" in statement[0]
        and statement[1] is not None
        and statement[1][6] == '["mixed_content_packet"]'
        for statement in connection.executed_statements
    )
    review_event = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.PacketEvents" in statement[0]
        and statement[1] is not None
        and statement[1][2] == "document.review_task.created"
    )
    assert review_event[1] is not None
    review_payload = json.loads(str(review_event[1][3]))
    assert review_payload["reasonCodes"] == ["mixed_content_packet"]


def test_execute_packet_recommendation_stage_routes_unsupported_fields_to_review(
    monkeypatch: MonkeyPatch,
) -> None:
    """Unsupported extracted fields should pause recommendations for review."""

    connection = FakeConnection()
    snapshot = build_snapshot()
    classification_result = snapshot.classification_results[0].model_copy(
        update={
            "result_payload": {
                "classificationExecution": {
                    "classificationKey": "bank_correspondence",
                    "documentTypeKey": "bank_statement",
                },
                "requiredFields": ["account_number", "statement_date"],
            }
        }
    )
    unsupported_extraction = snapshot.extraction_results[0].model_copy(
        update={
            "result_payload": {
                "extractedFields": [
                    {
                        "confidence": 0.96,
                        "name": "account_number",
                        "value": "1234",
                    },
                    {
                        "confidence": 0.94,
                        "name": "statement_date",
                        "value": "2026-03-31",
                    },
                    {
                        "confidence": 0.98,
                        "name": "mystery_balance_code",
                        "value": "ZX-42",
                    },
                ]
            }
        }
    )
    snapshot = snapshot.model_copy(
        update={
            "classification_results": (classification_result,),
            "extraction_results": (unsupported_extraction,),
        }
    )

    class FakeRepository:
        """Repository stub that returns one packet snapshot with odd fields."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self, packet_id: str
        ) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_recommendation,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_recommendation,
        "open_sql_connection",
        fake_open_sql_connection,
    )

    response = packet_recommendation.execute_packet_recommendation_stage(
        "pkt_archive_001",
        build_settings(),
    )

    assert response.executed_document_count == 1
    assert response.status == PacketStatus.AWAITING_REVIEW
    assert response.next_stage == ProcessingStageName.REVIEW
    assert response.processed_documents[0].review_task_id is not None
    assert response.processed_documents[0].status == PacketStatus.AWAITING_REVIEW
    assert any(
        "INSERT INTO dbo.ReviewTasks" in statement[0]
        and statement[1] is not None
        and statement[1][6] == '["hallucinated_recommendation_field"]'
        for statement in connection.executed_statements
    )
    review_event = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.PacketEvents" in statement[0]
        and statement[1] is not None
        and statement[1][2] == "document.review_task.created"
    )
    assert review_event[1] is not None
    review_payload = json.loads(str(review_event[1][3]))
    assert review_payload["reasonCodes"] == ["hallucinated_recommendation_field"]
    review_task_index = next(
        index
        for index, statement in enumerate(connection.executed_statements)
        if "INSERT INTO dbo.ReviewTasks" in statement[0]
    )
    recommendation_run_index = next(
        index
        for index, statement in enumerate(connection.executed_statements)
        if "INSERT INTO dbo.RecommendationRuns" in statement[0]
    )
    assert review_task_index < recommendation_run_index