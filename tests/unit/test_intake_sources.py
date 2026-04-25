"""Unit tests for durable intake-source models and SQL persistence."""

from __future__ import annotations

from collections.abc import Iterator
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from types import TracebackType

from pytest import MonkeyPatch

import document_intelligence.persistence as persistence
from document_intelligence.models import (
    IntakeSourceCreateRequest,
    IntakeSourceEnablementRequest,
    IntakeSourceKind,
    IntakeSourceUpdateRequest,
    PartnerApiFeedSourceConfiguration,
    WatchedBlobPrefixSourceConfiguration,
    validate_intake_source_configuration,
)
from document_intelligence.settings import AppSettings


def build_settings(**overrides: object) -> AppSettings:
    """Build app settings for intake-source repository tests."""

    values: dict[str, object] = {
        "sql_connection_string": (
            "Server=tcp:test-sql.database.windows.net,1433;"
            "Database=docintel;User ID=docintel;Password=Password123!"
        )
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


class FakeIntakeSourceCursor:
    """Minimal DB-API cursor stub for intake-source repository tests."""

    def __init__(self, connection: FakeIntakeSourceConnection) -> None:
        self._connection = connection
        self._rows: list[tuple[object, ...]] = []

    def __enter__(self) -> FakeIntakeSourceCursor:
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
        if normalized_statement.startswith("SELECT sourceId,"):
            self._rows = list(self._connection.rows)
            return

        self._rows = []

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)

    def fetchone(self) -> tuple[object, ...] | None:
        if not self._rows:
            return None

        return self._rows[0]


class FakeIntakeSourceConnection:
    """Minimal DB-API connection stub for intake-source repository tests."""

    def __init__(self, rows: list[tuple[object, ...]] | None = None) -> None:
        self.rows = rows or []
        self.executed_statements: list[tuple[str, tuple[object, ...] | None]] = []
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> FakeIntakeSourceCursor:
        return FakeIntakeSourceCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_validate_intake_source_configuration_uses_discriminator() -> None:
    """The source-kind discriminator should hydrate the correct config model."""

    configuration = validate_intake_source_configuration(
        {
            "source_kind": "watched_blob_prefix",
            "storage_account_name": "stdocdev123",
            "container_name": "raw-documents",
            "blob_prefix": "ops/inbox/",
        }
    )

    assert isinstance(configuration, WatchedBlobPrefixSourceConfiguration)
    assert configuration.source_kind == IntakeSourceKind.WATCHED_BLOB_PREFIX


def test_sql_intake_source_repository_lists_sources(
    monkeypatch: MonkeyPatch,
) -> None:
    """The repository should hydrate intake-source rows from SQL."""

    connection = FakeIntakeSourceConnection(
        rows=[
            (
                "src_ops_blob",
                "Ops blob watcher",
                "Primary blob watcher",
                True,
                "ops@example.com",
                5,
                "kv://storage/ops-watcher",
                "watched_blob_prefix",
                json.dumps(
                    {
                        "source_kind": "watched_blob_prefix",
                        "storage_account_name": "stdocdev123",
                        "container_name": "raw-documents",
                        "blob_prefix": "ops/inbox/",
                    }
                ),
                None,
                datetime(2026, 4, 5, 11, 30, tzinfo=UTC),
                None,
                None,
                datetime(2026, 4, 5, 10, 0, tzinfo=UTC),
                datetime(2026, 4, 5, 11, 30, tzinfo=UTC),
            )
        ]
    )

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeIntakeSourceConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(persistence, "open_sql_connection", fake_open_sql_connection)

    repository = persistence.SqlIntakeSourceRepository(build_settings())
    response = repository.list_intake_sources()

    assert response.items[0].source_id == "src_ops_blob"
    assert response.items[0].configuration.source_kind == (
        IntakeSourceKind.WATCHED_BLOB_PREFIX
    )
    assert response.items[0].last_success_at_utc == datetime(
        2026,
        4,
        5,
        11,
        30,
        tzinfo=UTC,
    )


