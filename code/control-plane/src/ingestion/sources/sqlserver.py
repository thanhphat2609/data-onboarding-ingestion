"""SQL Server: the client behind Test connection and the query preview."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import pymssql

from ingestion.sources.base import (
    LOGIN_TIMEOUT_S,
    QUERY_TIMEOUT_S,
    Preview,
    SourceError,
    TestResult,
    elapsed_ms,
    json_value,
    preview_statement,
    resolve_password,
)
from ingestion.templates import Template, with_defaults


def _sqlserver_message(error: Exception) -> str:
    """Turns a pymssql error (code, b'DB-Lib error message ...') into one readable line."""
    code, raw = (error.args + (None, None))[:2] if error.args else (None, None)
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw or error)
    lines = [line.strip() for line in text.replace("\r", "").split("\n")]
    lines = [line for line in lines if line and not line.startswith("DB-Lib error message")]
    message = " ".join(lines[:2]) or str(error)
    if code == 18456:
        return f"{message} Check the username and the password secret."
    if code in (20009, 20002):
        return f"Cannot reach the server: {message}"
    return message


class SqlServerClient:
    def __init__(self, params: dict[str, Any], template: Template, connect: Callable[..., Any] = pymssql.connect):
        """``connect`` is replaced by a fake in tests; the parameters get the template's defaults."""
        self.params = with_defaults(template.params("connection_params"), params)
        self.template = template
        self._connect_fn = connect

    def _connect(self) -> Any:
        """Opens a read-only pymssql connection with timeouts; SourceError with a readable message."""
        p = self.params
        password = resolve_password(p)
        try:
            return self._connect_fn(
                server=str(p["host"]),
                port=str(p["port"]),
                user=str(p["username"]),
                password=password,
                database=str(p["database"]),
                login_timeout=LOGIN_TIMEOUT_S,
                timeout=QUERY_TIMEOUT_S,
                # FreeTDS encrypts with "require" but doesn't verify the certificate; the JDBC driver used for runs
                # honours trust_server_certificate.
                encryption="require" if p["encrypt"] else "request",
                read_only=True,  # ApplicationIntent=ReadOnly, as in the template URL
                appname="ingestion-api",
                autocommit=True,
            )
        except pymssql.Error as error:
            raise SourceError(_sqlserver_message(error)) from None

    def test(self) -> TestResult:
        """Opens a connection and reports the server and database; warns when the login can write."""
        started = time.monotonic()
        try:
            conn = self._connect()
        except SourceError as error:
            return TestResult(False, str(error))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION, DB_NAME(), HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'INSERT')")
            version, database, can_insert = cursor.fetchone()
        except pymssql.Error as error:
            return TestResult(False, _sqlserver_message(error))
        finally:
            conn.close()
        product = str(version).splitlines()[0].split(" (KB")[0].strip()
        message = f"Connected to {product}, database {database}"
        if can_insert:
            message += f". Warning: this login can write to {database}; use a read-only login"
        return TestResult(True, message, elapsed_ms(started))

    def _describe(self, cursor: Any, query: str) -> list[dict[str, str]] | None:
        """Column names and exact types from the server, without running the query."""
        cursor.execute(
            "SELECT name, system_type_name, error_message FROM sys.dm_exec_describe_first_result_set(%s, NULL, 0) "
            "WHERE is_hidden = 0 ORDER BY column_ordinal",
            (query,),
        )
        rows = cursor.fetchall()
        if rows and rows[0][2]:
            raise SourceError(str(rows[0][2]))
        return [{"name": str(name), "type": str(type_name)} for name, type_name, _ in rows] or None

    def preview(self, query: str) -> Preview:
        """First rows of the query; the column types come from the server's describe, without running the query."""
        statement, plain = preview_statement(self.template, query)
        conn = self._connect()
        try:
            cursor = conn.cursor()
            columns = self._describe(cursor, plain)
            cursor.execute(statement)
            rows = [[json_value(v) for v in row] for row in cursor.fetchall()]
            if columns is None:
                columns = [{"name": d[0], "type": "unknown"} for d in cursor.description or []]
        except pymssql.Error as error:
            raise SourceError(_sqlserver_message(error)) from None
        finally:
            conn.close()
        return Preview(columns, rows)
