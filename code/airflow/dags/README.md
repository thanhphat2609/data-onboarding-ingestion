# DAGs

Mounted on Airflow at `/opt/airflow/dags/ingestion/` ([ADR-0008](../../../docs/adr/0008-airflow-dag-per-job.md)).

## `ingestion_dag_factory.py`

One Python file that turns every `pipelines/jobs/<name>.yaml` into its own DAG `ingest__<name>`. Nobody writes a DAG per job; the Web UI only writes YAML.

| Job field | DAG |
|---|---|
| `name` | `dag_id = ingest__<name>` |
| `schedule` | schedule (`Asia/Ho_Chi_Minh`); no schedule means manual runs only |
| `owner`, `connection`, connection template, `tags` | owner and tags `ingestion`, `owner:…`, `connection:…`, `source:…` |
| `connection` | pool `conn__<connection>` on every task |
| `runtime.timeout` | the Flink job is cancelled after it |

Every DAG has `max_active_runs=1`, `catchup=False` and an `ingest_date` parameter in the trigger form (empty: the run's logical date).

**Validation per file:** the job and its connection are checked against `code/templates/schemas/*.json`, the file name must equal `name`, and the connection and templates must exist. An invalid file is skipped with a one-line reason in the DAG processor log; every other DAG keeps loading.

**Tasks (Phase 1):** `validate → submit → wait`. `submit` runs Flink's bundled WordCount example on the session cluster to prove the wiring; the PyFlink runner replaces it in Phase 4, and preflight, verify and publish (with the table Asset) arrive in Phase 5.

## `../scripts/sync_pools.py`

Prints a pool `conn__<name>` per connection file, sized by `limits.max_concurrent_runs`, for `airflow pools import`. Non-prod runs it on every Airflow start.
