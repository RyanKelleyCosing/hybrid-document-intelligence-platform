"""Unit tests for the SQL migration helpers."""

from __future__ import annotations

import json
from pathlib import Path
from types import TracebackType

import pytest

from document_intelligence.utils import sql_migrations
from document_intelligence.utils.sql_migrations import SqlMigration


class FakeCursor:
    """Minimal DB-API style cursor for SQL migration tests."""

    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection
        self._rows: list[tuple[str, str]] = []

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
        self._connection.executed_statements.append((statement.strip(), params))
        normalized_statement = " ".join(statement.split())
        if (
            "SELECT migrationId, scriptChecksum FROM dbo.SchemaMigrations"
            in normalized_statement
        ):
            self._rows = list(self._connection.applied_checksums.items())
            return

        if "INSERT INTO dbo.SchemaMigrations" in normalized_statement:
            if params is None:
                raise AssertionError("Expected SQL migration ledger insert params")
            migration_id = str(params[0])
            checksum = str(params[3])
            self._connection.applied_checksums[migration_id] = checksum
            self._rows = []
            return

        self._rows = []

    def fetchall(self) -> list[tuple[str, str]]:
        return list(self._rows)


class FakeConnection:
    """Minimal DB-API style connection for SQL migration tests."""

    def __init__(self, applied_checksums: dict[str, str] | None = None) -> None:
        self.applied_checksums = applied_checksums or {}
        self.executed_statements: list[tuple[str, tuple[object, ...] | None]] = []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def create_migration(
    *,
    migration_id: str,
    script_path: Path,
    script_text: str,
) -> SqlMigration:
    """Build a SqlMigration instance for tests."""
    script_bytes = script_text.encode("utf-8")
    return SqlMigration(
        migration_id=migration_id,
        description=f"Migration {migration_id}",
        script_checksum=sql_migrations.compute_sql_script_checksum(script_bytes),
        script_path=script_path,
        script_path_display=script_path.as_posix(),
        script_text=script_text,
    )


def test_split_sql_batches_handles_go_separators() -> None:
    """GO lines should split SQL text into independent batches."""
    batches = sql_migrations.split_sql_batches(
        "SELECT 1\nGO\n\nSELECT 2\nGO\nSELECT 3"
    )

    assert batches == ("SELECT 1", "SELECT 2", "SELECT 3")


def test_load_sql_migrations_reads_manifest_and_checksums(tmp_path: Path) -> None:
    """The manifest loader should resolve scripts and compute checksums."""
    manifest_path = tmp_path / "scripts" / "sql-migrations.json"
    script_path = tmp_path / "scripts" / "001_test.sql"
    manifest_path.parent.mkdir(parents=True)
    script_path.write_text("SELECT 1", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "migrations": [
                    {
                        "id": "001_test",
                        "description": "Create a test object.",
                        "path": "scripts/001_test.sql",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    migrations = sql_migrations.load_sql_migrations(
        manifest_path=manifest_path,
        repo_root=tmp_path,
    )

    assert len(migrations) == 1
    assert migrations[0].migration_id == "001_test"
    assert migrations[0].script_path == script_path.resolve()
    assert migrations[0].script_checksum == sql_migrations.compute_sql_script_checksum(
        b"SELECT 1"
    )


def test_apply_sql_migrations_to_connection_skips_and_applies_pending() -> None:
    """Applied migrations should be skipped while pending ones execute."""
    first_migration = create_migration(
        migration_id="001_first",
        script_path=Path("scripts/001_first.sql"),
        script_text="SELECT 1",
    )
    second_migration = create_migration(
        migration_id="002_second",
        script_path=Path("scripts/002_second.sql"),
        script_text="SELECT 2\nGO\nSELECT 3",
    )
    connection = FakeConnection(
        applied_checksums={
            first_migration.migration_id: first_migration.script_checksum,
        }
    )

    result = sql_migrations.apply_sql_migrations_to_connection(
        connection,
        (first_migration, second_migration),
    )

    assert result.applied_migration_ids == ("002_second",)
    assert result.skipped_migration_ids == ("001_first",)
    assert connection.applied_checksums == {
        "001_first": first_migration.script_checksum,
        "002_second": second_migration.script_checksum,
    }
    executed_statements = [statement for statement, _ in connection.executed_statements]
    assert any(
        "CREATE TABLE dbo.SchemaMigrations" in statement
        for statement in executed_statements
    )
    assert any(statement == "SELECT 2" for statement in executed_statements)
    assert any(statement == "SELECT 3" for statement in executed_statements)


def test_apply_sql_migrations_to_connection_rejects_checksum_drift() -> None:
    """A changed script must fail when the ledger contains a different checksum."""
    migration = create_migration(
        migration_id="001_first",
        script_path=Path("scripts/001_first.sql"),
        script_text="SELECT 1",
    )
    connection = FakeConnection(applied_checksums={migration.migration_id: "mismatch"})

    with pytest.raises(ValueError, match="Recorded SQL migration checksum"):
        sql_migrations.apply_sql_migrations_to_connection(connection, (migration,))