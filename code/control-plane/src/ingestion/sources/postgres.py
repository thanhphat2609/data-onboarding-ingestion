"""PostgreSQL: the client behind Test connection and the query preview."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

import psycopg

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
            "password": resolve_password(p),
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
        return TestResult(True, message, elapsed_ms(started))

    def preview(self, query: str) -> Preview:
        """First rows and column types of the query."""
        statement, _ = preview_statement(self.template, query)
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
