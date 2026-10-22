# Configuration Spec

Status: **Draft (Phase 0)**. This spec is formalized as JSON Schemas in Phases 1 (SQL Server, `IngestionJob`) and 3 (all kinds); until then this document is the reference. The files under `code/templates/` are the source of truth for template contents; the snippets below are copies.

All configuration is YAML. Every document has a `kind` and a `name`. Names are lowercase kebab-case (`^[a-z][a-z0-9-]{2,62}$`) and unique per kind. Templates are referenced as `<name>@<version>`.

| Kind | Location | Owner |
|---|---|---|
| `SourceTemplate` | `code/templates/sources/<name>.yaml` | Platform team |
| `SinkTemplate` | `code/templates/sinks/<name>.yaml` | Platform team |
| `Connection` | `pipelines/connections/<name>.yaml` | DE team |
| `IngestionJob` | `pipelines/jobs/<name>.yaml`, written by hand or by the UI; one file = one Airflow DAG | Users, data team |

The file name must equal `name` (`pipelines/connections/<name>.yaml`, `pipelines/jobs/<name>.yaml`); the API, `ingestctl validate` and CI reject a mismatch. A job's `name` cannot change once the job exists, because it is also the DAG id ([ADR-0008](adr/0008-airflow-dag-per-job.md)).

## Common types

| Type | Meaning |
|---|---|
| `string`, `int`, `bool` | Scalars |
| `enum` | One of `values` |
| `secret_ref` | `env://<VAR>` (non-prod) or `kv://<vault-name>/<secret-name>` (prod). Resolved at runtime only; never stored resolved |
| `duration` | `30s`, `15m`, `2h` |
| `list` | List of scalars |

Template parameters are declared as `<param>: { type, required, default, min, max, values, description }`.

---

## SourceTemplate

Describes a source **type**. Adding a new database of an existing type does not require a new template.

| Field | Required | Description |
|---|---|---|
| `kind` | yes | `SourceTemplate` |
| `name`, `version` | yes | Version is an integer; bump on any breaking change |
| `connector` | yes | `jdbc` or `bigquery` |
| `dialect` | yes | sqlglot dialect: `tsql`, `postgres`, `bigquery` |
| `driver` | jdbc | JDBC driver class |
| `url` | jdbc | Jinja template for the JDBC URL |
| `connection_params` | yes | Parameters a `Connection` must provide |
| `read_params` | yes | Parameters an `IngestionJob` may set under `source.read` |
| `preflight` | yes | Dialect-specific SQL templates: `preview`, `count`, `bounds`. `{{ query }}` is an AST-rewritten query, never raw user text |
| `type_mapping` | yes | Source type → Flink SQL type |
| `unsupported_types` | no | Types rejected at preflight with a `CAST` suggestion |
| `runtime_env` | no | Environment variables the runner needs (mapped from secrets) |

### `code/templates/sources/sqlserver.yaml`

```yaml
kind: SourceTemplate
name: sqlserver
version: 1
connector: jdbc
dialect: tsql
driver: com.microsoft.sqlserver.jdbc.SQLServerDriver
url: "jdbc:sqlserver://{{ host }}:{{ port }};databaseName={{ database }};encrypt={{ encrypt }};trustServerCertificate={{ trust_server_certificate }};applicationIntent=ReadOnly"

connection_params:
  host:                     { type: string, required: true }
  port:                     { type: int, default: 1433 }
  database:                 { type: string, required: true }
  username:                 { type: string, required: true }
  password:                 { type: secret_ref, required: true }
  encrypt:                  { type: bool, default: true }
  trust_server_certificate: { type: bool, default: false }

read_params:
  fetch_size:       { type: int, default: 10000, min: 100, max: 100000 }
  partition_column: { type: string, description: "Numeric or date output column" }
  partition_num:    { type: int, default: 4, min: 1, max: 32 }
  snapshot_column:  { type: string, description: "Adds <column> <= run_ts" }

preflight:
  preview: "SELECT TOP ({{ limit }}) * FROM ({{ query }}) AS q"
  count:   "SELECT COUNT_BIG(*) FROM ({{ query }}) AS q"
  bounds:  "SELECT MIN({{ column }}), MAX({{ column }}) FROM ({{ query }}) AS q"

type_mapping:
  bit: BOOLEAN
  tinyint: SMALLINT
  smallint: SMALLINT
  int: INT
  bigint: BIGINT
  decimal: "DECIMAL({{ precision }}, {{ scale }})"
  numeric: "DECIMAL({{ precision }}, {{ scale }})"
  money: DECIMAL(19, 4)
  real: FLOAT
  float: DOUBLE
  char: STRING
  varchar: STRING
  nchar: STRING
  nvarchar: STRING
  uniqueidentifier: STRING
  date: DATE
  datetime: TIMESTAMP(3)
  datetime2: "TIMESTAMP({{ scale }})"
  varbinary: BYTES

unsupported_types: [sql_variant, hierarchyid, geography, geometry, xml, datetimeoffset]

runtime_env:
  SRC_USERNAME: "{{ username }}"
  SRC_PASSWORD: "{{ password }}"
```

