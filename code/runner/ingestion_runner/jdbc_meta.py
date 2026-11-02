"""Asks the source what the query returns, before the Flink job is built.

The JDBC table connector needs every column and its type in the DDL, and a job's query can return anything, so this
reads the result's metadata and the partition column's bounds. It goes through the Flink JVM that PyFlink already
runs (py4j), so the JDBC drivers in ``/opt/flink/lib`` are used and no database client is added to the JobManager.
The password stays in memory, like in the job itself.
"""

from __future__ import annotations

import re
from typing import Any

from ingestion_runner.flink_sql import Column, check_columns
from ingestion_runner.plan import Plan
from ingestion_runner.types import flink_type

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
QUOTES = {"postgres": '"{}"', "sqlserver": "[{}]", "mysql": "`{}`"}


def _connect(plan: Plan) -> Any:
    """Opens a JDBC connection to the source in the Flink JVM, with the driver of the plan."""
    from pyflink.java_gateway import get_gateway

    jvm = get_gateway().jvm
    jvm.java.lang.Class.forName(plan.driver)
    return jvm.java.sql.DriverManager.getConnection(plan.jdbc_url, plan.username, plan.password)


def describe(plan: Plan) -> list[Column]:
    """Column names and Flink types of the job's query, from a statement that returns no rows."""
    connection = _connect(plan)
    try:
        statement = connection.createStatement()
        try:
            result = statement.executeQuery(f"SELECT * FROM ({plan.query}) AS q WHERE 1 = 0")
            meta = result.getMetaData()
            columns = [
                Column(
                    meta.getColumnLabel(i),
                    flink_type(
                        meta.getColumnLabel(i),
                        meta.getColumnType(i),
                        meta.getColumnTypeName(i),
                        meta.getPrecision(i),
                        meta.getScale(i),
                    ),
                )
                for i in range(1, meta.getColumnCount() + 1)
            ]
        finally:
            statement.close()
    finally:
        connection.close()
    check_columns(columns)
    return columns


def bounds(plan: Plan, columns: list[Column]) -> tuple[str, str] | None:
    """Lowest and highest value of the partition column, or None when there is nothing to split."""
    column = plan.partition_column
    if not column or plan.partition_num <= 1:
        return None
    if not IDENTIFIER.match(column):
        raise ValueError(f'partition_column "{column}" must be a plain column name')
    if column.lower() not in {c.name.lower() for c in columns}:
        raise ValueError(f'partition_column "{column}" is not a column of the query: {[c.name for c in columns]}')
    quoted = QUOTES[plan.dialect].format(column)
    connection = _connect(plan)
    try:
        statement = connection.createStatement()
        try:
            result = statement.executeQuery(f"SELECT MIN({quoted}), MAX({quoted}) FROM ({plan.query}) AS q")
            result.next()
            low, high = result.getString(1), result.getString(2)
        finally:
            statement.close()
    finally:
        connection.close()
    if low is None or high is None or low == high:
        return None
    return str(low), str(high)
