"""Unit tests for packet classification execution and OCR handoff."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace, TracebackType

from pytest import MonkeyPatch

import document_intelligence.packet_classification as packet_classification
from document_intelligence.models import (
    ArchivePreflightResult,
    ClassificationPriorRecord,
    ClassificationResultSource,
    DocumentAssetRecord,
    DocumentSource,
    IssuerCategory,
    ManagedClassificationDefinitionRecord,
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


def build_settings(**overrides: object) -> AppSettings:
    """Build settings for packet classification tests."""

    values: dict[str, object] = {
        "sql_connection_string": (
            "Server=tcp:test-sql.database.windows.net,1433;"
            "Database=docintel;User ID=docintel;Password=Password123!"
        ),
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
    """A DB-API connection stub that records classification SQL statements."""

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
    requested_prompt_profile_id: PromptProfileId | None = None,
) -> PacketWorkspaceSnapshot:
    """Build a packet workspace snapshot with one queued classification child."""

    packet = PacketRecord(
        created_at_utc=datetime(2026, 4, 5, 17, 0, tzinfo=UTC),
        packet_id="pkt_archive_001",
        packet_name="archive packet",
        packet_tags=(),
        received_at_utc=datetime(2026, 4, 5, 17, 0, tzinfo=UTC),
        source=DocumentSource.SCANNED_UPLOAD,
        source_uri="manual://packets/pkt_archive_001",
        status=PacketStatus.CLASSIFYING,
        submitted_by="operator@example.com",
        updated_at_utc=datetime(2026, 4, 5, 17, 0, tzinfo=UTC),
    )
    parent_document = PacketDocumentRecord(
        archive_preflight=ArchivePreflightResult(),
        content_type="application/zip",
        created_at_utc=datetime(2026, 4, 5, 17, 0, tzinfo=UTC),
        document_id="doc_parent_001",
        file_name="archive.zip",
        packet_id=packet.packet_id,
        received_at_utc=datetime(2026, 4, 5, 17, 0, tzinfo=UTC),
        source=DocumentSource.SCANNED_UPLOAD,
        source_uri=packet.source_uri,
        status=PacketStatus.COMPLETED,
        updated_at_utc=datetime(2026, 4, 5, 17, 0, tzinfo=UTC),
    )
    child_document = PacketDocumentRecord(
        archive_preflight=ArchivePreflightResult(),
        content_type="application/pdf",
        created_at_utc=datetime(2026, 4, 5, 17, 1, tzinfo=UTC),
        document_id="doc_child_001",
        file_hash_sha256=(
            "1ab1c490a7f757b76daba32673c30d2a2c6493f7c54dfdeb22725b08da45d141"
        ),
        file_name="statement.pdf",
        issuer_category=IssuerCategory.BANK,
        issuer_name="Fabrikam Bank",
        packet_id=packet.packet_id,
        received_at_utc=datetime(2026, 4, 5, 17, 1, tzinfo=UTC),
        requested_prompt_profile_id=requested_prompt_profile_id,
        source=DocumentSource.SCANNED_UPLOAD,
        source_summary="Archive child statement",
        source_tags=("bank", "statement"),
        source_uri=packet.source_uri,
        status=PacketStatus.CLASSIFYING,
        updated_at_utc=datetime(2026, 4, 5, 17, 1, tzinfo=UTC),
    )
    asset = DocumentAssetRecord(
        asset_id="asset_child_001",
        asset_role="archive_extracted_member",
        blob_name="statement.pdf",
        container_name="raw-documents",
        content_length_bytes=64,
        content_type="application/pdf",
        created_at_utc=datetime(2026, 4, 5, 17, 1, tzinfo=UTC),
        document_id=child_document.document_id,
        packet_id=packet.packet_id,
        storage_uri="https://storage.example/raw/statement.pdf",
    )
    parent_job = ProcessingJobRecord(
        attempt_number=1,
        completed_at_utc=datetime(2026, 4, 5, 17, 0, tzinfo=UTC),
        created_at_utc=datetime(2026, 4, 5, 17, 0, tzinfo=UTC),
        document_id=parent_document.document_id,
        job_id="job_parent_001",
        packet_id=packet.packet_id,
        queued_at_utc=datetime(2026, 4, 5, 17, 0, tzinfo=UTC),
        stage_name=ProcessingStageName.ARCHIVE_EXPANSION,
        status=ProcessingJobStatus.SUCCEEDED,
        updated_at_utc=datetime(2026, 4, 5, 17, 0, tzinfo=UTC),
    )
    child_job = ProcessingJobRecord(
        attempt_number=1,
        created_at_utc=datetime(2026, 4, 5, 17, 1, tzinfo=UTC),
        document_id=child_document.document_id,
        job_id="job_cls_001",
        packet_id=packet.packet_id,
        queued_at_utc=datetime(2026, 4, 5, 17, 1, tzinfo=UTC),
        stage_name=ProcessingStageName.CLASSIFICATION,
        status=ProcessingJobStatus.QUEUED,
        updated_at_utc=datetime(2026, 4, 5, 17, 1, tzinfo=UTC),
    )
    return PacketWorkspaceSnapshot(
        packet=packet,
        documents=(parent_document, child_document),
        document_assets=(asset,),
        packet_events=(),
        processing_jobs=(parent_job, child_job),
        ocr_results=(),
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


def build_rule_definitions() -> tuple[
    tuple[ManagedClassificationDefinitionRecord, ...],
    tuple[ManagedDocumentTypeDefinitionRecord, ...],
]:
    """Build managed definitions that resolve through the rule path."""

    return (
        (
            ManagedClassificationDefinitionRecord(
                classification_id="cls_bank_correspondence",
                classification_key="bank_correspondence",
                created_at_utc=datetime(2026, 4, 5, 16, 0, tzinfo=UTC),
                default_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                display_name="Bank Correspondence",
                issuer_category=IssuerCategory.BANK,
                updated_at_utc=datetime(2026, 4, 5, 16, 0, tzinfo=UTC),
            ),
        ),
        (
            ManagedDocumentTypeDefinitionRecord(
                classification_id="cls_bank_correspondence",
                created_at_utc=datetime(2026, 4, 5, 16, 0, tzinfo=UTC),
                default_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                display_name="Bank Statement",
                document_type_id="doc_bank_statement",
                document_type_key="bank_statement",
                required_fields=("account_number", "statement_date"),
                updated_at_utc=datetime(2026, 4, 5, 16, 0, tzinfo=UTC),
            ),
        ),
    )


def build_ai_definitions() -> tuple[
    tuple[ManagedClassificationDefinitionRecord, ...],
    tuple[ManagedDocumentTypeDefinitionRecord, ...],
]:
    """Build managed definitions that require the AI fallback path."""

    return (
        (
            ManagedClassificationDefinitionRecord(
                classification_id="cls_custom_correspondence",
                classification_key="custom_correspondence",
                created_at_utc=datetime(2026, 4, 5, 16, 0, tzinfo=UTC),
                display_name="Custom Correspondence",
                updated_at_utc=datetime(2026, 4, 5, 16, 0, tzinfo=UTC),
            ),
        ),
        (
            ManagedDocumentTypeDefinitionRecord(
                classification_id="cls_custom_correspondence",
                created_at_utc=datetime(2026, 4, 5, 16, 0, tzinfo=UTC),
                display_name="Custom Document",
                document_type_id="doc_custom_document",
                document_type_key="custom_document",
                required_fields=("statement_date",),
                updated_at_utc=datetime(2026, 4, 5, 16, 0, tzinfo=UTC),
            ),
        ),
    )


def test_execute_packet_classification_stage_promotes_rule_matched_document_to_ocr(
    monkeypatch: MonkeyPatch,
) -> None:
    """Rule-matched packet documents should complete classification and queue OCR."""

    connection = FakeConnection()
    snapshot = build_snapshot(
        requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT
    )
    classification_definitions, document_type_definitions = build_rule_definitions()

    class FakeRepository:
        """Repository stub that returns one packet snapshot and rule contracts."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self, packet_id: str
        ) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

        def list_classification_definitions(
            self,
        ) -> tuple[ManagedClassificationDefinitionRecord, ...]:
            return classification_definitions

        def list_classification_priors(
            self,
            **kwargs: object,
        ) -> tuple[ClassificationPriorRecord, ...]:
            del kwargs
            return ()

        def list_document_type_definitions(
            self,
        ) -> tuple[ManagedDocumentTypeDefinitionRecord, ...]:
            return document_type_definitions

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_classification,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_classification,
        "open_sql_connection",
        fake_open_sql_connection,
    )

    response = packet_classification.execute_packet_classification_stage(
        "pkt_archive_001",
        build_settings(),
    )

    assert response.executed_document_count == 1
    assert response.status == PacketStatus.OCR_RUNNING
    assert response.next_stage == ProcessingStageName.OCR
    assert response.processed_documents[0].classification_id == (
        "cls_bank_correspondence"
    )
    assert response.processed_documents[0].document_type_id == "doc_bank_statement"
    assert response.processed_documents[0].result_source == (
        ClassificationResultSource.RULE
    )
    assert connection.committed is True
    assert connection.rolled_back is False
    assert any(
        "UPDATE dbo.ProcessingJobs" in statement[0]
        for statement in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.ClassificationResults" in statement[0]
        and statement[1] is not None
        and statement[1][5] == "rule"
        for statement in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.ProcessingJobs" in statement[0]
        and statement[1] is not None
        and statement[1][3] == "ocr"
        for statement in connection.executed_statements
    )
    assert any(
        "UPDATE dbo.Packets" in statement[0]
        and statement[1] is not None
        and statement[1][0] == "ocr_running"
        for statement in connection.executed_statements
    )


