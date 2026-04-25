"""Unit tests for shared Azure SQL connection helpers."""

from __future__ import annotations

from contextlib import contextmanager

from pytest import MonkeyPatch

from document_intelligence.utils import sql


def test_build_sql_connection_config_parses_tcp_host_and_port() -> None:
    """Connection strings should normalize the server host and explicit port."""

    config = sql.build_sql_connection_config(
        "Server=tcp:sql-doc-test.database.windows.net,1433;"
        "Initial Catalog=docintel;"
        "User ID=docinteladmin;"
        "Password=Password123!;"
    )

    assert config.server_name == "sql-doc-test.database.windows.net"
    assert config.port == 1433
    assert config.database_name == "docintel"
    assert config.user_name == "docinteladmin"


def test_open_sql_connection_enables_tls(monkeypatch: MonkeyPatch) -> None:
    """Azure SQL connections should pass a CA bundle into python-tds."""

    captured: dict[str, object] = {}

    @contextmanager
    def fake_connect(**kwargs):
        captured.update(kwargs)
        yield "fake-connection"

    monkeypatch.setattr(sql.certifi, "where", lambda: "C:/certifi/cacert.pem")
    monkeypatch.setattr(sql.pytds, "connect", fake_connect)

    with sql.open_sql_connection(
        "Server=tcp:sql-doc-test.database.windows.net,1433;"
        "Initial Catalog=docintel;"
        "User ID=docinteladmin;"
        "Password=Password123!;",
        autocommit=True,
    ) as connection:
        assert connection == "fake-connection"

    assert captured["dsn"] == "sql-doc-test.database.windows.net"
    assert captured["port"] == 1433
    assert captured["database"] == "docintel"
    assert captured["user"] == "docinteladmin"
    assert captured["password"] == "Password123!"
    assert captured["autocommit"] is True
    assert captured["cafile"] == "C:/certifi/cacert.pem"
    assert captured["validate_host"] is True