"""The three Flink SQL statements of a run: the JDBC source, the Parquet sink and the INSERT between them.

Everything is plain SQL (ADR-0010): no Python UDFs, so the job graph runs entirely in the JVM and the TaskManagers need
no Python. The JDBC connector quotes its ``table-name`` as one identifier, so it can't read a derived table
``(<query>) AS q`` (spike 5 in docs/spikes/phase-2.md found this on MySQL: "Identifier name ... is too long"). Until
the ``JdbcSource`` fallback of ADR-0010 exists, the runner reads plain ``SELECT <columns or *> FROM <table>`` queries:
the connector gets the table and reads only the columns of the DDL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ingestion_runner.plan import Plan

AUDIT_COLUMNS = ("ingest_date", "_ingest_run_id", "_ingested_at")


@dataclass(frozen=True)
class Column:
    name: str
    flink_type: str


_IDENT = r"(?:[\w$]+|`[^`]+`|\"[^\"]+\"|\[[^\]]+\])"
_PLAIN_SELECT = re.compile(
    rf"^\s*SELECT\s+(?:\*|{_IDENT}(?:\s*,\s*{_IDENT})*)\s+FROM\s+({_IDENT}(?:\s*\.\s*{_IDENT})*)\s*$", re.IGNORECASE
)


def single_table(query: str, dialect: str) -> str:
    """The table of a plain ``SELECT <columns or *> FROM <table>`` query, as the JDBC connector takes it.

    Raises ValueError for anything else (joins, filters, expressions, aliases, subqueries).
    """
    found = _PLAIN_SELECT.match(query)
    if not found:
        raise ValueError(
            "the runner reads plain `SELECT <columns or *> FROM <table>` queries for now: Flink's JDBC connector "
            "can't read a derived table (ADR-0010, spike 5). Joins, filters, expressions and aliases need the "
            "JdbcSource fallback."
        )
    parts = [re.sub(r'^[`"\[]|[`"\]]$', "", part.strip()) for part in re.findall(_IDENT, found.group(1))]
    # MySQL's connector quotes the whole name as one identifier; the database is already in the JDBC URL.
    return parts[-1] if dialect == "mysql" else ".".join(parts)


def quote(name: str) -> str:
    """Backtick-quotes a column name for Flink SQL."""
    return "`" + name.replace("`", "``") + "`"


def options(values: dict[str, object]) -> str:
    """The body of a ``WITH (...)`` clause: one ``'key' = 'value'`` per option, quotes escaped."""
    return ",\n  ".join(f"'{key}' = '{str(value).replace(chr(39), chr(39) * 2)}'" for key, value in values.items())


def check_columns(columns: list[Column]) -> None:
    """Raises ValueError for a repeated column name or one that the platform adds itself (the audit columns)."""
    seen: set[str] = set()
    for column in columns:
        lowered = column.name.lower()
        if lowered in seen:
            raise ValueError(f'the query returns the column "{column.name}" twice; give each column its own name')
        if lowered in AUDIT_COLUMNS:
            raise ValueError(f'the query returns "{column.name}", a name the platform adds; rename it in the query')
        seen.add(lowered)


def source_ddl(plan: Plan, columns: list[Column], bounds: tuple[str, str] | None) -> str:
    """``CREATE TABLE src``: the JDBC table over the job's query, split into ranges when ``bounds`` is given."""
    jdbc: dict[str, object] = {
        "connector": "jdbc",
        "url": plan.jdbc_url,
        "driver": plan.driver,
        "username": plan.username,
        "password": plan.password,
        "table-name": single_table(plan.query, plan.dialect),
        "scan.fetch-size": plan.fetch_size,
    }
    if plan.dialect == "postgres":
        # The PostgreSQL driver only streams with a fetch size when auto-commit is off.
        jdbc["scan.auto-commit"] = "false"
    if plan.partition_column and bounds and plan.partition_num > 1:
        jdbc |= {
            "scan.partition.column": plan.partition_column,
            "scan.partition.num": plan.partition_num,
            "scan.partition.lower-bound": bounds[0],
            "scan.partition.upper-bound": bounds[1],
        }
    return f"CREATE TABLE src ({_columns(columns)}) WITH (\n  {options(jdbc)}\n)"


def sink_ddl(plan: Plan, columns: list[Column]) -> str:
    """``CREATE TABLE dst``: Parquet in the run's staging location, by ``ingest_date``, with the audit columns."""
    audit = "ingest_date STRING, _ingest_run_id STRING, _ingested_at TIMESTAMP(3)"
    sink: dict[str, object] = {
        "connector": "filesystem",
        "path": plan.staging_uri,
        "format": "parquet",
        "parquet.compression": plan.compression,
    }
    return f"CREATE TABLE dst ({_columns(columns)}, {audit}) PARTITIONED BY (ingest_date) WITH (\n  {options(sink)}\n)"


def insert_sql(plan: Plan, columns: list[Column]) -> str:
    """The ``INSERT`` from ``src`` into ``dst``; the audit values are literals, so the TaskManagers run no Python."""
    names = ", ".join(quote(column.name) for column in columns)
    audit = f"'{plan.ingest_date}', '{plan.run_id}', CAST('{plan.ingested_at}' AS TIMESTAMP(3))"
    return f"INSERT INTO dst SELECT {names}, {audit} FROM src"


def _columns(columns: list[Column]) -> str:
    """``name TYPE`` list for a ``CREATE TABLE``."""
    return ", ".join(f"{quote(column.name)} {column.flink_type}" for column in columns)