def test_execute_packet_classification_stage_uses_ai_fallback_when_rules_miss(
    monkeypatch: MonkeyPatch,
) -> None:
    """AI fallback should classify the packet when rule contracts do not match."""

    connection = FakeConnection()
    snapshot = build_snapshot()
    classification_definitions, document_type_definitions = build_ai_definitions()

    class FakeRepository:
        """Repository stub that returns one packet snapshot and AI-only contracts."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self, packet_id: str
        ) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

        def list_classification_definitions(
            self,
        ) -> tuple[ManagedClassificationDefinitionRecord, ...]:
            return classification_definitions

        def list_classification_priors(
            self,
            **kwargs: object,
        ) -> tuple[ClassificationPriorRecord, ...]:
            del kwargs
            return ()

        def list_document_type_definitions(
            self,
        ) -> tuple[ManagedDocumentTypeDefinitionRecord, ...]:
            return document_type_definitions

    class FakeAzureOpenAI:
        """Azure OpenAI stub that returns one valid fallback classification."""

        def __init__(self, **kwargs: object) -> None:
            del kwargs
            message = SimpleNamespace(
                content=(
                    '{"classification_id":"cls_custom_correspondence",'
                    '"document_type_id":"doc_custom_document",'
                    '"confidence":0.88,"rationale":"matched fallback hints"}'
                )
            )
            choice = SimpleNamespace(message=message)
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **create_kwargs: SimpleNamespace(choices=[choice])
                )
            )

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_classification,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_classification,
        "AzureOpenAI",
        FakeAzureOpenAI,
    )
    monkeypatch.setattr(
        packet_classification,
        "open_sql_connection",
        fake_open_sql_connection,
    )

    response = packet_classification.execute_packet_classification_stage(
        "pkt_archive_001",
        build_settings(
            azure_openai_api_key="test-key",
            azure_openai_deployment="gpt4o-deployment",
            azure_openai_endpoint="https://aoai.example.com",
        ),
    )

    assert response.executed_document_count == 1
    assert response.processed_documents[0].classification_id == (
        "cls_custom_correspondence"
    )
    assert response.processed_documents[0].document_type_id == "doc_custom_document"
    assert response.processed_documents[0].result_source == (
        ClassificationResultSource.AI
    )
    assert any(
        "INSERT INTO dbo.ClassificationResults" in statement[0]
        and statement[1] is not None
        and statement[1][5] == "ai"
        for statement in connection.executed_statements
    )


def test_execute_packet_classification_stage_reuses_matching_prior(
    monkeypatch: MonkeyPatch,
) -> None:
    """Stored priors should short-circuit the colder rule and AI paths."""

    connection = FakeConnection()
    snapshot = build_snapshot()
    classification_definitions, document_type_definitions = build_rule_definitions()
    classification_prior = ClassificationPriorRecord(
        account_id="acct_123",
        classification_id="cls_bank_correspondence",
        classification_prior_id="prior_001",
        confidence_weight=0.97,
        confirmed_at_utc=datetime(2026, 4, 4, 12, 0, tzinfo=UTC),
        created_at_utc=datetime(2026, 4, 4, 12, 0, tzinfo=UTC),
        document_fingerprint=(
            "1ab1c490a7f757b76daba32673c30d2a2c6493f7c54dfdeb22725b08da45d141"
        ),
        document_type_id="doc_bank_statement",
        issuer_name_normalized="fabrikam bank",
        packet_id="pkt_prior_source",
        prompt_profile_id=PromptProfileId.BANK_STATEMENT,
        source_document_id="doc_prior_001",
        source_fingerprint=None,
        updated_at_utc=datetime(2026, 4, 4, 12, 0, tzinfo=UTC),
    )

    class FakeRepository:
        """Repository stub that returns one packet snapshot and a reusable prior."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self, packet_id: str
        ) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

        def list_classification_definitions(
            self,
        ) -> tuple[ManagedClassificationDefinitionRecord, ...]:
            return classification_definitions

        def list_classification_priors(
            self,
            **kwargs: object,
        ) -> tuple[ClassificationPriorRecord, ...]:
            if kwargs.get("document_fingerprint"):
                return (classification_prior,)
            return ()

        def list_document_type_definitions(
            self,
        ) -> tuple[ManagedDocumentTypeDefinitionRecord, ...]:
            return document_type_definitions

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_classification,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_classification,
        "open_sql_connection",
        fake_open_sql_connection,
    )

    response = packet_classification.execute_packet_classification_stage(
        "pkt_archive_001",
        build_settings(),
    )

    assert response.executed_document_count == 1
    assert response.processed_documents[0].result_source == (
        ClassificationResultSource.PRIOR_REUSE
    )
    assert response.processed_documents[0].classification_id == (
        "cls_bank_correspondence"
    )
    assert any(
        "INSERT INTO dbo.ClassificationResults" in statement[0]
        and statement[1] is not None
        and statement[1][5] == "prior_reuse"
        for statement in connection.executed_statements
    )