def test_sql_intake_source_repository_creates_source(
    monkeypatch: MonkeyPatch,
) -> None:
    """The repository should insert durable intake-source definitions."""

    connection = FakeIntakeSourceConnection()

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeIntakeSourceConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(persistence, "open_sql_connection", fake_open_sql_connection)

    repository = persistence.SqlIntakeSourceRepository(build_settings())
    record = repository.create_intake_source(
        IntakeSourceCreateRequest(
            source_name="County referrals",
            description="Inbound partner referral webhook",
            owner_email="ops@example.com",
            credentials_reference="kv://partner/referrals",
            configuration=PartnerApiFeedSourceConfiguration(
                partner_name="County court partner",
                relative_path="/api/intake/partner-referrals/v1",
                auth_scheme="hmac",
            ),
        )
    )

    assert record.source_id.startswith("src_")
    assert record.configuration.source_kind == IntakeSourceKind.PARTNER_API_FEED
    assert connection.committed is True
    assert connection.rolled_back is False

    statement, params = connection.executed_statements[0]
    assert "INSERT INTO dbo.IntakeSources" in statement
    assert params is not None
    assert params[1] == "County referrals"
    assert params[2] == "partner_api_feed"
    assert json.loads(str(params[8]))["partner_name"] == "County court partner"


def test_sql_intake_source_repository_gets_one_source(
    monkeypatch: MonkeyPatch,
) -> None:
    """The repository should hydrate a single intake-source row by id."""

    connection = FakeIntakeSourceConnection(
        rows=[
            (
                "src_ops_blob",
                "Ops blob watcher",
                "Primary blob watcher",
                True,
                "ops@example.com",
                5,
                "kv://storage/ops-watcher",
                "watched_blob_prefix",
                json.dumps(
                    {
                        "source_kind": "watched_blob_prefix",
                        "storage_account_name": "stdocdev123",
                        "container_name": "raw-documents",
                        "blob_prefix": "ops/inbox/",
                    }
                ),
                datetime(2026, 4, 7, 8, 0, tzinfo=UTC),
                datetime(2026, 4, 7, 8, 5, tzinfo=UTC),
                None,
                None,
                datetime(2026, 4, 5, 10, 0, tzinfo=UTC),
                datetime(2026, 4, 7, 8, 5, tzinfo=UTC),
            )
        ]
    )

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeIntakeSourceConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(persistence, "open_sql_connection", fake_open_sql_connection)

    repository = persistence.SqlIntakeSourceRepository(build_settings())
    record = repository.get_intake_source("src_ops_blob")

    assert record.source_id == "src_ops_blob"
    assert record.last_seen_at_utc == datetime(2026, 4, 7, 8, 0, tzinfo=UTC)
    assert record.last_success_at_utc == datetime(2026, 4, 7, 8, 5, tzinfo=UTC)


def test_sql_intake_source_repository_updates_source(
    monkeypatch: MonkeyPatch,
) -> None:
    """The repository should replace a durable intake-source definition."""

    connection = FakeIntakeSourceConnection(
        rows=[
            (
                "src_ops_blob",
                "Ops blob watcher",
                "Primary blob watcher",
                True,
                "ops@example.com",
                5,
                "kv://storage/ops-watcher",
                "watched_blob_prefix",
                json.dumps(
                    {
                        "source_kind": "watched_blob_prefix",
                        "storage_account_name": "stdocdev123",
                        "container_name": "raw-documents",
                        "blob_prefix": "ops/inbox/",
                    }
                ),
                None,
                datetime(2026, 4, 7, 8, 5, tzinfo=UTC),
                None,
                None,
                datetime(2026, 4, 5, 10, 0, tzinfo=UTC),
                datetime(2026, 4, 7, 8, 5, tzinfo=UTC),
            )
        ]
    )

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeIntakeSourceConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(persistence, "open_sql_connection", fake_open_sql_connection)

    repository = persistence.SqlIntakeSourceRepository(build_settings())
    record = repository.update_intake_source(
        "src_ops_blob",
        IntakeSourceUpdateRequest(
            source_name="Ops blob watcher",
            description="Updated watcher",
            owner_email="ops@example.com",
            polling_interval_minutes=10,
            configuration=WatchedBlobPrefixSourceConfiguration(
                storage_account_name="stdocdev123",
                container_name="raw-documents",
                blob_prefix="ops/updated/",
            ),
        ),
    )

    assert record.source_id == "src_ops_blob"
    assert record.description == "Updated watcher"
    assert record.polling_interval_minutes == 10
    assert connection.committed is True
    statement, params = connection.executed_statements[1]
    assert "UPDATE dbo.IntakeSources" in statement
    assert params is not None
    assert params[0] == "Ops blob watcher"
    assert params[2] == "Updated watcher"
    assert json.loads(str(params[7]))["blob_prefix"] == "ops/updated/"


