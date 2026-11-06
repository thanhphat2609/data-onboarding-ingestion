# Ingestion runner

One PyFlink job (ADR-0010) that copies the result of an `IngestionJob`'s query to Parquet. It reads the YAML files as they are merged (the job, its connection, the two templates); there is no intermediate spec.

What a run does:

1. `plan.py` loads the job, its connection and the templates, and resolves the password from its `env://` reference on the JobManager.
2. `jdbc_meta.py` asks the source for the query's columns (a statement with `WHERE 1 = 0`) and, with a `partition_column`, for its MIN and MAX. It uses the JDBC drivers of the Flink JVM through py4j, so nothing is installed besides PyYAML.
3. `flink_sql.py` builds three statements: the JDBC source over the query's table, the filesystem Parquet sink, and `INSERT ... SELECT` with the audit columns `ingest_date`, `_ingest_run_id`, `_ingested_at`. The query must be a plain `SELECT <columns or *> FROM <table>`: the JDBC connector can't read a derived table ([ADR-0019](../../docs/adr/0019-runner-on-the-prototype-cluster.md)).
4. The job runs in batch mode on the session cluster. `--target staging` (the default of this command line) writes `<storage root>/_staging/<run_id>/ingest_date=<date>/` (ADR-0004; publishing is Phase 5). `--target final` writes `<sink uri>/ingest_date=<date>/` with `INSERT OVERWRITE`, replacing the partition: that is what Airflow asks for until the publisher exists.

## Try it (Codespace)

Rebuild the JobManager once (PyYAML and the new mounts), start the example sources, and save a connection and a job in the Web UI (the runner reads the Web UI's working copy, `pipelines/`):

```bash
docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build flink-jobmanager
alias jm='docker compose -f infrastructure/non-prod/docker-compose.yml exec flink-jobmanager'

jm flink run -py /opt/runner/main.py \
  --job /opt/ingestion/pipelines/jobs/shop-orders-daily.yaml \
  --output-root file:///opt/ingestion/spike-out
```

The run prints a `RUNNER_RESULT {...}` line. Read the output back (pandas through pyarrow):

```bash
jm python /opt/spikes/phase-2/check_parquet.py /opt/ingestion/spike-out/_staging/<run_id>
```

Options: `--run-id`, `--ingest-date` (default today, UTC), `--target {staging,final}`, `--connections-dir` (default: `connections/` next to the job's folder), `--templates-dir`, `--no-wait`. Without `--output-root` the sink's `abfss://` location is used, which needs the account key in the Flink configuration (`ADLS_ACCOUNT_KEY`) and a storage account without soft delete ([ADR-0019](../../docs/adr/0019-runner-on-the-prototype-cluster.md)).

**On a cluster:** Airflow runs it as `PythonDriver` through the JobManager's REST API, with the runner, the templates and the merged `pipelines/` mounted on the JobManager (orchestration `dags/common/flink_rest.py`). The run prints `RUNNER_RESULT {...}` with the Flink job id.

## Limits of this first version

- Parquet only; Delta waits for the Delta spike (ADR-0004).
- `snapshot_column` is rejected with a clear error.
- Only plain single-table queries (`SELECT <columns or *> FROM <table>`): joins, filters, expressions, aliases and subqueries are refused with a message. The `JdbcSource` fallback of ADR-0010 lifts this.
- `--target final` has no atomic publish, `_SUCCESS` or manifest: a failed run can leave its partition half written until the next run replaces it.
- `target_file_size_mb` is not applied: Flink's Parquet writer rolls files on checkpoints, so a batch job writes one file per sink task. A partitioned scan gives several files.
- Timestamps are declared `TIMESTAMP(3)` (milliseconds); spike 11 decides whether to keep more precision.
- Unconstrained numerics (PostgreSQL `numeric` without precision) and types without a Flink equivalent fail before the job starts, naming the column and asking for a cast in the query.
- The password is part of the job graph that goes to the TaskManagers (spike 7 looks for a way around it).
- First run on a cluster (2026-11-06): MySQL (`shop.customers`) → Parquet on ADLS Gen2, submitted by Airflow. PostgreSQL and SQL Server are not run on a cluster yet. The derived table `(<query>) AS q` fails on MySQL (spike 5); the plain table works.

## Develop

```bash
pip install -e "code/runner[dev]"
cd code/runner && pytest -q && ruff check . && mypy ingestion_runner
```

The tests are offline (plan, type mapping, SQL); PyFlink is only imported when a job runs.
