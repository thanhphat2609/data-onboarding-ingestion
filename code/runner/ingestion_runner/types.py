"""Maps JDBC column types (``java.sql.Types``) to Flink SQL types.

The JDBC connector needs the column list in its DDL, and a job's query can return anything, so the runner reads the
result's metadata from the source first (jdbc_meta.py) and maps it here. Mapping by ``java.sql.Types`` works the same
for every driver; the type name only settles the few cases where drivers report a generic type.
"""

from __future__ import annotations

BIT, TINYINT, SMALLINT, INTEGER, BIGINT = -7, -6, 5, 4, -5
FLOAT, REAL, DOUBLE, NUMERIC, DECIMAL = 6, 7, 8, 2, 3
CHAR, VARCHAR, LONGVARCHAR, NCHAR, NVARCHAR, LONGNVARCHAR = 1, 12, -1, -15, -9, -16
DATE, TIME, TIMESTAMP, TIMESTAMP_WITH_TIMEZONE = 91, 92, 93, 2014
BOOLEAN, OTHER, CLOB = 16, 1111, 2005
BINARY, VARBINARY, LONGVARBINARY, BLOB = -2, -3, -4, 2004

SIMPLE = {
    TINYINT: "SMALLINT",  # SQL Server's tinyint is unsigned (0-255), which doesn't fit a signed TINYINT
    SMALLINT: "SMALLINT",
    INTEGER: "INT",
    BIGINT: "BIGINT",
    REAL: "FLOAT",
    FLOAT: "DOUBLE",
    DOUBLE: "DOUBLE",
    BOOLEAN: "BOOLEAN",
    CHAR: "STRING",
    VARCHAR: "STRING",
    LONGVARCHAR: "STRING",
    NCHAR: "STRING",
    NVARCHAR: "STRING",
    LONGNVARCHAR: "STRING",
    CLOB: "STRING",
    DATE: "DATE",
    TIME: "TIME(0)",
    TIMESTAMP_WITH_TIMEZONE: "TIMESTAMP_LTZ(3)",
    BINARY: "BYTES",
    VARBINARY: "BYTES",
    LONGVARBINARY: "BYTES",
    BLOB: "BYTES",
}

# PostgreSQL reports these as OTHER or as a plain TIMESTAMP.
STRING_TYPE_NAMES = {"uuid", "json", "jsonb"}
ZONED_TIMESTAMP_NAMES = {"timestamptz", "timestamp with time zone"}


class UnsupportedType(ValueError):
    """A column the runner can't copy; the message names it and says what to do in the query."""


def flink_type(column: str, sql_type: int, type_name: str, precision: int, scale: int) -> str:
    """Flink SQL type for one JDBC column; raises UnsupportedType, naming the column, when there is no safe mapping."""
    name = type_name.lower()
    if sql_type == BIT:
        if precision <= 1:
            return "BOOLEAN"
        raise UnsupportedType(f'column "{column}": {type_name}({precision}) is not supported; cast it in the query')
    if sql_type in (NUMERIC, DECIMAL):
        # PostgreSQL's unconstrained numeric reports precision 0 (or a huge one): there is no safe fixed type for it.
        if not 1 <= precision <= 38 or scale < 0 or scale > precision:
            raise UnsupportedType(
                f'column "{column}": {type_name}({precision},{scale}) has no fixed precision of at most 38 digits; '
                f"cast it in the query, for example CAST({column} AS DECIMAL(38, 10))"
            )
        return f"DECIMAL({precision}, {scale})"
    if sql_type == TIMESTAMP:
        return "TIMESTAMP_LTZ(3)" if name in ZONED_TIMESTAMP_NAMES else "TIMESTAMP(3)"
    if sql_type == OTHER and name in STRING_TYPE_NAMES:
        return "STRING"
    if sql_type in SIMPLE:
        return SIMPLE[sql_type]
    raise UnsupportedType(
        f'column "{column}": type {type_name} (JDBC {sql_type}) is not supported; cast it in the query'
    )
