"""Unit tests for packet review decisions and packet-state handoff."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import TracebackType

from pytest import MonkeyPatch, raises

from document_intelligence.models import (
    AccountMatchCandidate,
    AccountMatchRunRecord,
    AccountMatchStatus,
    ArchivePreflightResult,
    DocumentSource,
    ExtractionFieldEditInput,
    ExtractionResultRecord,
    PacketDocumentRecord,
    PacketRecord,
    PacketReviewAssignmentRequest,
    PacketReviewDecisionRequest,
    PacketReviewExtractionEditRequest,
    PacketReviewNoteRequest,
    PacketReviewTaskCreateRequest,
    PacketStatus,
    PacketWorkspaceSnapshot,
    ProcessingJobRecord,
    ProcessingJobStatus,
    ProcessingStageName,
    PromptProfileId,
    ReviewDecisionRecord,
    ReviewStatus,
    ReviewTaskPriority,
    ReviewTaskRecord,
)
import document_intelligence.packet_review as packet_review
from document_intelligence.settings import AppSettings


def build_settings(**overrides: object) -> AppSettings:
    """Build settings for packet review tests."""

    values: dict[str, object] = {
        "sql_connection_string": (
            "Server=tcp:test-sql.database.windows.net,1433;"
            "Database=docintel;User ID=docintel;Password=Password123!"
        ),
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


class FakeCursor:
    """A DB-API cursor stub that records review SQL statements."""

    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection
        self.rowcount = -1

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
        self.rowcount = 1
        if (
            normalized_statement.startswith("UPDATE dbo.ReviewTasks")
            and self._connection.review_task_update_rowcount is not None
        ):
            self.rowcount = self._connection.review_task_update_rowcount
        self._connection.executed_statements.append((normalized_statement, params))


class FakeConnection:
    """A DB-API connection stub that records review SQL statements."""

    def __init__(self, *, review_task_update_rowcount: int | None = None) -> None:
        self.committed = False
        self.executed_statements: list[tuple[str, tuple[object, ...] | None]] = []
        self.review_task_update_rowcount = review_task_update_rowcount
        self.rolled_back = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def build_snapshot(
    *,
    document_status: PacketStatus = PacketStatus.AWAITING_REVIEW,
    include_review_task: bool = True,
    packet_status: PacketStatus = PacketStatus.AWAITING_REVIEW,
    with_existing_decision: bool = False,
) -> PacketWorkspaceSnapshot:
    """Build a packet workspace snapshot with one SQL-backed review task."""

    packet = PacketRecord(
        created_at_utc=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
        packet_id="pkt_archive_001",
        packet_name="review packet",
        packet_tags=(),
        received_at_utc=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
        source=DocumentSource.SCANNED_UPLOAD,
        source_uri="manual://packets/pkt_archive_001",
        status=packet_status,
        submitted_by="operator@example.com",
        updated_at_utc=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
    )
    document = PacketDocumentRecord(
        account_candidates=("acct_123",),
        archive_preflight=ArchivePreflightResult(),
        content_type="application/pdf",
        created_at_utc=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
        document_id="doc_child_001",
        document_text="Statement for account 1234.",
        file_name="statement.pdf",
        packet_id=packet.packet_id,
        received_at_utc=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
        requested_prompt_profile_id=PromptProfileId.BANK_STATEMENT,
        source=DocumentSource.SCANNED_UPLOAD,
        source_uri=packet.source_uri,
        status=document_status,
        updated_at_utc=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
    )
    review_task = ReviewTaskRecord(
        assigned_user_email="reviewer@example.com",
        assigned_user_id=None,
        created_at_utc=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
        document_id=document.document_id,
        due_at_utc=None,
        notes_summary="Extraction needs confirmation.",
        packet_id=packet.packet_id,
        priority=ReviewTaskPriority.NORMAL,
        reason_codes=("low_confidence",),
        review_task_id="task_001",
        row_version="0000000000000001",
        selected_account_id="acct_123",
        status=PacketStatus.AWAITING_REVIEW,
        updated_at_utc=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
    )
    review_tasks: tuple[ReviewTaskRecord, ...] = ()
    if include_review_task:
        review_tasks = (review_task,)
    extraction_result = ExtractionResultRecord(
        created_at_utc=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
        document_id=document.document_id,
        document_type="bank_statement",
        extraction_result_id="ext_001",
        model_name="gpt4o",
        packet_id=packet.packet_id,
        prompt_profile_id=PromptProfileId.BANK_STATEMENT,
        provider="azure_openai",
        result_payload={
            "extractedFields": [
                {
                    "confidence": 0.94,
                    "name": "account_number",
                    "value": "1234",
                }
            ]
        },
        summary="Extracted summary.",
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
        created_at_utc=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
        document_id=document.document_id,
        match_run_id="match_001",
        packet_id=packet.packet_id,
        rationale="Matched to the hinted account.",
        selected_account_id="acct_123",
        status=AccountMatchStatus.MATCHED,
    )
    processing_jobs = (
        ProcessingJobRecord(
            attempt_number=1,
            completed_at_utc=datetime(2026, 4, 10, 13, 2, tzinfo=UTC),
            created_at_utc=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
            document_id=document.document_id,
            error_code=None,
            error_message=None,
            job_id="job_ext_001",
            packet_id=packet.packet_id,
            queued_at_utc=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
            stage_name=ProcessingStageName.EXTRACTION,
            started_at_utc=datetime(2026, 4, 10, 13, 1, tzinfo=UTC),
            status=ProcessingJobStatus.SUCCEEDED,
            updated_at_utc=datetime(2026, 4, 10, 13, 2, tzinfo=UTC),
        ),
    )
    review_decisions = ()
    if with_existing_decision and include_review_task:
        review_decisions = (
            ReviewDecisionRecord(
                decision_id="decision_existing",
                review_task_id=review_task.review_task_id,
                packet_id=packet.packet_id,
                document_id=document.document_id,
                decision_status=ReviewStatus.APPROVED,
                decision_reason_code=None,
                selected_account_id="acct_123",
                review_notes=None,
                decided_by_user_id=None,
                decided_by_email="reviewer@example.com",
                decided_at_utc=datetime(2026, 4, 10, 13, 5, tzinfo=UTC),
            ),
        )

    return PacketWorkspaceSnapshot(
        packet=packet,
        documents=(document,),
        document_assets=(),
        packet_events=(),
        processing_jobs=processing_jobs,
        ocr_results=(),
        extraction_results=(extraction_result,),
        classification_results=(),
        account_match_runs=(account_match_run,),
        review_tasks=review_tasks,
        review_decisions=review_decisions,
        operator_notes=(),
        audit_events=(),
        recommendation_runs=(),
        recommendation_results=(),
    )


def test_create_packet_review_task_persists_review_task_and_records_audit_event(
    monkeypatch: MonkeyPatch,
) -> None:
    """Creating a review task should persist the task, state updates, and audit trail."""

    connection = FakeConnection()
    snapshot = build_snapshot(
        document_status=PacketStatus.READY_FOR_RECOMMENDATION,
        include_review_task=False,
        packet_status=PacketStatus.READY_FOR_RECOMMENDATION,
    )

    class FakeRepository:
        """Repository stub that returns one packet snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot(self, packet_id: str) -> PacketWorkspaceSnapshot:
            assert packet_id == "pkt_archive_001"
            return snapshot

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        assert autocommit is False
        assert connection_string == build_settings().sql_connection_string
        yield connection

    monkeypatch.setattr(packet_review, "SqlOperatorStateRepository", FakeRepository)
    monkeypatch.setattr(packet_review, "open_sql_connection", fake_open_sql_connection)

    response = packet_review.create_packet_review_task(
        "pkt_archive_001",
        "doc_child_001",
        PacketReviewTaskCreateRequest(
            assigned_user_email="qa.reviewer@example.com",
            created_by_email="lead.reviewer@example.com",
            notes_summary="Manual follow-up requested from the protected review tab.",
            selected_account_id="acct_123",
        ),
        build_settings(),
    )

    assert response.packet_id == "pkt_archive_001"
    assert response.document_id == "doc_child_001"
    assert response.review_task_id.startswith("task_")
    assert connection.committed is True

    review_task_insert = next(
        statement
        for statement in connection.executed_statements
        if statement[0].startswith("INSERT INTO dbo.ReviewTasks")
    )
    assert review_task_insert[1] == (
        response.review_task_id,
        "pkt_archive_001",
        "doc_child_001",
        None,
        "qa.reviewer@example.com",
        PacketStatus.AWAITING_REVIEW.value,
        ReviewTaskPriority.NORMAL.value,
        "acct_123",
        json.dumps([]),
        "Manual follow-up requested from the protected review tab.",
    )
    assert (
        "UPDATE dbo.PacketDocuments SET status = %s, updatedAtUtc = SYSUTCDATETIME() WHERE documentId = %s",
        (PacketStatus.AWAITING_REVIEW.value, "doc_child_001"),
    ) in connection.executed_statements
    assert (
        "UPDATE dbo.Packets SET status = %s, updatedAtUtc = SYSUTCDATETIME() WHERE packetId = %s",
        (PacketStatus.AWAITING_REVIEW.value, "pkt_archive_001"),
    ) in connection.executed_statements
    assert any(
        statement[0].startswith("INSERT INTO dbo.PacketEvents")
        and statement[1] is not None
        and statement[1][2] == "document.review_task.created"
        for statement in connection.executed_statements
    )
    audit_insert = next(
        statement
        for statement in connection.executed_statements
        if statement[0].startswith("INSERT INTO dbo.AuditEvents")
    )
    assert audit_insert[1] is not None
    assert audit_insert[1][5] == "review.task.created"
    assert "q***@example.com" in str(audit_insert[1][6])


