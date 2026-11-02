# Phase 2 spike results

Status: **in progress** · Started 2026-10-25 · Plan: [roadmap Phase 2](../roadmap.md#phase-2-connector-spikes) · Code: [code/spikes/phase-2/](../../code/spikes/phase-2/README.md)

Each spike records what was run, the outcome (works / works with changes / fails), and the decision it feeds. Fill a row when a spike has run; keep failures, they are results too.

## Environment

| Item | Version | Notes |
|---|---|---|
| Flink | 1.20.5 (`flink:1.20.5-scala_2.12-java17`) | Session cluster, 1 JobManager, 1 TaskManager with 4 slots, `execution.runtime-mode: BATCH` |
| JDBC connector | `flink-connector-jdbc` 3.4.0-1.20 | Bundle with all dialects |
| Drivers | mssql-jdbc 13.6.1.jre11, postgresql 42.7.14, mysql-connector-j 9.7.0 | |
| Parquet | `flink-sql-parquet` 1.20.5 + `hadoop-client-api`/`-runtime` 3.3.6 | Hadoop classes are needed by the Parquet writer |
| ADLS Gen2 | `flink-azure-fs-hadoop` 1.20.5 (plugin) | Needs the dev storage account and a service principal |
| PyFlink | `apache-flink` 1.20.5 on Python 3.11 (JobManager only) | Image size: _to measure_ |
| BigQuery | candidate: `com.google.cloud.flink:flink-1.17-connector-bigquery` 1.2.0 | Built for 1.17; compatibility with 1.20 is the question |
| Test sources | SQL Server 2022 (`crm`), PostgreSQL 16.15 (`sales`), MySQL 8.4.13 (`shop`) | Same model: `segments`, `customers` (10k), `orders` (10M via `seed-large.sh`) |

## Results

| # | Spike | Outcome | Notes and decision |
|---|---|---|---|
| 0 | Phase 1 carry-over: Run now → WordCount `FINISHED`, invalid file flagged | | |
| 1 | Flink image builds; JobManager image size with PyFlink | | |
| 2 | SQL Server → Parquet, table mode, `applicationIntent=ReadOnly` | | |
| 3 | PostgreSQL → Parquet, partitioned scan, `scan.auto-commit=false` | | |
| 4 | MySQL → Parquet, partitioned scan, `useCursorFetch=true` | | |
| 5 | Query mode: `(<query>) AS q` with JOIN + CTE on SQL Server, PostgreSQL, MySQL | | Fallback if rejected: Java `JdbcSource` through the PyFlink gateway |
| 6 | PyFlink through REST with `PythonDriver` (`submit_rest.py`) | | Feeds [ADR-0010](../adr/0010-pyflink-runner.md) |
| 7 | Keeping the password out of the job plan | | Runner requirement (architecture §3.7) |
| 8 | Parquet to ADLS Gen2 with `abfss://` | | Blocked: storage account and credentials |
| 9 | BigQuery source from PyFlink SQL DDL (table read, materialized query) | | Blocked: BigQuery project and service account |
| 10 | Delta commit of Flink-written Parquet with delta-rs; replace one `ingest_date` | | Feeds [ADR-0004](../adr/0004-lake-layout-and-delta-commit.md) |
| 11 | Parquet timestamps readable by pandas, Spark and Delta readers | | `check_parquet.py` covers pyarrow/pandas |
| 12 | REST API source: approach compared, ADR written | ✅ ADR written; 🟡 PyFlink run pending | [ADR-0015](../adr/0015-rest-api-source-via-redpanda.md). 2026-10-30, outside the Codespace: `airflow dags test` on Airflow 3.3.2 (`validate → fetch → submit → wait`, a 429 retried); `fetch` → Redpanda v25.3.18 (two runs: offsets [0, 100) and [100, 200)); Flink 1.20.3 SQL client with `flink-sql-connector-kafka` 3.3.0-1.20 read [100, 200) with `scan.bounded.mode: specific-offsets` → Parquet, `FINISHED` in 3.4 s, 100 rows, only that run's records. Redpanda's HTTP proxy can't create topics (and answers 200 with `error_code: 3` for a missing one), so `fetch` uses confluent-kafka. To do in the Codespace: `kafka_to_parquet.py` from PyFlink |
| 13 | Runner first cut ([code/runner/](../../code/runner/README.md)) on the saved jobs: JDBC metadata through py4j, `(<query>) AS q` with a partitioned scan, Parquet to `_staging/<run_id>/` | | Covers spikes 3-6 through the real code path; written 2026-11-02, not run yet |

## Throughput (10M rows of `orders`, 4 slots)

| Source | Partitions | Fetch size | Seconds | Rows/s | Rows/s per slot |
|---|---|---|---|---|---|
| SQL Server | | | | | |
| PostgreSQL | | | | | |
| MySQL | | | | | |
| BigQuery | | | | | |

## Decisions

- **REST API source** (2026-10-30): Airflow `fetch` lands records on Redpanda; Flink reads the run's offset range as the bounded table `landing` ([ADR-0015](../adr/0015-rest-api-source-via-redpanda.md)). Pinned: Redpanda v25.3.18, `flink-sql-connector-kafka` 3.3.0-1.20, `confluent-kafka` 2.16.0.

_Filled at the end of the phase: pinned versions (copied to architecture §11), Delta strategy, BigQuery connector._
