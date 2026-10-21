# Configuration Spec

Status: **Draft (Phase 0)**. This spec is formalized as JSON Schemas in Phase 2; until then this document is the reference.

All configuration is YAML. Every document has a `kind` and a `name`. Names are lowercase kebab-case (`^[a-z][a-z0-9-]{2,62}$`) and unique per kind. Templates are referenced as `<name>@<version>`.

| Kind | Location | Owner |
|---|---|---|
| `SourceTemplate` | `templates/sources/<name>.yaml` | Platform team |
| `SinkTemplate` | `templates/sinks/<name>.yaml` | Platform team |
| `Connection` | `connections/<name>.yaml` | DE team |
| `IngestionJob` | `jobs/<name>.yaml` or created through the API/UI | Users, data team |

## Common types

| Type | Meaning |
|---|---|
| `string`, `int`, `bool` | Scalars |
| `enum` | One of `values` |
| `secret_ref` | `kv://<vault-name>/<secret-name>`. Resolved at runtime only; never stored resolved |
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

### `templates/sources/sqlserver.yaml`

```yaml
kind: SourceTemplate
name: sqlserver
version: 1
connector: jdbc
dialect: tsql
driver: com.microsoft.sqlserver.jdbc.SQLServerDriver
url: >-
  jdbc:sqlserver://{{ host }}:{{ port }};databaseName={{ database }};
  encrypt={{ encrypt }};trustServerCertificate={{ trust_server_certificate }};
  applicationIntent=ReadOnly

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

### `templates/sources/postgresql.yaml` (differences)

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

### `templates/sources/bigquery.yaml` (differences)

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
  credentials:     { type: secret_ref, description: "Service account JSON; omit to use workload identity" }
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

### `templates/sinks/adls_parquet.yaml`

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

### `templates/sinks/adls_delta.yaml`

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

One onboarded source. Created by the DE team through a pull request (or the UI in Phase 6).

| Field | Required | Description |
|---|---|---|
| `kind` | yes | `Connection` |
| `name` | yes | |
| `template` | yes | `<source-template>@<version>` |
| `owner` | yes | Team responsible for the connection |
| `params` | yes | Values for the template's `connection_params` |
| `limits.max_concurrent_runs` | no | Default `2` |
| `limits.max_partition_num` | no | Caps `read.partition_num` for every job on this connection |
| `limits.run_window` | no | Allowed local time window, for example `"19:00-06:00"` |
| `access.groups` | no | Entra ID groups allowed to create jobs on this connection |

```yaml
kind: Connection
name: crm-sqlserver-prod
template: sqlserver@1
owner: de-team
params:
  host: crm-ag-listener.internal
  database: CRM
  username: svc_ingest_ro
  password: kv://kv-dataplatform/crm-sqlserver-ro
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
| `name` | yes | |
| `owner` | yes | Team or person accountable for the job |
| `connection` | yes | `Connection` name |
| `source.query` | yes | Read-only SQL in the connection's dialect |
| `source.read` | no | Overrides for the template's `read_params` |
| `sink.template` | yes | `<sink-template>@<version>` |
| `sink.params` | yes | Values for the sink template's `params` |
| `verify.row_count` | no | `exact` (default), `tolerance`, or `skip` |
| `verify.tolerance_pct` | with `tolerance` | Allowed relative difference, for example `0.1` |
| `runtime.parallelism` | no | Default derived from `partition_num` |
| `runtime.taskmanager` | no | `{ cpu, memory }`, default `{ cpu: 2, memory: 4g }` |
| `runtime.timeout` | no | Default `2h` |
| `runtime.retries` | no | Default `1` |
| `schedule` | no | Cron expression; used from Phase 5 by the Airflow DAG generator, ignored before |
| `tags` | no | Free-form labels |

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

`POST /jobs/{name}/runs` or `ingestctl run <name>`:

| Field | Default | Description |
|---|---|---|
| `ingest_date` | Today in `Asia/Ho_Chi_Minh` | Target partition; any past date enables backfill |
| `triggered_by` | Caller identity | `user:<id>`, `airflow:<dag_id>`, `cli:<user>` |
| `dry_run` | `false` | Validate, preflight and render only |

---

## Rendered output (per run, never edited by hand)

- **Resolved job spec** (`job.yaml`): all templates expanded, preflight results inlined (schema, bounds, expected count), secrets still as environment variable placeholders.
- **`FlinkDeployment` manifest** rendered from `templates/runtime/flinkdeployment.yaml.j2`.

Both are stored in `runs` for audit and can be re-submitted with `ingestctl submit --run <run_id>`.

```yaml
apiVersion: flink.apache.org/v1beta1
kind: FlinkDeployment
metadata:
  name: ingest-<run_id>
  namespace: ingestion
  labels:
    ingestion/run-id: <run_id>
    ingestion/job: crm-customers-daily
spec:
  image: <registry>/ingestion-runner:<version>
  flinkVersion: v1_20
  serviceAccount: flink-ingestion
  flinkConfiguration:
    execution.runtime-mode: BATCH
    taskmanager.numberOfTaskSlots: "2"
  jobManager:  { resource: { cpu: 1, memory: 2048m } }
  taskManager: { resource: { cpu: 2, memory: 4096m } }
  podTemplate: {}   # mounts the job spec ConfigMap and Key Vault secrets as env
  job:
    jarURI: local:///opt/flink/usrlib/ingestion-runner.jar
    args: ["--spec", "/opt/spec/job.yaml"]
    parallelism: 8
    upgradeMode: stateless
```