### `code/templates/sources/postgresql.yaml` (differences)

```yaml
kind: SourceTemplate
name: postgresql
version: 1
connector: jdbc
dialect: postgres
driver: org.postgresql.Driver
url: "jdbc:postgresql://{{ host }}:{{ port }}/{{ database }}?sslmode={{ sslmode }}"

connection_params:
  host:     { type: string, required: true }
  port:     { type: int, default: 5432 }
  database: { type: string, required: true }
  username: { type: string, required: true }
  password: { type: secret_ref, required: true }
  sslmode:  { type: enum, values: [require, verify-ca, verify-full], default: require }

read_params:
  fetch_size:       { type: int, default: 10000 }
  auto_commit:      { type: bool, default: false, description: "Must be false for fetch_size to stream" }
  partition_column: { type: string }
  partition_num:    { type: int, default: 4, min: 1, max: 32 }
  snapshot_column:  { type: string }

preflight:
  preview: "SELECT * FROM ({{ query }}) AS q LIMIT {{ limit }}"
  count:   "SELECT COUNT(*) FROM ({{ query }}) AS q"
  bounds:  "SELECT MIN({{ column }}), MAX({{ column }}) FROM ({{ query }}) AS q"

# uuid, json, jsonb, arrays -> STRING; timestamptz -> TIMESTAMP_LTZ(6)
```

### `code/templates/sources/bigquery.yaml` (differences)

```yaml
kind: SourceTemplate
name: bigquery
version: 1
connector: bigquery
dialect: bigquery

connection_params:
  project_id:      { type: string, required: true }
  location:        { type: string, default: US }
  billing_project: { type: string }
  credentials:     { type: secret_ref, description: "Service account JSON; omit to use the host identity (prod)" }
  temp_dataset:    { type: string, required: true, description: "Dataset for materialized query results" }

read_params:
  max_streams:       { type: int, default: 8 }
  max_bytes_billed:  { type: int, description: "Dry-run limit; run is rejected above it" }

# Query mode: CREATE TABLE `{{ temp_dataset }}.ingest_{{ run_id }}`
#   OPTIONS (expiration_timestamp = TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR))
#   AS {{ query }}
```

---

## SinkTemplate

| Field | Required | Description |
|---|---|---|
| `kind` | yes | `SinkTemplate` |
| `name`, `version` | yes | |
| `format` | yes | `parquet` or `delta` |
| `uri` | yes | Jinja template for the table root URI |
| `params` | yes | Parameters an `IngestionJob` sets under `sink.params` |
| `partition_by` | yes | Always starts with `ingest_date` in v1 |
| `publish` | yes | Publisher strategy: `rename_partition` (Parquet) or `delta_commit` (Delta) |

### `code/templates/sinks/adls_parquet.yaml`

```yaml
kind: SinkTemplate
name: adls_parquet
version: 1
format: parquet
uri: "abfss://{{ container }}@{{ storage_account }}.dfs.core.windows.net/parquet/{{ path }}"

params:
  storage_account:     { type: string, required: true }
  container:           { type: string, default: raw }
  path:                { type: string, required: true, description: "<system>/<schema>/<table>" }
  compression:         { type: enum, values: [snappy, zstd], default: snappy }
  target_file_size_mb: { type: int, default: 256 }

partition_by: [ingest_date]
publish: rename_partition
```

### `code/templates/sinks/adls_delta.yaml`

```yaml
kind: SinkTemplate
name: adls_delta
version: 1
format: delta
uri: "abfss://{{ container }}@{{ storage_account }}.dfs.core.windows.net/delta/{{ path }}"

params:
  storage_account:     { type: string, required: true }
  container:           { type: string, default: raw }
  path:                { type: string, required: true }
  target_file_size_mb: { type: int, default: 256 }
  schema_evolution:    { type: enum, values: [fail, add_columns], default: fail }

partition_by: [ingest_date]
publish: delta_commit
```

---

## Connection

One onboarded source. Created by the DE team through the UI or a pull request.

| Field | Required | Description |
|---|---|---|
| `kind` | yes | `Connection` |
| `name` | yes | |
| `template` | yes | `<source-template>@<version>` |
| `owner` | yes | Team responsible for the connection |
| `params` | yes | Values for the template's `connection_params` |
| `limits.max_concurrent_runs` | no | Default `2`; becomes the size of the Airflow pool `conn__<name>` |
| `limits.max_partition_num` | no | Caps `read.partition_num` for every job on this connection |
| `limits.run_window` | no | Allowed local time window, for example `"19:00-06:00"` |
| `access.groups` | no | Entra ID groups allowed to create jobs on this connection (enforced once SSO exists, Phase 6) |