def test_execute_packet_classification_stage_routes_low_confidence_ai_to_review(
    monkeypatch: MonkeyPatch,
) -> None:
    """Low-confidence AI fallback classifications should pause for review."""

    connection = FakeConnection()
    snapshot = build_snapshot()
    classification_definitions, document_type_definitions = build_ai_definitions()

    class FakeRepository:
        """Repository stub that returns one packet snapshot and AI-only contracts."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self, packet_id: str
        ) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

        def list_classification_definitions(
            self,
        ) -> tuple[ManagedClassificationDefinitionRecord, ...]:
            return classification_definitions

        def list_classification_priors(
            self,
            **kwargs: object,
        ) -> tuple[ClassificationPriorRecord, ...]:
            del kwargs
            return ()

        def list_document_type_definitions(
            self,
        ) -> tuple[ManagedDocumentTypeDefinitionRecord, ...]:
            return document_type_definitions

    class FakeAzureOpenAI:
        """Azure OpenAI stub that returns a low-confidence fallback classification."""

        def __init__(self, **kwargs: object) -> None:
            del kwargs
            message = SimpleNamespace(
                content=(
                    '{"classification_id":"cls_custom_correspondence",'
                    '"document_type_id":"doc_custom_document",'
                    '"confidence":0.41,"rationale":"weak fallback hints"}'
                )
            )
            choice = SimpleNamespace(message=message)
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **create_kwargs: SimpleNamespace(choices=[choice])
                )
            )

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(
        packet_classification,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_classification,
        "AzureOpenAI",
        FakeAzureOpenAI,
    )
    monkeypatch.setattr(
        packet_classification,
        "open_sql_connection",
        fake_open_sql_connection,
    )

    response = packet_classification.execute_packet_classification_stage(
        "pkt_archive_001",
        build_settings(
            azure_openai_api_key="test-key",
            azure_openai_deployment="gpt4o-deployment",
            azure_openai_endpoint="https://aoai.example.com",
            classification_drift_confidence_threshold=0.75,
        ),
    )

    assert response.executed_document_count == 1
    assert response.status == PacketStatus.AWAITING_REVIEW
    assert response.next_stage == ProcessingStageName.REVIEW
    assert response.processed_documents[0].result_source == ClassificationResultSource.AI
    assert response.processed_documents[0].ocr_job_id is None
    assert response.processed_documents[0].review_task_id is not None
    assert any(
        "INSERT INTO dbo.ClassificationResults" in statement[0]
        and statement[1] is not None
        and statement[1][5] == "ai"
        for statement in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.ReviewTasks" in statement[0]
        and statement[1] is not None
        and statement[1][5] == '["classification_drift"]'
        for statement in connection.executed_statements
    )
    assert not any(
        "INSERT INTO dbo.ProcessingJobs" in statement[0]
        and statement[1] is not None
        and statement[1][3] == "ocr"
        for statement in connection.executed_statements
    )
    review_required_event = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.PacketEvents" in statement[0]
        and statement[1] is not None
        and statement[1][2] == "document.classification.review_required"
    )
    assert review_required_event[1] is not None
    review_required_payload = json.loads(str(review_required_event[1][3]))
    assert review_required_payload["reasonCodes"] == ["classification_drift"]


def test_execute_packet_classification_stage_routes_unseen_documents_to_review(
    monkeypatch: MonkeyPatch,
) -> None:
    """Unclassifiable documents should open review work instead of failing the run."""

    connection = FakeConnection()
    snapshot = build_snapshot()

    class FakeRepository:
        """Repository stub that returns no matching contracts or priors."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(
            self, packet_id: str
        ) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

        def list_classification_definitions(
            self,
        ) -> tuple[ManagedClassificationDefinitionRecord, ...]:
            return ()

        def list_classification_priors(
            self,
            **kwargs: object,
        ) -> tuple[ClassificationPriorRecord, ...]:
            del kwargs
            return ()

        def list_document_type_definitions(
            self,
        ) -> tuple[ManagedDocumentTypeDefinitionRecord, ...]:
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
        packet_classification,
        "SqlOperatorStateRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        packet_classification,
        "open_sql_connection",
        fake_open_sql_connection,
    )

    response = packet_classification.execute_packet_classification_stage(
        "pkt_archive_001",
        build_settings(),
    )

    assert response.executed_document_count == 1
    assert response.status == PacketStatus.AWAITING_REVIEW
    assert response.next_stage == ProcessingStageName.REVIEW
    assert response.processed_documents[0].classification_result_id is None
    assert response.processed_documents[0].ocr_job_id is None
    assert response.processed_documents[0].result_source is None
    assert response.processed_documents[0].review_task_id is not None
    assert not any(
        "INSERT INTO dbo.ClassificationResults" in statement[0]
        for statement in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.ReviewTasks" in statement[0]
        and statement[1] is not None
        and statement[1][5] == '["unseen_document_type"]'
        for statement in connection.executed_statements
    )
    review_required_event = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.PacketEvents" in statement[0]
        and statement[1] is not None
        and statement[1][2] == "document.classification.review_required"
    )
    assert review_required_event[1] is not None
    review_required_payload = json.loads(str(review_required_event[1][3]))
    assert review_required_payload["reasonCodes"] == ["unseen_document_type"]
