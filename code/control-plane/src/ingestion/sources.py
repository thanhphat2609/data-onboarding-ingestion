"""Live access to sources for "Test connection" and the query preview. One client class per source template.

The run itself never goes through here: Flink reads the source (Phase 4). This module only opens short, read-only
sessions with a login timeout and a query timeout.
"""

from __future__ import annotations

import datetime as dt
import decimal
import json
import re
import ssl
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import psycopg
import pymssql
import pymysql
from pymysql.constants import FIELD_TYPE

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
    def test(self) -> TestResult:
        """Opens a connection and reports the server and database."""
        ...

    def preview(self, query: str) -> Preview:
        """First rows and column types of the query."""
        ...


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
    if isinstance(value, bytes | bytearray | memoryview):
        data = bytes(value)
        return "0x" + data[:64].hex() + ("…" if len(data) > 64 else "")
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict | list):
        return json.dumps(value, default=str)
    return str(value)


def _password(params: dict[str, Any]) -> str:
    """The connection's password from its secret reference; SourceError says which variable is missing."""
    try:
        return resolve(str(params["password"]))
    except SecretError as error:
        raise SourceError(f"password: {error}") from None


def _preview_statement(template: Template, query: str) -> tuple[str, str]:
    """The template's preview snippet around the query, and the query as a derived table would see it."""
    prefix, body = split_for_wrapping(query, str(template.body["dialect"]))
    outer = render(template.body["preflight"]["preview"], {"limit": PREVIEW_ROWS, "query": body})
    join = (lambda sql: f"{prefix} {sql}") if prefix else (lambda sql: sql)
    return join(outer), join(body)


def _elapsed_ms(started: float) -> int:
    """Milliseconds since ``started``, a ``time.monotonic()`` value."""
    return round((time.monotonic() - started) * 1000)


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
        """``connect`` is replaced by a fake in tests; the parameters get the template's defaults."""
        self.params = with_defaults(template.params("connection_params"), params)
        self.template = template
        self._connect_fn = connect

    def _connect(self) -> Any:
        """Opens a read-only pymssql connection with timeouts; SourceError with a readable message."""
        p = self.params
        password = _password(p)
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
        return TestResult(True, message, _elapsed_ms(started))

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
        statement, plain = _preview_statement(self.template, query)
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


# --- PostgreSQL ----------------------------------------------------------------------------------


def _postgres_message(error: Exception) -> str:
    """A one-line message for a psycopg error, with a hint for the common causes."""
    message = " ".join(line.strip() for line in str(error).strip().splitlines()[:2]) or type(error).__name__
    if "password authentication failed" in message:
        return f"{message}. Check the username and the password secret."
    if isinstance(error, psycopg.OperationalError) and re.search(r"connect|timeout|resolve|refused", message, re.I):
        return f"Cannot reach the server: {message}"
    return message


