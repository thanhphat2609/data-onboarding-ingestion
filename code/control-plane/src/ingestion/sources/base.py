"""What every source client shares: the errors, the result types, the protocol and the small helpers.

Live access to sources is for "Test connection" and the query preview only. The run itself never goes through here:
Flink reads the source (Phase 4). The clients open short, read-only sessions with a login timeout and a query timeout.
"""

from __future__ import annotations

import datetime as dt
import decimal
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from ingestion.secrets import SecretError, resolve
from ingestion.sql import split_for_wrapping
from ingestion.templates import Template, render

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


def resolve_password(params: dict[str, Any]) -> str:
    """The connection's password from its secret reference; SourceError says which variable is missing."""
    try:
        return resolve(str(params["password"]))
    except SecretError as error:
        raise SourceError(f"password: {error}") from None


def preview_statement(template: Template, query: str) -> tuple[str, str]:
    """The template's preview snippet around the query, and the query as a derived table would see it."""
    prefix, body = split_for_wrapping(query, str(template.body["dialect"]))
    outer = render(template.body["preflight"]["preview"], {"limit": PREVIEW_ROWS, "query": body})
    join = (lambda sql: f"{prefix} {sql}") if prefix else (lambda sql: sql)
    return join(outer), join(body)


def elapsed_ms(started: float) -> int:
    """Milliseconds since ``started``, a ``time.monotonic()`` value."""
    return round((time.monotonic() - started) * 1000)
