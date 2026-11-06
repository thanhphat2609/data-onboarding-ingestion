"""MySQL: the client behind Test connection and the query preview."""

from __future__ import annotations

import re
import ssl
import time
from collections.abc import Callable
from typing import Any

import pymysql
from pymysql.constants import FIELD_TYPE

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
                password=resolve_password(p),
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
        return TestResult(True, message, elapsed_ms(started))

    def preview(self, query: str) -> Preview:
        """First rows and column types of the query."""
        statement, _ = preview_statement(self.template, query)
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