def test_apply_packet_review_decision_queues_recommendation(
    monkeypatch: MonkeyPatch,
) -> None:
    """Approving an extraction-backed task should ready the packet for recommendation."""

    connection = FakeConnection()
    snapshot = build_snapshot()

    class FakeRepository:
        """Repository stub that returns one packet snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot_for_review_task(
            self,
            review_task_id: str,
        ) -> PacketWorkspaceSnapshot:
            assert review_task_id == "task_001"
            return snapshot

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(packet_review, "SqlOperatorStateRepository", FakeRepository)
    monkeypatch.setattr(packet_review, "open_sql_connection", fake_open_sql_connection)

    response = packet_review.apply_packet_review_decision(
        "task_001",
        PacketReviewDecisionRequest(
            decision_status=ReviewStatus.APPROVED,
            decided_by_email="reviewer@example.com",
            expected_row_version="0000000000000001",
            review_notes=(
                "Looks consistent. Contact owner@example.com about 4111 1111 1111 1111."
            ),
            selected_account_id="acct_123",
        ),
        build_settings(),
    )

    assert response.packet_status == PacketStatus.READY_FOR_RECOMMENDATION
    assert response.review_task_status == PacketStatus.READY_FOR_RECOMMENDATION
    assert response.document_status == PacketStatus.READY_FOR_RECOMMENDATION
    assert response.queued_recommendation_job_id is not None
    assert response.operator_note is not None
    assert response.operator_note.note_text == (
        "Looks consistent. Contact o***@example.com about xxxx xxxx xxxx 1111."
    )
    assert connection.committed is True
    assert connection.rolled_back is False
    assert any(
        "INSERT INTO dbo.ReviewDecisions" in statement[0]
        for statement in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.OperatorNotes" in statement[0]
        for statement in connection.executed_statements
    )
    assert any(
        "INSERT INTO dbo.ProcessingJobs" in statement[0]
        and statement[1] is not None
        and statement[1][3] == "recommendation"
        for statement in connection.executed_statements
    )
    operator_note_insert = next(
        params
        for statement, params in connection.executed_statements
        if "INSERT INTO dbo.OperatorNotes" in statement
    )
    assert operator_note_insert is not None
    assert operator_note_insert[6] == response.operator_note.note_text
    audit_insert = next(
        params
        for statement, params in connection.executed_statements
        if "INSERT INTO dbo.AuditEvents" in statement
    )
    assert audit_insert is not None
    audit_payload = json.loads(str(audit_insert[6]))
    assert audit_payload["contentControls"]["retentionClass"] == "review_history"
    assert "reviewNotes" in audit_payload["contentControls"]["maskedFields"]


def test_apply_packet_review_assignment_reassigns_task_and_records_audit_event(
    monkeypatch: MonkeyPatch,
) -> None:
    """Review-task reassignment should update SQL ownership and audit history."""

    connection = FakeConnection()
    snapshot = build_snapshot()

    class FakeRepository:
        """Repository stub that returns one packet snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot_for_review_task(
            self,
            review_task_id: str,
        ) -> PacketWorkspaceSnapshot:
            assert review_task_id == "task_001"
            return snapshot

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(packet_review, "SqlOperatorStateRepository", FakeRepository)
    monkeypatch.setattr(packet_review, "open_sql_connection", fake_open_sql_connection)

    response = packet_review.apply_packet_review_assignment(
        "task_001",
        PacketReviewAssignmentRequest(
            assigned_by_email="lead.reviewer@example.com",
            assigned_user_email="qa.reviewer@example.com",
            expected_row_version="0000000000000001",
        ),
        build_settings(),
    )

    assert response.review_task_id == "task_001"
    assert response.packet_id == snapshot.packet.packet_id
    assert response.assigned_user_email == "qa.reviewer@example.com"
    review_task_update = next(
        params
        for statement, params in connection.executed_statements
        if statement.startswith("UPDATE dbo.ReviewTasks")
    )
    assert review_task_update == (
        None,
        "qa.reviewer@example.com",
        "task_001",
        "awaiting_review",
        bytes.fromhex("0000000000000001"),
    )
    assert any(
        "INSERT INTO dbo.PacketEvents" in statement
        for statement, _ in connection.executed_statements
    )
    audit_insert = next(
        params
        for statement, params in connection.executed_statements
        if "INSERT INTO dbo.AuditEvents" in statement
    )
    assert audit_insert is not None
    audit_payload = json.loads(str(audit_insert[6]))
    assert audit_payload["assignedUserEmail"] == "q***@example.com"
    assert audit_payload["assignedUserId"] is None
    assert audit_payload["previousAssignedUserEmail"] == "r***@example.com"
    assert audit_payload["previousAssignedUserId"] is None
    assert audit_payload["reviewTaskId"] == "task_001"
    assert audit_payload["contentControls"]["retentionClass"] == "review_history"


