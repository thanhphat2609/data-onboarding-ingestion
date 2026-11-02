# Ingestion runner

One PyFlink job (ADR-0010) that copies the result of an `IngestionJob`'s query to Parquet. It reads the YAML files as they are merged (the job, its connection, the two templates); there is no intermediate spec.

What a run does:

1. `plan.py` loads the job, its connection and the templates, and resolves the password from its `env://` reference on the JobManager.
2. `jdbc_meta.py` asks the source for the query's columns (a statement with `WHERE 1 = 0`) and, with a `partition_column`, for its MIN and MAX. It uses the JDBC drivers of the Flink JVM through py4j, so nothing is installed besides PyYAML.
3. `flink_sql.py` builds three statements: the JDBC source over `(<query>) AS q`, the filesystem Parquet sink, and `INSERT ... SELECT` with the audit columns `ingest_date`, `_ingest_run_id`, `_ingested_at`.
4. The job runs in batch mode on the session cluster and writes to `<storage root>/_staging/<run_id>/ingest_date=<date>/` (ADR-0004). Publishing from staging is Phase 5.

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

Options: `--run-id`, `--ingest-date` (default today, UTC), `--connections-dir` (default: `connections/` next to the job's folder), `--templates-dir`, `--no-wait`. Without `--output-root` the sink's `staging_uri` is used (`abfss://`), which needs the ADLS credentials in the Flink configuration (spike 8).

## Limits of this first version

- Parquet only; Delta waits for the Delta spike (ADR-0004).
- `snapshot_column` is rejected with a clear error.
- `target_file_size_mb` is not applied: Flink's Parquet writer rolls files on checkpoints, so a batch job writes one file per sink task. A partitioned scan gives several files.
- Timestamps are declared `TIMESTAMP(3)` (milliseconds); spike 11 decides whether to keep more precision.
- Unconstrained numerics (PostgreSQL `numeric` without precision) and types without a Flink equivalent fail before the job starts, naming the column and asking for a cast in the query.
- The password is part of the job graph that goes to the TaskManagers (spike 7 looks for a way around it).
- Not yet run on a cluster. Whether the JDBC connector takes the derived table `(<query>) AS q` on each dialect is spike 5; the fallback is in ADR-0010.

## Develop

```bash
pip install -e "code/runner[dev]"
cd code/runner && pytest -q && ruff check . && mypy ingestion_runner
```

The tests are offline (plan, type mapping, SQL); PyFlink is only imported when a job runs.
