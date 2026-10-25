"""Live access to sources for "Test connection" and the query preview. One client class per source template.

The run itself never goes through here: Flink reads the source (Phase 4). This module only opens short sessions
with a login timeout and a query timeout.
"""

from __future__ import annotations

import datetime as dt
import decimal
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import pymssql

from ingestion.secrets import SecretError, resolve
from ingestion.sql import split_for_wrapping
from ingestion.templates import Template, render, with_defaults

PREVIEW_ROWS = 100
LOGIN_TIMEOUT_S = 10
QUERY_TIMEOUT_S = 60


class SourceError(Exception):
    """A failure with a message for users (bad host, login failed, invalid query...)."""


@dataclass
class TestResult:
    ok: bool
    message: str
    latency_ms: int | None = None


@dataclass
class Preview:
    columns: list[dict[str, str]]
    rows: list[list[Any]]


class SourceClient(Protocol):
    def test(self) -> TestResult: ...

    def preview(self, query: str) -> Preview: ...


def json_value(value: Any) -> Any:
    """Makes a database value JSON-safe without losing precision (decimals and big integers become text)."""
    if value is None or isinstance(value, bool | str | float):
        return value
    if isinstance(value, int):
        return value if abs(value) < 2**53 else str(value)
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, bytes | bytearray):
        return "0x" + bytes(value[:64]).hex() + ("…" if len(value) > 64 else "")
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


# --- SQL Server ----------------------------------------------------------------------------------


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
        self.params = with_defaults(template.params("connection_params"), params)
        self.template = template
        self._connect_fn = connect

    def _connect(self) -> Any:
        p = self.params
        try:
            password = resolve(str(p["password"]))
        except SecretError as error:
            raise SourceError(f"password: {error}") from None
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
        latency = round((time.monotonic() - started) * 1000)
        product = str(version).splitlines()[0].split(" (KB")[0].strip()
        message = f"Connected to {product}, database {database}"
        if can_insert:
            message += f". Warning: this login can write to {database}; use a read-only login"
        return TestResult(True, message, latency)

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
        dialect = str(self.template.body["dialect"])
        prefix, body = split_for_wrapping(query, dialect)
        outer = render(self.template.body["preflight"]["preview"], {"limit": PREVIEW_ROWS, "query": body})
        statement = f"{prefix} {outer}" if prefix else outer
        conn = self._connect()
        try:
            cursor = conn.cursor()
            columns = self._describe(cursor, f"{prefix} {body}" if prefix else body)
            cursor.execute(statement)
            rows = [[json_value(v) for v in row] for row in cursor.fetchall()]
            if columns is None:
                columns = [{"name": d[0], "type": "unknown"} for d in cursor.description or []]
        except pymssql.Error as error:
            raise SourceError(_sqlserver_message(error)) from None
        finally:
            conn.close()
        return Preview(columns, rows)


_CLIENTS: dict[str, type[SqlServerClient]] = {"sqlserver": SqlServerClient}


def client_for(connection: dict[str, Any], template: Template) -> SourceClient:
    client = _CLIENTS.get(template.name)
    if client is None:
        raise SourceError(f"Live access to {template.ref} sources is not available yet")
    return client(connection["params"], template)
