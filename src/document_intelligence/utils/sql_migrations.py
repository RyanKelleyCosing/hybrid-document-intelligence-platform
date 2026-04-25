"""Helpers for repeatable Azure SQL schema migrations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from document_intelligence.utils.sql import open_sql_connection

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SQL_MIGRATION_MANIFEST = Path("scripts/sql-migrations.json")
_SCHEMA_MIGRATIONS_TABLE_SQL = """
IF OBJECT_ID(N'dbo.SchemaMigrations', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SchemaMigrations (
        migrationId NVARCHAR(128) NOT NULL,
        description NVARCHAR(400) NOT NULL,
        scriptPath NVARCHAR(400) NOT NULL,
        scriptChecksum CHAR(64) NOT NULL,
        appliedAtUtc DATETIME2 NOT NULL
            CONSTRAINT DF_SchemaMigrations_AppliedAtUtc
            DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_SchemaMigrations PRIMARY KEY CLUSTERED (migrationId)
    );
END;
"""


@dataclass(frozen=True)
class SqlMigration:
    """Metadata and SQL content for one ordered schema migration."""

    migration_id: str
    description: str
    script_checksum: str
    script_path: Path
    script_path_display: str
    script_text: str


@dataclass(frozen=True)
class SqlMigrationApplyResult:
    """Summary of which SQL migrations were applied or skipped."""

    applied_migration_ids: tuple[str, ...]
    skipped_migration_ids: tuple[str, ...]


def compute_sql_script_checksum(script_bytes: bytes) -> str:
    """Return a stable checksum for a SQL migration script."""
    return hashlib.sha256(script_bytes).hexdigest()


def split_sql_batches(script_text: str) -> tuple[str, ...]:
    """Split a SQL script into batches using sqlcmd-style GO separators."""
    batches: list[str] = []
    current_lines: list[str] = []

    for line in script_text.splitlines():
        if line.strip().upper() == "GO":
            batch = "\n".join(current_lines).strip()
            if batch:
                batches.append(batch)
            current_lines = []
            continue

        current_lines.append(line)

    final_batch = "\n".join(current_lines).strip()
    if final_batch:
        batches.append(final_batch)

    return tuple(batches)


def _coerce_manifest_path(repo_root: Path, manifest_path: Path | None) -> Path:
    """Resolve the manifest path relative to the repository root."""
    candidate_path = manifest_path or DEFAULT_SQL_MIGRATION_MANIFEST
    if candidate_path.is_absolute():
        return candidate_path
    return repo_root / candidate_path


def _require_manifest_string(value: object, *, field_name: str) -> str:
    """Validate a non-empty manifest string field."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"SQL migration manifest field '{field_name}' is required")


def _resolve_repo_script_path(repo_root: Path, relative_path: str) -> Path:
    """Resolve a migration script path and keep it inside the repository."""
    resolved_repo_root = repo_root.resolve()
    resolved_path = (resolved_repo_root / relative_path).resolve()
    try:
        resolved_path.relative_to(resolved_repo_root)
    except ValueError as error:
        raise ValueError(
            f"SQL migration path '{relative_path}' resolves outside the repository"
        ) from error

    if not resolved_path.is_file():
        raise FileNotFoundError(
            f"SQL migration script '{relative_path}' was not found"
        )

    return resolved_path


def load_sql_migrations(
    *,
    manifest_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> tuple[SqlMigration, ...]:
    """Load the ordered SQL migration plan from the manifest file."""
    resolved_manifest_path = _coerce_manifest_path(repo_root, manifest_path)
    manifest_payload = json.loads(resolved_manifest_path.read_text(encoding="utf-8"))
    migration_entries = manifest_payload.get("migrations")
    if not isinstance(migration_entries, list):
        raise ValueError("SQL migration manifest must define a 'migrations' list")

    migrations: list[SqlMigration] = []
    seen_migration_ids: set[str] = set()
    for index, entry in enumerate(migration_entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(
                f"SQL migration manifest entry {index} must be an object"
            )

        migration_id = _require_manifest_string(
            entry.get("id"),
            field_name=f"migrations[{index}].id",
        )
        if migration_id in seen_migration_ids:
            raise ValueError(f"Duplicate SQL migration id '{migration_id}'")

        description = _require_manifest_string(
            entry.get("description"),
            field_name=f"migrations[{index}].description",
        )
        relative_path = _require_manifest_string(
            entry.get("path"),
            field_name=f"migrations[{index}].path",
        )
        script_path = _resolve_repo_script_path(repo_root, relative_path)
        script_bytes = script_path.read_bytes()
        migrations.append(
            SqlMigration(
                migration_id=migration_id,
                description=description,
                script_checksum=compute_sql_script_checksum(script_bytes),
                script_path=script_path,
                script_path_display=relative_path,
                script_text=script_bytes.decode("utf-8"),
            )
        )
        seen_migration_ids.add(migration_id)

    return tuple(migrations)


def ensure_schema_migrations_table(connection: Any) -> None:
    """Create the migration ledger table when it does not already exist."""
    with connection.cursor() as cursor:
        cursor.execute(_SCHEMA_MIGRATIONS_TABLE_SQL)


def load_applied_migration_checksums(connection: Any) -> dict[str, str]:
    """Return previously applied migration ids and their recorded checksums."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT migrationId, scriptChecksum
            FROM dbo.SchemaMigrations
            ORDER BY migrationId ASC
            """
        )
        rows = cursor.fetchall()

    return {str(migration_id): str(checksum) for migration_id, checksum in rows}


def execute_sql_batches(connection: Any, script_text: str) -> None:
    """Execute each SQL batch in order against the open connection."""
    for batch in split_sql_batches(script_text):
        with connection.cursor() as cursor:
            cursor.execute(batch)


def record_applied_migration(connection: Any, migration: SqlMigration) -> None:
    """Persist the successful application of one migration into the ledger."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dbo.SchemaMigrations (
                migrationId,
                description,
                scriptPath,
                scriptChecksum
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                migration.migration_id,
                migration.description,
                migration.script_path_display,
                migration.script_checksum,
            ),
        )


def apply_sql_migrations_to_connection(
    connection: Any,
    migrations: tuple[SqlMigration, ...],
) -> SqlMigrationApplyResult:
    """Apply pending migrations and validate checksums for existing ones."""
    ensure_schema_migrations_table(connection)
    applied_checksums = load_applied_migration_checksums(connection)
    applied_migration_ids: list[str] = []
    skipped_migration_ids: list[str] = []

    for migration in migrations:
        applied_checksum = applied_checksums.get(migration.migration_id)
        if applied_checksum is not None:
            if applied_checksum != migration.script_checksum:
                raise ValueError(
                    "Recorded SQL migration checksum does not match the current "
                    f"script for '{migration.migration_id}'"
                )
            skipped_migration_ids.append(migration.migration_id)
            continue

        execute_sql_batches(connection, migration.script_text)
        record_applied_migration(connection, migration)
        applied_migration_ids.append(migration.migration_id)

    return SqlMigrationApplyResult(
        applied_migration_ids=tuple(applied_migration_ids),
        skipped_migration_ids=tuple(skipped_migration_ids),
    )


def apply_sql_migrations(
    connection_string: str,
    *,
    manifest_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
) -> SqlMigrationApplyResult:
    """Open Azure SQL and apply the configured migration plan."""
    migrations = load_sql_migrations(
        manifest_path=manifest_path,
        repo_root=repo_root,
    )
    with open_sql_connection(connection_string, autocommit=True) as connection:
        return apply_sql_migrations_to_connection(connection, migrations)