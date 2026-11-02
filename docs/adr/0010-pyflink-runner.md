# ADR-0010: PyFlink runner, Table API and SQL only

- Status: Proposed (pending Phase 2 spikes)
- Date: 2026-10-22

## Context

The architecture planned the generic ingestion runner as a Java 17 / Maven project. Everything else in the platform is Python: the Ingestion API, the CLI, the Airflow DAG factory and tasks. The team that maintains the platform, and the people who join it later, work in Python; a single Java component would be the part nobody is comfortable changing.

The runner is small: it reads the job file, its connection and the templates, declares a source and a sink, and starts one bounded job. It does not transform rows beyond adding audit columns.

## Decision

- Write the runner in **PyFlink 1.20** (Python), in `code/runner/`.
- Use **only the Table API and Flink SQL**. No Python UDFs and no Python DataStream functions, so the job graph runs entirely in the JVM:
  - TaskManagers need no Python; their image and performance stay as they are.
  - Only the JobManager image adds Python and PyFlink, because it runs the script that builds the job.
- Express everything in SQL: sources and sinks as `CREATE TABLE` with the JDBC, BigQuery and filesystem connectors; audit columns `ingest_date`, `_ingest_run_id` and `_ingested_at` as literals in the `INSERT ... SELECT`.
- **Submit through the Flink REST API** with the `flink-python` JAR shipped with Flink: `POST /jars/{flink-python}/run`, entry class `org.apache.flink.client.python.PythonDriver`, arguments `-py <runner>/main.py --job <path> --run-id <run_id> --ingest-date <date>`. Airflow needs no Flink client and no Java.
- **Query mode** (free-form SQL with joins and CTEs) passes the user's query to the JDBC table connector as a derived table, `(<query>) AS q`. CTEs are inlined into derived tables by sqlglot before rendering; recursive CTEs are rejected. If the connector cannot take a derived table for a dialect, the fallback is the Java `JdbcSource` wrapped through PyFlink's Java gateway.
- **Written row counts** come from the Parquet footers of the staged files, read by the publisher. The runner does not write a manifest, because a job submitted through REST cannot reliably run code after the job ends.

## Update 2026-11-02: no resolved spec

The first cut of the runner (`code/runner/`, [README](../../code/runner/README.md)) reads the merged YAML files directly: the `IngestionJob`, its `Connection` and the two templates. There is no resolved job spec and no `spec_version`: the files are written by the Data Team through pull requests, and the template versions (`mysql@1`, `adls_parquet@1`) already version the contract between the repositories. What the old spec carried is found at run time instead: the runner asks the source for the query's columns (JDBC metadata, through the Flink JVM, so no database client is added to the JobManager) and for the partition column's bounds. The expected row count stays a preflight and `verify` concern of Airflow.

The status stays *Proposed* until spikes 5 and 6 have run on a cluster: the derived table `(<query>) AS q` per dialect, and submission with `PythonDriver`.

## Consequences

- One language across the platform; new members can read and change every component.
- Python versions are bound to PyFlink 1.20 (Python 3.8–3.11) for the runner; the rest of the platform can use Python 3.12.
- The JobManager image grows by Python and the `apache-flink` package; the TaskManager image does not.
- Features that need custom row-level code must be written as SQL. If one ever needs a UDF, it is written in Java as a small, separate JAR, or the Python environment is added to the TaskManagers; either is a new ADR.
- Phase 2 must prove, before Phase 4 starts:
  1. REST submission with `PythonDriver` works on the session cluster.
  2. The JDBC table connector accepts a derived table, including partitioned scans, on SQL Server and PostgreSQL; otherwise the `JdbcSource` fallback works from PyFlink.
  3. The BigQuery connector works from PyFlink SQL DDL.
  4. The size of the JobManager image with PyFlink is acceptable for Codespaces.

## Alternatives considered

- **Java runner** (the previous plan): direct access to every connector API and no Python on the cluster, but a second language that future maintainers may not know.
- **PyFlink with Python UDFs**: more flexible, but Python on every TaskManager, serialization between the JVM and Python, and slower jobs.
- **Flink SQL Gateway** (submit SQL statements over REST, no runner): no runner code at all, but one more service to run, and run-level logic (spec loading, secret resolution, partition bounds) would move into Airflow tasks as string building.
