"""Unit tests for packet extraction execution, matching, and review routing."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import TracebackType

from pytest import MonkeyPatch

import document_intelligence.packet_extraction as packet_extraction
from document_intelligence.models import (
    AccountMatchCandidate,
    AccountMatchResult,
    AccountMatchStatus,
    ArchivePreflightResult,
    DocumentAnalysisResult,
    DocumentAssetRecord,
    DocumentSource,
    ExtractedField,
    IssuerCategory,
    OcrResultRecord,
    PacketDocumentRecord,
    PacketEventRecord,
    PacketRecord,
    PacketStatus,
    PacketWorkspaceSnapshot,
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStageName,
    ProfileSelectionMode,
    PromptProfileCandidate,
    PromptProfileId,
    PromptProfileSelection,
)
from document_intelligence.settings import AppSettings


def build_settings(**overrides: object) -> AppSettings:
    """Build settings for packet extraction tests."""

    values: dict[str, object] = {
        "low_confidence_threshold": 0.8,
        "processed_container_name": "processed-documents",
        "required_fields": ("account_number", "statement_date"),
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
    """A DB-API connection stub that records extraction SQL statements."""

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


def build_prompt_profile_selection() -> PromptProfileSelection:
    """Build a stable prompt-profile selection payload for extraction tests."""

    return PromptProfileSelection(
        candidate_profiles=(
            PromptProfileCandidate(
                profile_id=PromptProfileId.BANK_STATEMENT,
                issuer_category=IssuerCategory.BANK,
                rationale=("requested prompt profile was 'bank_statement'",),
                score=100,
            ),
        ),
        document_type_hints=("statement",),
        issuer_category=IssuerCategory.BANK,
        keyword_hints=("account number", "statement date"),
        primary_profile_id=PromptProfileId.BANK_STATEMENT,
        prompt_focus=("account identifiers", "statement periods"),
        selection_mode=ProfileSelectionMode.EXPLICIT,
        system_prompt="Extract bank-statement evidence.",
    )


def build_snapshot() -> PacketWorkspaceSnapshot:
    """Build a packet workspace snapshot with one queued extraction document."""

    packet = PacketRecord(
        created_at_utc=datetime(2026, 4, 6, 18, 0, tzinfo=UTC),
        packet_id="pkt_archive_001",
        packet_name="extraction packet",
        packet_tags=(),
        received_at_utc=datetime(2026, 4, 6, 18, 0, tzinfo=UTC),
        source=DocumentSource.SCANNED_UPLOAD,
        source_uri="manual://packets/pkt_archive_001",
        status=PacketStatus.EXTRACTING,
        submitted_by="operator@example.com",
        updated_at_utc=datetime(2026, 4, 6, 18, 0, tzinfo=UTC),
    )
    document = PacketDocumentRecord(
        account_candidates=("acct_123",),
        archive_preflight=ArchivePreflightResult(),
        content_type="application/pdf",
        created_at_utc=datetime(2026, 4, 6, 18, 1, tzinfo=UTC),
        document_id="doc_child_001",
        document_text="Statement page one",
        file_name="statement.pdf",
        issuer_category=IssuerCategory.BANK,
        issuer_name="Fabrikam Bank",
        packet_id=packet.packet_id,
        received_at_utc=datetime(2026, 4, 6, 18, 1, tzinfo=UTC),
        source=DocumentSource.SCANNED_UPLOAD,
        source_summary="Monthly statement",
        source_tags=("bank", "statement"),
        source_uri=packet.source_uri,
        status=PacketStatus.EXTRACTING,
        updated_at_utc=datetime(2026, 4, 6, 18, 1, tzinfo=UTC),
    )
    asset = DocumentAssetRecord(
        asset_id="asset_child_001",
        asset_role="archive_extracted_member",
        blob_name="statement.pdf",
        container_name="raw-documents",
        content_length_bytes=64,
        content_type="application/pdf",
        created_at_utc=datetime(2026, 4, 6, 18, 1, tzinfo=UTC),
        document_id=document.document_id,
        packet_id=packet.packet_id,
        storage_uri="https://storage.example/raw/statement.pdf",
    )
    extraction_job = ProcessingJobRecord(
        attempt_number=1,
        created_at_utc=datetime(2026, 4, 6, 18, 2, tzinfo=UTC),
        document_id=document.document_id,
        job_id="job_ext_001",
        packet_id=packet.packet_id,
        queued_at_utc=datetime(2026, 4, 6, 18, 2, tzinfo=UTC),
        stage_name=ProcessingStageName.EXTRACTION,
        status=ProcessingJobStatus.QUEUED,
        updated_at_utc=datetime(2026, 4, 6, 18, 2, tzinfo=UTC),
    )
    ocr_result = OcrResultRecord(
        created_at_utc=datetime(2026, 4, 6, 18, 2, tzinfo=UTC),
        document_id=document.document_id,
        model_name="prebuilt-layout",
        ocr_confidence=0.93,
        ocr_result_id="ocr_001",
        packet_id=packet.packet_id,
        page_count=2,
        provider="azure_document_intelligence",
        text_excerpt="Statement for account 1234",
        text_storage_uri="https://storage.example/packet-ocr/doc_child_001/ocr_001.txt",
    )
    queued_event = PacketEventRecord(
        created_at_utc=datetime(2026, 4, 6, 18, 2, tzinfo=UTC),
        document_id=document.document_id,
        event_id=1,
        event_payload={
            "strategy": {
                "classification_result_id": "clsr_001",
                "document_type_id": "doc_bank_statement",
                "document_type_key": "bank_statement",
                "matching_path": "account_number_lookup",
                "prompt_profile_id": "bank_statement",
                "required_fields": ["account_number", "statement_date"],
                "strategy_source": "classification_contract",
            }
        },
        event_type="document.extraction.queued",
        packet_id=packet.packet_id,
    )
    return PacketWorkspaceSnapshot(
        packet=packet,
        documents=(document,),
        document_assets=(asset,),
        packet_events=(queued_event,),
        processing_jobs=(extraction_job,),
        ocr_results=(ocr_result,),
        extraction_results=(),
        classification_results=(),
        account_match_runs=(),
        review_tasks=(),
        review_decisions=(),
        operator_notes=(),
        audit_events=(),
        recommendation_runs=(),
        recommendation_results=(),
    )


def test_execute_packet_extraction_stage_creates_review_task(
    monkeypatch: MonkeyPatch,
) -> None:
    """Risky extraction outcomes should persist review work alongside results."""

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

        def list_document_type_definitions(self) -> tuple[object, ...]:
            return ()

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_extraction,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_extraction,
        "download_blob_text",
        lambda **kwargs: "Statement for account 1234",
    )
    monkeypatch.setattr(
        packet_extraction,
        "extract_document_from_ocr",
        lambda *args, **kwargs: DocumentAnalysisResult(
            document_type="bank_statement",
            extracted_fields=(
                ExtractedField(
                    name="account_number",
                    value="1234",
                    confidence=0.62,
                ),
            ),
            model_name="prebuilt-layout+gpt4o-deployment",
            ocr_confidence=0.93,
            ocr_text="Statement for account 1234",
            page_count=2,
            prompt_profile=build_prompt_profile_selection(),
            provider="azure_document_intelligence+azure_openai",
            summary="Bank statement extracted with one missing field.",
            warnings=("used test extraction",),
        ),
    )
    monkeypatch.setattr(
        packet_extraction,
        "match_document_to_account",
        lambda *args, **kwargs: AccountMatchResult(
            candidates=(
                AccountMatchCandidate(
                    account_id="acct_123",
                    account_number="1234",
                    debtor_name="Pat Doe",
                    issuer_name="Fabrikam Bank",
                    matched_on=("account_number_exact",),
                    score=81.0,
                ),
                AccountMatchCandidate(
                    account_id="acct_456",
                    account_number="1234",
                    debtor_name="Pat Doe",
                    issuer_name="Fabrikam Bank",
                    matched_on=("account_number_exact",),
                    score=78.0,
                ),
            ),
            rationale="Multiple SQL candidates scored too closely to auto-link.",
            selected_account_id=None,
            status=AccountMatchStatus.AMBIGUOUS,
        ),
    )
    monkeypatch.setattr(
        packet_extraction,
        "open_sql_connection",
        fake_open_sql_connection,
    )

    response = packet_extraction.execute_packet_extraction_stage(
        "pkt_archive_001",
        build_settings(),
    )

    assert response.executed_document_count == 1
    assert response.status == PacketStatus.AWAITING_REVIEW
    assert response.next_stage == ProcessingStageName.REVIEW
    assert response.processed_documents[0].review_task_id is not None
    assert (
        response.processed_documents[0].review_decision.requires_manual_review
        is True
    )
    assert response.processed_documents[0].extraction_strategy.strategy_source == (
        "classification_contract"
    )
    assert connection.committed is True
    assert connection.rolled_back is False
    assert any(
        "INSERT INTO dbo.ExtractionResults" in statement[0]
        for statement in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.AccountMatchRuns" in statement[0]
        for statement in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.ReviewTasks" in statement[0]
        for statement in connection.executed_statements
    )
    assert any(
        "UPDATE dbo.Packets" in statement[0]
        and statement[1] is not None
        and statement[1][0] == "awaiting_review"
        for statement in connection.executed_statements
    )
    extraction_insert = next(
        params
        for statement, params in connection.executed_statements
        if "INSERT INTO dbo.ExtractionResults" in statement
    )
    assert extraction_insert is not None
    extraction_payload = json.loads(str(extraction_insert[8]))
    assert extraction_payload["contentControls"]["retentionClass"] == (
        "extracted_content"
    )
    assert extraction_payload["contentControls"]["containsSensitiveContent"] is True
    assert extraction_payload["contentControls"]["maskedFields"] == []


def test_execute_packet_extraction_stage_advances_to_recommendation_ready(
    monkeypatch: MonkeyPatch,
) -> None:
    """Clean extraction outcomes should become recommendation-ready."""

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

        def list_document_type_definitions(self) -> tuple[object, ...]:
            return ()

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_extraction,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_extraction,
        "download_blob_text",
        lambda **kwargs: "Statement for account 1234 dated 2026-03-31",
    )
    monkeypatch.setattr(
        packet_extraction,
        "extract_document_from_ocr",
        lambda *args, **kwargs: DocumentAnalysisResult(
            document_type="bank_statement",
            extracted_fields=(
                ExtractedField(
                    name="account_number",
                    value="1234",
                    confidence=0.96,
                ),
                ExtractedField(
                    name="statement_date",
                    value="2026-03-31",
                    confidence=0.94,
                ),
            ),
            model_name="prebuilt-layout+gpt4o-deployment",
            ocr_confidence=0.93,
            ocr_text="Statement for account 1234 dated 2026-03-31",
            page_count=2,
            prompt_profile=build_prompt_profile_selection(),
            provider="azure_document_intelligence+azure_openai",
            summary="Bank statement extracted cleanly.",
            warnings=(),
        ),
    )
    monkeypatch.setattr(
        packet_extraction,
        "match_document_to_account",
        lambda *args, **kwargs: AccountMatchResult(
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
            rationale="Matched to the highest-ranked Azure SQL account candidate.",
            selected_account_id="acct_123",
            status=AccountMatchStatus.MATCHED,
        ),
    )
    monkeypatch.setattr(
        packet_extraction,
        "open_sql_connection",
        fake_open_sql_connection,
    )

    response = packet_extraction.execute_packet_extraction_stage(
        "pkt_archive_001",
        build_settings(),
    )

    assert response.executed_document_count == 1
    assert response.status == PacketStatus.READY_FOR_RECOMMENDATION
    assert response.next_stage == ProcessingStageName.RECOMMENDATION
    assert response.processed_documents[0].recommendation_job_id is not None
    assert response.processed_documents[0].review_task_id is None
    assert response.processed_documents[0].selected_account_id == "acct_123"
    assert (
        response.processed_documents[0].review_decision.requires_manual_review
        is False
    )
    assert connection.committed is True
    assert connection.rolled_back is False
    assert not any(
        "INSERT INTO dbo.ReviewTasks" in statement[0]
        for statement in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.ProcessingJobs" in statement[0]
        and statement[1] is not None
        and statement[1][3] == "recommendation"
        for statement in connection.executed_statements
    )
    assert any(
        "UPDATE dbo.Packets" in statement[0]
        and statement[1] is not None
        and statement[1][0] == "ready_for_recommendation"
        for statement in connection.executed_statements
    )
    extraction_insert = next(
        params
        for statement, params in connection.executed_statements
        if "INSERT INTO dbo.ExtractionResults" in statement
    )
    assert extraction_insert is not None
    extraction_payload = json.loads(str(extraction_insert[8]))
    assert extraction_payload["contentControls"]["retentionClass"] == (
        "extracted_content"
    )
    assert extraction_payload["contentControls"]["containsSensitiveContent"] is True
    assert extraction_payload["contentControls"]["maskedFields"] == []
