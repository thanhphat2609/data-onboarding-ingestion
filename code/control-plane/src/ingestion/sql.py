"""Checks and rewrites of user SQL with sqlglot (ADR-0005).

Phase 1 rules: exactly one read-only SELECT, uniquely named output columns. The read-only database login stays the
primary control; this is the second layer. Phase 3 adds the dialect blocklist and the partitioned-query rewrites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

Severity = Literal["error", "warning"]

# Statement types a read-only query must never contain, at any depth.
_FORBIDDEN_NODES: dict[type[exp.Expression], str] = {
    exp.Insert: "INSERT",
    exp.Update: "UPDATE",
    exp.Delete: "DELETE",
    exp.Merge: "MERGE",
    exp.Create: "CREATE",
    exp.Drop: "DROP",
    exp.Alter: "ALTER",
    exp.TruncateTable: "TRUNCATE",
    exp.Grant: "GRANT",
    exp.Command: "Commands",
    exp.Execute: "EXEC",
}
# Functions that reach outside the connected database.
_FORBIDDEN_FUNCTIONS = {"OPENROWSET", "OPENQUERY", "OPENDATASOURCE", "OPENXML"}
# Template dialects sqlglot has no name for. Flink SQL is close to ANSI (Calcite), which is sqlglot's default dialect.
_SQLGLOT_DIALECTS = {"flink": ""}
# API jobs (rest_api template, ADR-0015) read only the table that the run's fetch task filled.
LANDING_TABLE = "landing"


@dataclass
class SqlIssue:
    severity: Severity
    message: str


@dataclass
class SqlCheck:
    mode: Literal["table", "query"] = "query"
    issues: list[SqlIssue] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when there is no error; warnings don't block."""
        return not any(issue.severity == "error" for issue in self.issues)

    def error(self, message: str) -> None:
        """Adds an error: the job can't be saved."""
        self.issues.append(SqlIssue("error", message))

    def warning(self, message: str) -> None:
        """Adds a warning: the job can still be saved."""
        self.issues.append(SqlIssue("warning", message))


def _sqlglot(dialect: str) -> str:
    """sqlglot's name for a template's dialect."""
    return _SQLGLOT_DIALECTS.get(dialect, dialect)


def _parse(query: str, dialect: str) -> list[exp.Expr]:
    """The statements of the query, without empty ones."""
    return [statement for statement in sqlglot.parse(query, read=_sqlglot(dialect)) if statement is not None]


def check_sql(query: str, dialect: str) -> SqlCheck:
    """Checks that the query is one read-only statement with named, unique columns (ADR-0005).

    Never raises: problems come back as errors (the job can't be saved) or warnings (it can).
    """
    result = SqlCheck()
    if not query.strip():
        result.error("Query is empty")
        return result
    try:
        statements = _parse(query, dialect)
    except ParseError as error:
        detail = error.errors[0] if error.errors else {}
        where = f" at line {detail['line']}, column {detail['col']}" if "line" in detail else ""
        result.error(f"Syntax error{where}: {detail.get('description') or 'cannot parse the query'}")
        return result

    if len(statements) != 1:
        result.error("Only one statement is allowed")
    if not statements:
        return result
    statement = statements[0]

    for node in statement.walk():
        for node_type, label in _FORBIDDEN_NODES.items():
            if isinstance(node, node_type):
                result.error(f"{label} is not allowed in a read-only query")
        if isinstance(node, exp.Into):
            result.error("SELECT ... INTO is not allowed")
        if isinstance(node, exp.Anonymous) and node.name.upper() in _FORBIDDEN_FUNCTIONS:
            result.error(f"{node.name.upper()} is not allowed: read only from the connected database")
    for other in statements[1:]:
        if not isinstance(other, exp.Query):
            result.error(f"{other.key.upper()} is not allowed in a read-only query")
    if not isinstance(statement, exp.Query):
        result.error("The query must be a SELECT, optionally with WITH")
        return result

    if statement.args.get("order"):
        result.warning("A top-level ORDER BY is removed before the run")
    columns = statement.named_selects
    if "*" in columns or any(isinstance(s, exp.Star) or s.is_star for s in statement.selects):
        result.warning("SELECT * changes the output when the source table changes; list the columns")
    else:
        for position, name in enumerate(columns, start=1):
            if not name:
                result.error(f"Column {position} has no name; add an alias (AS <name>)")
        duplicates = sorted({name for name in columns if name and columns.count(name) > 1})
        if duplicates:
            result.error(f"Duplicate column names: {', '.join(duplicates)}; add aliases")
    result.columns = [name for name in columns if name and name != "*"]

    tables = [table.sql(dialect=_sqlglot(dialect)) for table in statement.find_all(exp.Table)]
    result.tables = tables
    if dialect == "flink":
        ctes = {cte.alias.lower() for cte in statement.find_all(exp.CTE)}
        others = sorted({t for t in tables if t.lower() not in {LANDING_TABLE, *ctes}})
        if others:
            result.error(f"Read only from the table {LANDING_TABLE}, not {', '.join(others)}: the API data lands there")
    complex_query = any(
        statement.find(node_type) is not None
        for node_type in (exp.Join, exp.Group, exp.SetOperation, exp.With, exp.Distinct, exp.Having, exp.Window)
    )
    result.mode = "table" if len(tables) == 1 and not complex_query else "query"
    return result


def split_for_wrapping(query: str, dialect: str) -> tuple[str, str]:
    """Splits a checked query into its WITH clause and a body that fits in a derived table.

    Template snippets such as ``SELECT TOP ({{ limit }}) * FROM ({{ query }}) AS q`` wrap the user query, but a
    derived table can't hold a WITH clause or, in T-SQL, an ORDER BY without TOP. So the CTEs go in front of the
    outer statement and a top-level ORDER BY is dropped. Returns ``(with_clause or "", body)``.
    """
    statement = _parse(query, dialect)[0].copy()
    with_clause = statement.args.get("with_")
    statement.set("with_", None)
    if statement.args.get("order") and not statement.args.get("limit"):
        statement.set("order", None)
    prefix = with_clause.sql(dialect=_sqlglot(dialect)) if with_clause is not None else ""
    return prefix, statement.sql(dialect=_sqlglot(dialect))
