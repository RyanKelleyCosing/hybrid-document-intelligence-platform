"""Shared Azure SQL connection helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import certifi
import pytds  # type: ignore[import-untyped]


@dataclass(frozen=True)
class SqlConnectionConfig:
    """Normalized connection settings extracted from a SQL connection string."""

    database_name: str
    password: str
    port: int
    server_name: str
    user_name: str


def resolve_sql_cafile() -> str:
    """Return the CA bundle path used for Azure SQL TLS validation."""

    return certifi.where()


def parse_connection_string(connection_string: str) -> dict[str, str]:
    """Parse a semicolon-delimited SQL connection string into a dictionary."""
    connection_values: dict[str, str] = {}
    for segment in connection_string.split(";"):
        if not segment or "=" not in segment:
            continue
        key, value = segment.split("=", maxsplit=1)
        connection_values[key.strip().lower()] = value.strip()
    return connection_values


def build_sql_connection_config(connection_string: str) -> SqlConnectionConfig:
    """Build a typed SQL connection config from an environment string."""
    connection_values = parse_connection_string(connection_string)
    server_name = (
        connection_values.get("server")
        or connection_values.get("data source")
        or connection_values.get("address")
    )
    database_name = (
        connection_values.get("database")
        or connection_values.get("initial catalog")
    )
    user_name = (
        connection_values.get("uid")
        or connection_values.get("user id")
        or connection_values.get("user")
    )
    password = connection_values.get("pwd") or connection_values.get("password")

    if not server_name or not database_name or not user_name or not password:
        raise ValueError("DOCINT_SQL_CONNECTION_STRING is missing required values")

    normalized_server_name = server_name.removeprefix("tcp:")
    port = 1433
    if "," in normalized_server_name:
        host_name, port_value = normalized_server_name.rsplit(",", maxsplit=1)
        normalized_server_name = host_name
        port = int(port_value)

    return SqlConnectionConfig(
        database_name=database_name,
        password=password,
        port=port,
        server_name=normalized_server_name,
        user_name=user_name,
    )


@contextmanager
def open_sql_connection(
    connection_string: str,
    *,
    autocommit: bool,
) -> Iterator[Any]:
    """Open a pytds connection from the supplied connection string."""
    config = build_sql_connection_config(connection_string)
    with pytds.connect(
        dsn=config.server_name,
        port=config.port,
        database=config.database_name,
        user=config.user_name,
        password=config.password,
        autocommit=autocommit,
        cafile=resolve_sql_cafile(),
        validate_host=True,
    ) as connection:
        yield connection