# ADR-0005: Free-form read-only SQL with AST validation and rewriting

- Status: Proposed
- Date: 2026-10-21

## Context

Users, including the data team, need joins, CTEs and aggregations, not only "select a table". The Flink JDBC table connector accepts a table name, not an arbitrary query, and the platform must derive several variants of each query (preview, count, bounds, partitioned ranges) without breaking dialect rules.

## Decision

- Users write free-form SQL in the **connection's own dialect**.
- The control plane parses it with **sqlglot** and accepts only a single read-only query. It rejects DML, DDL, `SELECT ... INTO`, multiple statements, procedure calls, and a per-dialect blocklist (`OPENROWSET`, `OPENQUERY`, `xp_*`, `dblink`, `pg_sleep`, `pg_read_file`, ...). Output columns must be unique and named.
- **Mode selection:** a single-table projection and filter runs in *table mode* (Flink JDBC table connector with filter push-down); everything else runs in *query mode*: the SQL text becomes a derived table `(<query>) AS q` for the same connector, with CTEs inlined by sqlglot ([ADR-0010](0010-pyflink-runner.md)). BigQuery queries are materialized to a temporary table.
- **All derived queries are built by transforming the AST**, never by string concatenation. Because every variant wraps the query as a derived table, non-recursive CTEs are inlined into derived tables (`SELECT * FROM (WITH ...)` is invalid in T-SQL) and a top-level `ORDER BY` is removed.
- Partitioning in query mode is opt-in through an output `partition_column` (numeric or date) and becomes `BETWEEN ? AND ?` ranges.
- **The read-only database principal is the primary control.** SQL validation is a second layer that also gives users early, readable errors.

## Consequences

- Users get full SQL expressiveness without access to Flink.
- Complex queries are executed several times (preflight count and bounds, then the run). Users can skip verification and partitioning for expensive queries.
- Dialect edge cases live in one module with a dedicated test suite of accepted and rejected queries.

## Alternatives considered

- **Table picker only** (table, columns, filter): safe and simple, but does not meet the data team's needs.
- **Passing a subquery as the JDBC `table-name`**: depends on dialect-specific identifier quoting and breaks on CTEs; rejected.
- **Running user SQL inside Flink SQL** (federated): the user would have to write Flink SQL instead of the source dialect, and push-down would be lost.