def test_sql_intake_source_repository_sets_enablement(
    monkeypatch: MonkeyPatch,
) -> None:
    """The repository should pause or resume one intake-source definition."""

    connection = FakeIntakeSourceConnection(
        rows=[
            (
                "src_ops_blob",
                "Ops blob watcher",
                "Primary blob watcher",
                True,
                "ops@example.com",
                5,
                "kv://storage/ops-watcher",
                "watched_blob_prefix",
                json.dumps(
                    {
                        "source_kind": "watched_blob_prefix",
                        "storage_account_name": "stdocdev123",
                        "container_name": "raw-documents",
                        "blob_prefix": "ops/inbox/",
                    }
                ),
                None,
                datetime(2026, 4, 7, 8, 5, tzinfo=UTC),
                None,
                None,
                datetime(2026, 4, 5, 10, 0, tzinfo=UTC),
                datetime(2026, 4, 7, 8, 5, tzinfo=UTC),
            )
        ]
    )

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeIntakeSourceConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(persistence, "open_sql_connection", fake_open_sql_connection)

    repository = persistence.SqlIntakeSourceRepository(build_settings())
    record = repository.set_intake_source_enablement(
        "src_ops_blob",
        IntakeSourceEnablementRequest(is_enabled=False),
    )

    assert record.source_id == "src_ops_blob"
    assert record.is_enabled is False
    assert connection.committed is True
    statement, params = connection.executed_statements[1]
    assert "UPDATE dbo.IntakeSources" in statement
    assert params is not None
    assert params[0] is False
    assert params[2] == "src_ops_blob"


def test_sql_intake_source_repository_deletes_source(
    monkeypatch: MonkeyPatch,
) -> None:
    """The repository should delete one durable intake-source definition."""

    connection = FakeIntakeSourceConnection(
        rows=[
            (
                "src_ops_blob",
                "Ops blob watcher",
                "Primary blob watcher",
                True,
                "ops@example.com",
                5,
                "kv://storage/ops-watcher",
                "watched_blob_prefix",
                json.dumps(
                    {
                        "source_kind": "watched_blob_prefix",
                        "storage_account_name": "stdocdev123",
                        "container_name": "raw-documents",
                        "blob_prefix": "ops/inbox/",
                    }
                ),
                None,
                datetime(2026, 4, 7, 8, 5, tzinfo=UTC),
                None,
                None,
                datetime(2026, 4, 5, 10, 0, tzinfo=UTC),
                datetime(2026, 4, 7, 8, 5, tzinfo=UTC),
            )
        ]
    )

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeIntakeSourceConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(persistence, "open_sql_connection", fake_open_sql_connection)

    repository = persistence.SqlIntakeSourceRepository(build_settings())
    response = repository.delete_intake_source("src_ops_blob")

    assert response.deleted is True
    assert response.source_id == "src_ops_blob"
    assert response.source_name == "Ops blob watcher"
    assert connection.committed is True
    statement, params = connection.executed_statements[1]
    assert "DELETE FROM dbo.IntakeSources" in statement
    assert params == ("src_ops_blob",)


def test_sql_intake_source_repository_records_execution_state(
    monkeypatch: MonkeyPatch,
) -> None:
    """The repository should persist last-seen, success, and error state."""

    connection = FakeIntakeSourceConnection()

    @contextmanager
    def fake_open_sql_connection(
        connection_string: str,
        *,
        autocommit: bool,
    ) -> Iterator[FakeIntakeSourceConnection]:
        del connection_string, autocommit
        yield connection

    monkeypatch.setattr(persistence, "open_sql_connection", fake_open_sql_connection)

    repository = persistence.SqlIntakeSourceRepository(build_settings())
    executed_at_utc = datetime(2026, 4, 7, 9, 0, tzinfo=UTC)
    repository.record_intake_source_execution(
        "src_ops_blob",
        last_error_message="ops/inbox/broken.pdf: download failed",
        last_seen_at_utc=executed_at_utc,
        last_success_at_utc=executed_at_utc,
    )

    assert connection.committed is True
    assert connection.rolled_back is False
    statement, params = connection.executed_statements[0]
    assert "UPDATE dbo.IntakeSources" in statement
    assert params is not None
    assert params[0] == executed_at_utc
    assert params[1] == executed_at_utc
    assert params[2] == executed_at_utc
    assert params[3] == "ops/inbox/broken.pdf: download failed"
    assert params[5] == "src_ops_blob"