class PostgresClient:
    def __init__(self, params: dict[str, Any], template: Template, connect: Callable[..., Any] = psycopg.connect):
        """``connect`` is replaced by a fake in tests; the parameters get the template's defaults."""
        self.params = with_defaults(template.params("connection_params"), params)
        self.template = template
        self._connect_fn = connect

    def _connect(self) -> Any:
        """Opens a psycopg connection with timeouts and the connection's sslmode."""
        p = self.params
        options: dict[str, Any] = {
            "host": str(p["host"]),
            "port": int(p["port"]),
            "dbname": str(p["database"]),
            "user": str(p["username"]),
            "password": _password(p),
            "sslmode": str(p["sslmode"]),
            "connect_timeout": LOGIN_TIMEOUT_S,
            "application_name": "ingestion-api",
            # Read-only sessions and a statement timeout, whatever the role allows.
            "options": f"-c default_transaction_read_only=on -c statement_timeout={QUERY_TIMEOUT_S * 1000}",
            "autocommit": True,
        }
        if p["sslmode"] in ("verify-ca", "verify-full"):
            options["sslrootcert"] = "system"  # the image's CA bundle, as for Azure Database for PostgreSQL
        try:
            return self._connect_fn(**options)
        except psycopg.Error as error:
            raise SourceError(_postgres_message(error)) from None

    def test(self) -> TestResult:
        """Opens a connection and reports the server and database; warns when the login can write."""
        started = time.monotonic()
        try:
            conn = self._connect()
        except SourceError as error:
            return TestResult(False, str(error))
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT version(), current_database(), EXISTS ("
                " SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')"
                " AND has_table_privilege(c.oid, 'INSERT, UPDATE, DELETE'))"
            )
            version, database, can_write = cursor.fetchone()
        except psycopg.Error as error:
            return TestResult(False, _postgres_message(error))
        finally:
            conn.close()
        product = str(version).split(" on ")[0].split(",")[0]
        message = f"Connected to {product}, database {database}"
        if can_write:
            message += f". Warning: this role can write to tables in {database}; use a read-only role"
        return TestResult(True, message, _elapsed_ms(started))

    def preview(self, query: str) -> Preview:
        """First rows and column types of the query."""
        statement, _ = _preview_statement(self.template, query)
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(statement)
            rows = [[json_value(v) for v in row] for row in cursor.fetchall()]
            columns = [{"name": c.name, "type": c.type_display} for c in cursor.description or []]
        except psycopg.Error as error:
            raise SourceError(_postgres_message(error)) from None
        finally:
            conn.close()
        return Preview(columns, rows)


# --- MySQL ---------------------------------------------------------------------------------------

_MYSQL_TYPES = {
    FIELD_TYPE.TINY: "tinyint",
    FIELD_TYPE.SHORT: "smallint",
    FIELD_TYPE.INT24: "mediumint",
    FIELD_TYPE.LONG: "int",
    FIELD_TYPE.LONGLONG: "bigint",
    FIELD_TYPE.FLOAT: "float",
    FIELD_TYPE.DOUBLE: "double",
    FIELD_TYPE.DATE: "date",
    FIELD_TYPE.NEWDATE: "date",
    FIELD_TYPE.TIME: "time",
    FIELD_TYPE.DATETIME: "datetime",
    FIELD_TYPE.TIMESTAMP: "timestamp",
    FIELD_TYPE.YEAR: "year",
    FIELD_TYPE.VARCHAR: "varchar",
    FIELD_TYPE.VAR_STRING: "varchar",
    FIELD_TYPE.STRING: "char",
    FIELD_TYPE.BLOB: "text/blob",
    FIELD_TYPE.TINY_BLOB: "text/blob",
    FIELD_TYPE.MEDIUM_BLOB: "text/blob",
    FIELD_TYPE.LONG_BLOB: "text/blob",
    FIELD_TYPE.JSON: "json",
    FIELD_TYPE.BIT: "bit",
    FIELD_TYPE.ENUM: "enum",
    FIELD_TYPE.SET: "set",
    FIELD_TYPE.GEOMETRY: "geometry",
}


def _mysql_type(description: tuple[Any, ...]) -> str:
    """Type name of a result column, for the preview."""
    _, code, _, _, precision, scale, _ = description
    if code in (FIELD_TYPE.DECIMAL, FIELD_TYPE.NEWDECIMAL):
        # The driver reports the display length; the digits are that minus the sign and the decimal point.
        digits = max(int(precision or 0) - (1 if scale else 0) - 1, 1)
        return f"decimal({digits},{scale or 0})"
    return _MYSQL_TYPES.get(code, f"type {code}")


def _mysql_ssl(mode: str) -> dict[str, Any]:
    """pymysql arguments for the template's ssl_mode (same names as the JDBC driver's sslMode)."""
    if mode == "DISABLED":
        return {"ssl_disabled": True}
    context = ssl.create_default_context()
    if mode in ("PREFERRED", "REQUIRED"):
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif mode == "VERIFY_CA":
        context.check_hostname = False
    return {"ssl": context}