def test_apply_packet_review_decision_blocks_repeat_decisions(
    monkeypatch: MonkeyPatch,
) -> None:
    """A review task with an existing decision should reject duplicate mutations."""

    snapshot = build_snapshot(with_existing_decision=True)

    class FakeRepository:
        """Repository stub that returns a decided review-task snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot_for_review_task(
            self,
            review_task_id: str,
        ) -> PacketWorkspaceSnapshot:
            assert review_task_id == "task_001"
            return snapshot

    monkeypatch.setattr(packet_review, "SqlOperatorStateRepository", FakeRepository)

    with raises(RuntimeError, match="already has a recorded decision"):
        packet_review.apply_packet_review_decision(
            "task_001",
            PacketReviewDecisionRequest(
                decision_status=ReviewStatus.APPROVED,
                decided_by_email="reviewer@example.com",
                expected_row_version="0000000000000001",
            ),
            build_settings(),
        )


def test_apply_packet_review_decision_rejects_stale_row_version(
    monkeypatch: MonkeyPatch,
) -> None:
    """A stale client row version should be rejected before any write begins."""

    snapshot = build_snapshot()

    class FakeRepository:
        """Repository stub that returns one packet snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot_for_review_task(
            self,
            review_task_id: str,
        ) -> PacketWorkspaceSnapshot:
            assert review_task_id == "task_001"
            return snapshot

    monkeypatch.setattr(packet_review, "SqlOperatorStateRepository", FakeRepository)

    with raises(RuntimeError, match="changed after it was loaded"):
        packet_review.apply_packet_review_decision(
            "task_001",
            PacketReviewDecisionRequest(
                decision_status=ReviewStatus.APPROVED,
                decided_by_email="reviewer@example.com",
                expected_row_version="0000000000000002",
            ),
            build_settings(),
        )


