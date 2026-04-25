"""Unit tests for the remaining Epic 1 SQL operator-state repository."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from types import TracebackType

from pytest import MonkeyPatch

import document_intelligence.operator_state as operator_state
from document_intelligence.models import (
    AccountMatchStatus,
    ArchivePreflightDisposition,
    AuditEventCreateRequest,
    ClassificationPriorCreateRequest,
    ClassificationResultCreateRequest,
    ClassificationResultSource,
    DocumentSource,
    ExtractionResultCreateRequest,
    IssuerCategory,
    OperatorNoteCreateRequest,
    PacketAssignmentState,
    PacketQueueListRequest,
    PacketStatus,
    ProcessingStageName,
    PromptProfileId,
)
from document_intelligence.settings import AppSettings


def build_settings(**overrides: object) -> AppSettings:
    """Build app settings for SQL operator-state repository tests."""

    values: dict[str, object] = {
        "sql_connection_string": (
            "Server=tcp:test-sql.database.windows.net,1433;"
            "Database=docintel;User ID=docintel;Password=Password123!"
        )
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


class FakeSequencedCursor:
    """A DB-API cursor stub that returns queued result sets in order."""

    def __init__(self, connection: FakeSequencedConnection) -> None:
        self._connection = connection
        self._current_result: object = []

    def __enter__(self) -> FakeSequencedCursor:
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
        if self._connection.result_sets:
            self._current_result = self._connection.result_sets.pop(0)
            return

        self._current_result = []

    def fetchone(self) -> tuple[object, ...] | None:
        if isinstance(self._current_result, tuple):
            return self._current_result
        if isinstance(self._current_result, list):
            if not self._current_result:
                return None
            first_row = self._current_result[0]
            return first_row if isinstance(first_row, tuple) else None
        return None

    def fetchall(self) -> list[tuple[object, ...]]:
        if isinstance(self._current_result, list):
            return [row for row in self._current_result if isinstance(row, tuple)]
        if isinstance(self._current_result, tuple):
            return [self._current_result]
        return []


class FakeSequencedConnection:
    """A DB-API connection stub that records executed statements."""

    def __init__(self, result_sets: list[object] | None = None) -> None:
        self.result_sets = result_sets or []
        self.executed_statements: list[tuple[str, tuple[object, ...] | None]] = []
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> FakeSequencedCursor:
        return FakeSequencedCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_list_managed_contracts_hydrates_seed_rows(
    monkeypatch: MonkeyPatch,
) -> None:
    """The repository should hydrate managed definitions and prompt profiles."""

    connections = [
        FakeSequencedConnection(
            result_sets=[
                [
                    (
                        "cls_bank_correspondence",
                        "bank_correspondence",
                        "Bank Correspondence",
                        None,
                        True,
                        "bank",
                        "bank_statement",
                        datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                        datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                    )
                ]
            ]
        ),
        FakeSequencedConnection(
            result_sets=[
                [
                    (
                        "doc_bank_statement",
                        "bank_statement",
                        "Bank Statement",
                        None,
                        True,
                        "cls_bank_correspondence",
                        "bank_statement",
                        '["account_number","statement_date"]',
                        datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                        datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                    )
                ]
            ]
        ),
        FakeSequencedConnection(
            result_sets=[
                [
                    (
                        "bank_statement",
                        "Bank Statement",
                        None,
                        "bank",
                        True,
                        datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                        datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                    )
                ]
            ]
        ),
        FakeSequencedConnection(
            result_sets=[
                [
                    (
                        "ppv_bank_statement_v1",
                        "bank_statement",
                        1,
                        '{"requiredFields":["account_number","statement_date"]}',
                        True,
                        datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                    )
                ]
            ]
        ),
    ]

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connections.pop(0)

    monkeypatch.setattr(operator_state, "open_sql_connection", fake_open_sql_connection)

    repository = operator_state.SqlOperatorStateRepository(build_settings())

    classifications = repository.list_classification_definitions()
    document_types = repository.list_document_type_definitions()
    prompt_profiles = repository.list_prompt_profiles()
    prompt_profile_versions = repository.list_prompt_profile_versions()

    assert classifications[0].classification_key == "bank_correspondence"
    assert classifications[0].default_prompt_profile_id == (
        PromptProfileId.BANK_STATEMENT
    )
    assert document_types[0].required_fields == (
        "account_number",
        "statement_date",
    )
    assert prompt_profiles[0].issuer_category == IssuerCategory.BANK
    assert prompt_profile_versions[0].definition_payload["requiredFields"] == [
        "account_number",
        "statement_date",
    ]


def test_persist_operator_confirmed_classification_inserts_result_and_prior(
    monkeypatch: MonkeyPatch,
) -> None:
    """Operator-confirmed classifications should persist both result and prior rows."""

    connection = FakeSequencedConnection()

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(operator_state, "open_sql_connection", fake_open_sql_connection)

    repository = operator_state.SqlOperatorStateRepository(build_settings())
    classification_record, prior_record = (
        repository.persist_operator_confirmed_classification(
            classification_request=ClassificationResultCreateRequest(
                packet_id="pkt_demo_001",
                document_id="doc_demo_001",
                classification_id="cls_bank_correspondence",
                document_type_id="doc_bank_statement",
                prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                confidence=0.97,
                result_source=ClassificationResultSource.AI,
                result_payload={"source": "operator"},
            ),
            prior_request=ClassificationPriorCreateRequest(
                packet_id="pkt_demo_001",
                source_document_id="doc_demo_001",
                document_fingerprint=(
                    "8d74e7eed6a76016ff7858d11d2f74c07a814e3cd3f81c4b6cf2e5f0376ea9d4"
                ),
                source_fingerprint=(
                    "d86d3f2c0214f31f9f19fe5f4d1f4c6b0f9bdb7612cd2925976ec965bbf64b0e"
                ),
                issuer_name_normalized="fabrikam bank",
                classification_id="cls_bank_correspondence",
                document_type_id="doc_bank_statement",
                prompt_profile_id=PromptProfileId.BANK_STATEMENT,
                confirmed_by_email="operator@example.com",
            ),
        )
    )

    assert classification_record.result_source == (
        ClassificationResultSource.OPERATOR_CONFIRMED
    )
    assert prior_record.document_type_id == "doc_bank_statement"
    assert connection.committed is True
    assert len(connection.executed_statements) == 2
    assert "INSERT INTO dbo.ClassificationResults" in (
        connection.executed_statements[0][0]
    )
    assert "INSERT INTO dbo.ClassificationPriors" in (
        connection.executed_statements[1][0]
    )


def test_get_packet_workspace_snapshot_hydrates_related_records(
    monkeypatch: MonkeyPatch,
) -> None:
    """The repository should hydrate the packet workspace snapshot from SQL."""

    connection = FakeSequencedConnection(
        result_sets=[
            (
                "pkt_demo_001",
                "demo packet",
                "scanned_upload",
                "manual://packets/pkt_demo_001",
                "awaiting_review",
                "operator@example.com",
                '["urgent"]',
                datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                datetime(2026, 4, 5, 12, 5, tzinfo=UTC),
                "a" * 64,
                "b" * 64,
                None,
                '{"status":"possible_duplicate","signals":[]}',
            ),
            [
                (
                    "doc_demo_001",
                    "pkt_demo_001",
                    "sample.pdf",
                    "application/pdf",
                    "scanned_upload",
                    "manual://packets/pkt_demo_001",
                    "awaiting_review",
                    None,
                    "unknown",
                    "bank_statement",
                    None,
                    '[]',
                    '[]',
                    None,
                    "c" * 64,
                    "doc_archive_parent",
                    "asset_archive_parent",
                    "nested/sample.pdf",
                    1,
                    '{"archivePreflight":{"disposition":"not_archive","is_archive":false}}',
                    datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                    datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                    datetime(2026, 4, 5, 12, 5, tzinfo=UTC),
                )
            ],
            [
                (
                    "asset_demo_001",
                    "pkt_demo_001",
                    "doc_demo_001",
                    "original_upload",
                    "raw-documents",
                    "blob-name",
                    "application/pdf",
                    1024,
                    "https://storage.example/blob-name",
                    datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                )
            ],
            [
                (
                    1,
                    "pkt_demo_001",
                    "doc_demo_001",
                    "document.manual_intake.staged",
                    '{"blobUri":"https://storage.example/blob-name"}',
                    datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                )
            ],
            [
                (
                    "job_demo_001",
                    "pkt_demo_001",
                    "doc_demo_001",
                    "ocr",
                    "queued",
                    1,
                    datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                    None,
                    None,
                    None,
                    None,
                    datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                    datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
                )
            ],
            [
                (
                    "ocr_demo_001",
                    "pkt_demo_001",
                    "doc_demo_001",
                    "azure_document_intelligence",
                    "prebuilt-layout",
                    1,
                    0.98,
                    "https://storage.example/ocr.txt",
                    "excerpt",
                    datetime(2026, 4, 5, 12, 1, tzinfo=UTC),
                )
            ],
            [
                (
                    "ext_demo_001",
                    "pkt_demo_001",
                    "doc_demo_001",
                    "azure_openai",
                    "gpt-4o",
                    "bank_statement",
                    "bank_statement",
                    "summary",
                    (
                        '{"fields":[],"contentControls":{'
                        '"containsSensitiveContent":true,'
                        '"maskedFields":[],'
                        '"retentionClass":"extracted_content"}}'
                    ),
                    datetime(2026, 4, 5, 12, 2, tzinfo=UTC),
                )
            ],
            [
                (
                    "clsr_demo_001",
                    "pkt_demo_001",
                    "doc_demo_001",
                    "cls_bank_correspondence",
                    "doc_bank_statement",
                    "operator_confirmed",
                    0.99,
                    '{"reason":"verified"}',
                    "bank_statement",
                    datetime(2026, 4, 5, 12, 3, tzinfo=UTC),
                )
            ],
            [
                (
                    "match_demo_001",
                    "pkt_demo_001",
                    "doc_demo_001",
                    "matched",
                    "acct_001",
                    "Matched by account number",
                    datetime(2026, 4, 5, 12, 3, tzinfo=UTC),
                )
            ],
            [
                (
                    "match_demo_001",
                    "acct_001",
                    "12345",
                    "Jordan Patel",
                    "Fabrikam Bank",
                    '["account_number_exact"]',
                    97.0,
                    1,
                )
            ],
            [
                (
                    "task_demo_001",
                    "pkt_demo_001",
                    "doc_demo_001",
                    None,
                    None,
                    "awaiting_review",
                    "high",
                    "acct_001",
                    '["low_confidence"]',
                    "Needs review",
                    None,
                    datetime(2026, 4, 5, 12, 4, tzinfo=UTC),
                    datetime(2026, 4, 5, 12, 4, tzinfo=UTC),
                )
            ],
            [
                (
                    "decision_demo_001",
                    "task_demo_001",
                    "pkt_demo_001",
                    "doc_demo_001",
                    "approved",
                    None,
                    "acct_001",
                    "Looks good",
                    None,
                    "operator@example.com",
                    datetime(2026, 4, 5, 12, 10, tzinfo=UTC),
                )
            ],
            [
                (
                    "note_demo_001",
                    "pkt_demo_001",
                    "doc_demo_001",
                    "task_demo_001",
                    None,
                    "operator@example.com",
                    "Investigated OCR output.",
                    False,
                    datetime(2026, 4, 5, 12, 8, tzinfo=UTC),
                )
            ],
            [
                (
                    1,
                    None,
                    "operator@example.com",
                    "pkt_demo_001",
                    "doc_demo_001",
                    "task_demo_001",
                    "review.task.created",
                    '{"priority":"high"}',
                    datetime(2026, 4, 5, 12, 4, tzinfo=UTC),
                )
            ],
            [
                (
                    "recrun_demo_001",
                    "pkt_demo_001",
                    "doc_demo_001",
                    "task_demo_001",
                    "bank_statement",
                    "ready_for_review",
                    None,
                    "operator@example.com",
                    '{"inputs":[]}',
                    None,
                    datetime(2026, 4, 5, 12, 11, tzinfo=UTC),
                    datetime(2026, 4, 5, 12, 11, tzinfo=UTC),
                )
            ],
            [
                (
                    "recres_demo_001",
                    "recrun_demo_001",
                    "pkt_demo_001",
                    "doc_demo_001",
                    "debt_relief_recommendation",
                    "Recommend hardship review.",
                    '{"why":"verified evidence"}',
                    '[{"evidence_kind":"extracted_field","field_name":"account_number"}]',
                    0.82,
                    "Advisory only.",
                    "pending",
                    None,
                    None,
                    None,
                    datetime(2026, 4, 5, 12, 12, tzinfo=UTC),
                    datetime(2026, 4, 5, 12, 12, tzinfo=UTC),
                )
            ],
        ]
    )

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(operator_state, "open_sql_connection", fake_open_sql_connection)

    repository = operator_state.SqlOperatorStateRepository(build_settings())
    snapshot = repository.get_packet_workspace_snapshot("pkt_demo_001")

    assert snapshot.packet.packet_id == "pkt_demo_001"
    assert snapshot.packet.source == DocumentSource.SCANNED_UPLOAD
    assert snapshot.packet.status == PacketStatus.AWAITING_REVIEW
    assert snapshot.documents[0].requested_prompt_profile_id == (
        PromptProfileId.BANK_STATEMENT
    )
    assert snapshot.documents[0].lineage.parent_document_id == "doc_archive_parent"
    assert snapshot.documents[0].lineage.archive_depth == 1
    assert snapshot.documents[0].archive_preflight.disposition == (
        ArchivePreflightDisposition.NOT_ARCHIVE
    )
    assert snapshot.extraction_results[0].result_payload["contentControls"][
        "retentionClass"
    ] == "extracted_content"
    assert snapshot.account_match_runs[0].status == AccountMatchStatus.MATCHED
    assert snapshot.review_tasks[0].priority.value == "high"
    assert snapshot.recommendation_runs[0].status.value == "ready_for_review"
    assert snapshot.recommendation_results[0].evidence_items[0].field_name == (
        "account_number"
    )


def test_create_extraction_result_adds_content_controls(
    monkeypatch: MonkeyPatch,
) -> None:
    """Extraction results should persist retention metadata with the payload."""

    connection = FakeSequencedConnection()

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(operator_state, "open_sql_connection", fake_open_sql_connection)

    repository = operator_state.SqlOperatorStateRepository(build_settings())
    record = repository.create_extraction_result(
        ExtractionResultCreateRequest(
            packet_id="pkt_demo_001",
            document_id="doc_demo_001",
            provider="azure_openai",
            model_name="gpt-4o",
            document_type="bank_statement",
            prompt_profile_id=PromptProfileId.BANK_STATEMENT,
            summary="Extracted summary.",
            result_payload={
                "extractedFields": [
                    {
                        "name": "account_number",
                        "value": "1234",
                        "confidence": 0.97,
                    }
                ]
            },
        )
    )

    assert record.result_payload["contentControls"]["retentionClass"] == (
        "extracted_content"
    )
    assert record.result_payload["contentControls"]["containsSensitiveContent"] is True
    assert record.result_payload["contentControls"]["maskedFields"] == []
    extraction_insert = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.ExtractionResults" in statement[0]
    )
    assert extraction_insert[1] is not None
    persisted_payload = json.loads(str(extraction_insert[1][8]))
    assert persisted_payload["contentControls"]["retentionClass"] == (
        "extracted_content"
    )


def test_list_packet_queue_hydrates_paged_rows(
    monkeypatch: MonkeyPatch,
) -> None:
    """The repository should hydrate packet queue rows from SQL."""

    connection = FakeSequencedConnection(
        result_sets=[
            [
                (
                    "pkt_demo_001",
                    "demo packet",
                    "scanned_upload",
                    "manual://packets/pkt_demo_001",
                    "awaiting_review",
                    "operator@example.com",
                    '[]',
                    datetime(2026, 4, 7, 8, 0, tzinfo=UTC),
                    datetime(2026, 4, 7, 8, 0, tzinfo=UTC),
                    datetime(2026, 4, 7, 8, 5, tzinfo=UTC),
                    2,
                    1,
                    0,
                    1,
                    "assigned",
                    "ops@example.com",
                    datetime(2026, 4, 7, 8, 10, tzinfo=UTC),
                    "doc_demo_001",
                    "statement.pdf",
                    "Fabrikam Bank",
                    "bank",
                    "extraction",
                    "queued",
                    "bank_correspondence",
                    "bank_statement",
                    1,
                    3,
                    1,
                )
            ]
        ]
    )

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(operator_state, "open_sql_connection", fake_open_sql_connection)

    repository = operator_state.SqlOperatorStateRepository(build_settings())
    response = repository.list_packet_queue(
        PacketQueueListRequest(page=1, page_size=25),
        stage_statuses=(PacketStatus.AWAITING_REVIEW,),
    )

    assert response.total_count == 1
    assert response.has_more is False
    assert response.items[0].packet_id == "pkt_demo_001"
    assert response.items[0].assignment_state == PacketAssignmentState.ASSIGNED
    assert response.items[0].assigned_user_email == "ops@example.com"
    assert response.items[0].classification_keys == ("bank_correspondence",)
    assert response.items[0].document_type_keys == ("bank_statement",)
    assert response.items[0].stage_name == ProcessingStageName.REVIEW
    executed_statement, params = connection.executed_statements[0]
    assert "FROM dbo.Packets p" in executed_statement
    assert params is not None
    assert "awaiting_review" in params


def test_create_operator_note_masks_sensitive_history(
    monkeypatch: MonkeyPatch,
) -> None:
    """Operator notes should mask obvious sensitive strings before persistence."""

    connection = FakeSequencedConnection()

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(operator_state, "open_sql_connection", fake_open_sql_connection)

    repository = operator_state.SqlOperatorStateRepository(build_settings())
    record = repository.create_operator_note(
        OperatorNoteCreateRequest(
            packet_id="pkt_demo_001",
            review_task_id="task_demo_001",
            created_by_email="reviewer@example.com",
            note_text="Contact owner@example.com about card 4111 1111 1111 1111.",
        )
    )

    assert record.note_text == (
        "Contact o***@example.com about card xxxx xxxx xxxx 1111."
    )
    note_insert = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.OperatorNotes" in statement[0]
    )
    assert note_insert[1] is not None
    assert note_insert[1][6] == record.note_text


def test_create_audit_event_masks_payload_and_adds_content_controls(
    monkeypatch: MonkeyPatch,
) -> None:
    """Audit events should persist masked payloads with content-control metadata."""

    connection = FakeSequencedConnection()

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ):
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(operator_state, "open_sql_connection", fake_open_sql_connection)

    repository = operator_state.SqlOperatorStateRepository(build_settings())
    record = repository.create_audit_event(
        AuditEventCreateRequest(
            packet_id="pkt_demo_001",
            event_type="review.decision.recorded",
            event_payload={
                "note": "owner@example.com 4111 1111 1111 1111",
                "nested": {"account": "1234567890"},
            },
        )
    )

    assert record.event_payload is not None
    assert record.event_payload["note"] == "o***@example.com xxxx xxxx xxxx 1111"
    assert record.event_payload["nested"]["account"] == "xxxxxx7890"
    assert record.event_payload["contentControls"]["retentionClass"] == "audit_history"
    assert record.event_payload["contentControls"]["containsSensitiveContent"] is True
    audit_insert = next(
        statement
        for statement in connection.executed_statements
        if "INSERT INTO dbo.AuditEvents" in statement[0]
    )
    assert audit_insert[1] is not None
    persisted_payload = json.loads(str(audit_insert[1][6]))
    assert persisted_payload["contentControls"]["retentionClass"] == "audit_history"
    assert "note" in persisted_payload["contentControls"]["maskedFields"]