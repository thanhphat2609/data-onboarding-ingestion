"""Live access to sources for "Test connection" and the query preview: one client class per source template.

``client_for`` picks the client of a connection's template. The run itself never goes through here: Flink reads the
source (Phase 4).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ingestion.sources.base import Preview, SourceClient, SourceError, TestResult
from ingestion.sources.mysql import MySqlClient
from ingestion.sources.postgres import PostgresClient
from ingestion.sources.sqlserver import SqlServerClient
from ingestion.templates import Template

__all__ = ["Preview", "SourceClient", "SourceError", "TestResult", "client_for"]

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