def test_apply_packet_review_decision_rejects_other_operator_assignment(
    monkeypatch: MonkeyPatch,
) -> None:
    """A task assigned to another reviewer should reject the decision."""

    snapshot = build_snapshot()

    class FakeRepository:
        """Repository stub that returns one packet snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot_for_review_task(
            self,
            review_task_id: str,
        ) -> PacketWorkspaceSnapshot:
            assert review_task_id == "task_001"
            return snapshot

    monkeypatch.setattr(packet_review, "SqlOperatorStateRepository", FakeRepository)

    with raises(
        RuntimeError,
        match="assigned to reviewer@example.com, not qa.reviewer@example.com",
    ):
        packet_review.apply_packet_review_decision(
            "task_001",
            PacketReviewDecisionRequest(
                decision_status=ReviewStatus.APPROVED,
                decided_by_email="qa.reviewer@example.com",
                expected_row_version="0000000000000001",
            ),
            build_settings(),
        )


def test_apply_packet_review_decision_rejects_concurrent_update_during_write(
    monkeypatch: MonkeyPatch,
) -> None:
    """A concurrent update detected by the SQL row version should roll back."""

    connection = FakeConnection(review_task_update_rowcount=0)
    snapshot = build_snapshot()

    class FakeRepository:
        """Repository stub that returns one packet snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot_for_review_task(
            self,
            review_task_id: str,
        ) -> PacketWorkspaceSnapshot:
            assert review_task_id == "task_001"
            return snapshot

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(packet_review, "SqlOperatorStateRepository", FakeRepository)
    monkeypatch.setattr(packet_review, "open_sql_connection", fake_open_sql_connection)

    with raises(RuntimeError, match="changed while this decision was being recorded"):
        packet_review.apply_packet_review_decision(
            "task_001",
            PacketReviewDecisionRequest(
                decision_status=ReviewStatus.APPROVED,
                decided_by_email="reviewer@example.com",
                expected_row_version="0000000000000001",
            ),
            build_settings(),
        )

    assert connection.committed is False
    assert connection.rolled_back is True