```yaml
kind: Connection
name: crm-sqlserver-prod
template: sqlserver@1
owner: de-team
params:
  host: crm-ag-listener.internal
  database: CRM
  username: svc_ingest_ro
  password: kv://kv-dataplatform/crm-sqlserver-ro   # non-prod: env://CRM_SQLSERVER_PASSWORD
limits:
  max_concurrent_runs: 2
  max_partition_num: 8
  run_window: "19:00-06:00"
access:
  groups: [data-team, analytics]
```

---

## IngestionJob

| Field | Required | Description |
|---|---|---|
| `kind` | yes | `IngestionJob` |
| `name` | yes | Immutable; DAG id is `ingest__<name>`. Recommended pattern `<system>-<dataset>-<frequency>` |
| `owner` | yes | Team or person accountable for the job |
| `connection` | yes | `Connection` name |
| `source.query` | yes | Read-only SQL in the connection's dialect |
| `source.read` | no | Overrides for the template's `read_params` |
| `sink.template` | yes | `<sink-template>@<version>` |
| `sink.params` | yes | Values for the sink template's `params` |
| `verify.row_count` | no | `exact` (default), `tolerance`, or `skip` |
| `verify.tolerance_pct` | with `tolerance` | Allowed relative difference, for example `0.1` |
| `runtime.parallelism` | no | Default derived from `partition_num`; capped by the free task slots of the session cluster |
| `runtime.timeout` | no | Default `2h` |
| `runtime.retries` | no | Default `1` |
| `schedule` | no | Cron expression or Airflow preset (`@daily`); becomes the DAG schedule. Omitted: manual runs only |
| `tags` | no | Free-form labels; added to the DAG tags |

### DAG mapping

The DAG factory turns each job into one DAG ([ADR-0008](adr/0008-airflow-dag-per-job.md)):

| Job field | DAG setting |
|---|---|
| `name` | `dag_id = ingest__<name>` |
| `schedule` | `schedule`; `None` when omitted |
| `owner` | DAG owner, tag `owner:<owner>` |
| `connection` | Tag `connection:<connection>`, pool `conn__<connection>` |
| connection template | Tag `source:<template>` |
| `tags` | DAG tags, plus `ingestion` |
| `runtime.retries`, `runtime.timeout` | Whole-run retries and timeout |
| `sink` | Outlet `Asset(<table root URI>)` on the `publish` task, for downstream DAGs |

Every DAG uses `max_active_runs=1` and `catchup=False`.

```yaml
kind: IngestionJob
name: crm-customers-daily
owner: data-team
connection: crm-sqlserver-prod
source:
  query: |
    WITH active AS (
      SELECT customer_id, segment_id, updated_at
      FROM dbo.customers
      WHERE is_deleted = 0
    )
    SELECT a.customer_id, a.updated_at, s.segment_name
    FROM active AS a
    JOIN dbo.segments AS s ON s.segment_id = a.segment_id
  read:
    partition_column: customer_id
    partition_num: 8
sink:
  template: adls_delta@1
  params:
    storage_account: stdatalakeprod
    path: crm/dbo/customers
verify:
  row_count: exact
runtime:
  timeout: 1h
  retries: 1
schedule: "0 2 * * *"
tags: [crm, daily]
```

### Run request

"Run now" in the UI, `POST /jobs/{name}/runs` or `ingestctl run <name>`. All of them trigger the DAG `ingest__<name>` through the Airflow REST API and pass the fields below as DAG run `conf`:

| Field | Default | Description |
|---|---|---|
| `ingest_date` | Logical date of the DAG run in `Asia/Ho_Chi_Minh` | Target partition; any past date enables backfill |
| `triggered_by` | Caller identity | `user:<id>`, `schedule`, `cli:<user>` |
| `dry_run` | `false` | Validate, preflight and render only |

---

## Rendered output (per run, never edited by hand)

- **Resolved job spec** (`job.yaml`): all templates expanded, preflight results inlined (schema, bounds, expected count), secrets still as references. Written to the run directory shared by Airflow and the Flink JobManager.
- **Flink submission request** for the session cluster ([ADR-0007](adr/0007-flink-standalone-session-cluster.md)), rendered with the defaults in `code/templates/runtime/`.

Both are stored in `runs` for audit and can be re-submitted with `ingestctl submit --run <run_id>`.

```http
POST /jars/<flink-python-jar-id>/run
Content-Type: application/json

{
  "entryClass": "org.apache.flink.client.python.PythonDriver",
  "parallelism": 8,
  "programArgsList": ["-py", "/opt/ingestion/runner/main.py", "--spec", "/opt/ingestion/runs/<run_id>/job.yaml"]
}
```

The response contains the Flink job id; the `wait` task polls `GET /jobs/<job_id>` until the job reaches a terminal state.