def _mysql_message(error: Exception) -> str:
    """A one-line message for a PyMySQL error, with a hint for the common causes."""
    code, message = (error.args + (None, None))[:2] if error.args else (None, str(error))
    message = str(message or error)
    if code == 1045:
        return f"{message}. Check the username and the password secret."
    if code in (2003, 2005, 2013):
        return f"Cannot reach the server: {message}"
    return message


class MySqlClient:
    def __init__(self, params: dict[str, Any], template: Template, connect: Callable[..., Any] = pymysql.connect):
        """``connect`` is replaced by a fake in tests; the parameters get the template's defaults."""
        self.params = with_defaults(template.params("connection_params"), params)
        self.template = template
        self._connect_fn = connect

    def _connect(self) -> Any:
        """Opens a PyMySQL connection with timeouts; checks that TLS was negotiated when ssl_mode asks."""
        p = self.params
        mode = str(p["ssl_mode"])
        try:
            conn = self._connect_fn(
                host=str(p["host"]),
                port=int(p["port"]),
                user=str(p["username"]),
                password=_password(p),
                database=str(p["database"]),
                connect_timeout=LOGIN_TIMEOUT_S,
                read_timeout=QUERY_TIMEOUT_S,
                write_timeout=QUERY_TIMEOUT_S,
                charset="utf8mb4",
                autocommit=True,
                program_name="ingestion-api",
                **_mysql_ssl(mode),
            )
            cursor = conn.cursor()
            # Read-only session and a statement timeout, whatever the user is granted.
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute(f"SET SESSION max_execution_time = {QUERY_TIMEOUT_S * 1000}")
            if mode not in ("DISABLED", "PREFERRED"):
                # pymysql falls back to plain text when the server has no TLS; REQUIRED and stricter must not.
                cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
                row = cursor.fetchone()
                if not row or not row[1]:
                    conn.close()
                    raise SourceError(f"ssl_mode {mode}: the server did not accept a TLS connection")
            return conn
        except pymysql.Error as error:
            raise SourceError(_mysql_message(error)) from None

    def test(self) -> TestResult:
        """Opens a connection and reports the server and database; warns when the login can write."""
        started = time.monotonic()
        try:
            conn = self._connect()
        except SourceError as error:
            return TestResult(False, str(error))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT VERSION(), DATABASE()")
            version, database = cursor.fetchone()
            cursor.execute("SHOW GRANTS")
            grants = " ".join(str(row[0]) for row in cursor.fetchall())
        except pymysql.Error as error:
            return TestResult(False, _mysql_message(error))
        finally:
            conn.close()
        message = f"Connected to MySQL {version}, database {database}"
        if re.search(r"\b(ALL PRIVILEGES|INSERT|UPDATE|DELETE)\b", grants):
            message += f". Warning: this user can write to {database}; grant SELECT only"
        return TestResult(True, message, _elapsed_ms(started))

    def preview(self, query: str) -> Preview:
        """First rows and column types of the query."""
        statement, _ = _preview_statement(self.template, query)
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(statement)
            rows = [[json_value(v) for v in row] for row in cursor.fetchall()]
            columns = [{"name": str(d[0]), "type": _mysql_type(d)} for d in cursor.description or []]
        except pymysql.Error as error:
            raise SourceError(_mysql_message(error)) from None
        finally:
            conn.close()
        return Preview(columns, rows)


_CLIENTS: dict[str, Callable[[dict[str, Any], Template], SourceClient]] = {
    "sqlserver": SqlServerClient,
    "postgresql": PostgresClient,
    "mysql": MySqlClient,
}


def client_for(connection: dict[str, Any], template: Template) -> SourceClient:
    """The client of the connection's source type; SourceError when the type has none yet."""
    client = _CLIENTS.get(template.name)
    if client is None:
        raise SourceError(f"Live access to {template.ref} sources is not available yet")
    return client(connection["params"], template)