def test_apply_packet_review_extraction_edits_persists_new_result_and_audit_event(
    monkeypatch: MonkeyPatch,
) -> None:
    """Saving extraction edits should create a new extraction result and audit trail."""

    connection = FakeConnection()
    snapshot = build_snapshot()

    class FakeRepository:
        """Repository stub that returns one packet snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot_for_review_task(
            self,
            review_task_id: str,
        ) -> PacketWorkspaceSnapshot:
            assert review_task_id == "task_001"
            return snapshot

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(packet_review, "SqlOperatorStateRepository", FakeRepository)
    monkeypatch.setattr(packet_review, "open_sql_connection", fake_open_sql_connection)

    response = packet_review.apply_packet_review_extraction_edits(
        "task_001",
        PacketReviewExtractionEditRequest(
            edited_by_email="reviewer@example.com",
            expected_row_version="0000000000000001",
            field_edits=(
                ExtractionFieldEditInput(
                    field_name="account_number",
                    value="5678",
                ),
            ),
        ),
        build_settings(),
    )

    assert response.review_task_id == "task_001"
    assert response.changed_fields[0].field_name == "account_number"
    assert response.changed_fields[0].original_value == "1234"
    assert response.changed_fields[0].current_value == "5678"
    assert response.extraction_result.extraction_result_id != "ext_001"
    extracted_fields = response.extraction_result.result_payload["extractedFields"]
    assert extracted_fields[0]["value"] == "5678"
    assert response.extraction_result.result_payload["reviewEdits"]["changeCount"] == 1
    assert connection.committed is True
    assert connection.rolled_back is False
    assert any(
        "INSERT INTO dbo.ExtractionResults" in statement[0]
        for statement in connection.executed_statements
    )
    extraction_insert = next(
        params
        for statement, params in connection.executed_statements
        if "INSERT INTO dbo.ExtractionResults" in statement
    )
    assert extraction_insert is not None
    assert '"reviewEdits"' in str(extraction_insert[8])
    assert '"5678"' in str(extraction_insert[8])
    assert any(
        "document.extraction.fields.updated" in str(statement[1])
        for statement in connection.executed_statements
        if statement[1] is not None
    )
    audit_insert = next(
        params
        for statement, params in connection.executed_statements
        if "INSERT INTO dbo.AuditEvents" in statement
    )
    assert audit_insert is not None
    audit_payload = json.loads(str(audit_insert[6]))
    assert audit_payload["contentControls"]["retentionClass"] == "review_history"


def test_apply_packet_review_note_persists_masked_note_and_audit_event(
    monkeypatch: MonkeyPatch,
) -> None:
    """Saving a review-task note should persist masked note history and audit state."""

    connection = FakeConnection()
    snapshot = build_snapshot()

    class FakeRepository:
        """Repository stub that returns one packet snapshot."""

        def __init__(self, settings: AppSettings) -> None:
            del settings

        def is_configured(self) -> bool:
            return True

        def get_packet_workspace_snapshot_for_review_task(
            self,
            review_task_id: str,
        ) -> PacketWorkspaceSnapshot:
            assert review_task_id == "task_001"
            return snapshot

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(packet_review, "SqlOperatorStateRepository", FakeRepository)
    monkeypatch.setattr(packet_review, "open_sql_connection", fake_open_sql_connection)

    response = packet_review.apply_packet_review_note(
        "task_001",
        PacketReviewNoteRequest(
            created_by_email="reviewer@example.com",
            expected_row_version="0000000000000001",
            note_text=(
                "Follow up with owner@example.com about card 4111 1111 1111 1111."
            ),
        ),
        build_settings(),
    )

    assert response.review_task_id == "task_001"
    assert response.packet_id == "pkt_archive_001"
    assert response.operator_note.note_text == (
        "Follow up with o***@example.com about card xxxx xxxx xxxx 1111."
    )
    assert connection.committed is True
    assert connection.rolled_back is False
    operator_note_insert = next(
        params
        for statement, params in connection.executed_statements
        if "INSERT INTO dbo.OperatorNotes" in statement
    )
    assert operator_note_insert is not None
    assert operator_note_insert[6] == response.operator_note.note_text
    review_task_update = next(
        params
        for statement, params in connection.executed_statements
        if statement.startswith("UPDATE dbo.ReviewTasks")
    )
    assert review_task_update is not None
    assert review_task_update[0] == response.operator_note.note_text
    audit_insert = next(
        params
        for statement, params in connection.executed_statements
        if "INSERT INTO dbo.AuditEvents" in statement
    )
    assert audit_insert is not None
    audit_payload = json.loads(str(audit_insert[6]))
    assert audit_payload["contentControls"]["retentionClass"] == "review_history"
    assert "noteText" in audit_payload["contentControls"]["maskedFields"]