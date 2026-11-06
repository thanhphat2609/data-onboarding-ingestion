# ADR-0019: The runner on the prototype cluster: what it reads, where it writes, how it is started

- Status: Accepted (prototype)
- Date: 2026-11-06
- Amends: [ADR-0004](0004-lake-layout-and-delta-commit.md) (writes go straight to the table path until the publisher exists), [ADR-0010](0010-pyflink-runner.md) (query mode)

## Context

The first end-to-end run (Airflow → Flink on VM 1 and VM 2 → MySQL → ADLS Gen2) found five things the ADRs did not settle. All five were fixed to get a demo running; this ADR records them so the next phase starts from what happened and not from the plan.

## Decision

**How a run is started.** The Airflow task `submit` (orchestration repository, `dags/common/flink_rest.py`) uploads the `flink-python` jar once and runs `org.apache.flink.client.python.PythonDriver` through the JobManager's REST API, with `-py /opt/runner/main.py --job <file> --run-id … --ingest-date … --target final --no-wait`. The JobManager mounts the runner, the templates and the orchestration checkout's `pipelines/` read-only (`/opt/runner`, `/opt/ingestion/templates`, `/opt/ingestion/pipelines`). Airflow can only upload a jar it can read, so the one-shot service `flink-python-jar-init` copies the jar to the volume `ingestion-flink-examples` on every deploy (a Docker volume is filled from the image only the first time). `--no-wait` makes the REST call return once the job is submitted; the task `wait` follows the job. The runner prints its job id as text: a Java object there made `json.dumps` fail *after* the job was submitted, so Airflow reported a failure for a job that kept running.

**What it reads: plain `SELECT <columns or *> FROM <table>`.** Flink's JDBC connector quotes its `table-name` as one identifier, so the derived table `(<query>) AS q` of ADR-0010 fails on MySQL with *Identifier name '(SELECT …' is too long* (spike 5's question, answered "no" for MySQL). The runner now gives the connector the table of a plain single-table query (MySQL: the table name without the database, which the JDBC URL already holds) and reads the columns of the DDL. Joins, filters, expressions, aliases and subqueries are refused with a message that says so. The `JdbcSource` fallback of ADR-0010 is the way to lift this limit and is not built.

**Where it writes: the table path, replacing the partition.** There is no publisher (Phase 5), so a run that wrote to `_staging/<run_id>/` left its data where nothing reads it. `--target final` writes `abfss://<container>@<account>.dfs.core.windows.net/parquet/<path>/ingest_date=<date>/` with `INSERT OVERWRITE`, so a rerun of the same date replaces that partition's files instead of adding to them. This gives up the atomic rename, `_SUCCESS` and `_manifest.json` of ADR-0004: a failed run can leave a partition half written until the next run. `--target staging` (the CLI default) keeps the ADR-0004 layout for when the publisher exists; Airflow chooses with `INGESTION_RUNNER_TARGET`.

**How it reaches ADLS: the account key, in the Flink configuration.** `fs.azure.account.key.<account>.dfs.core.windows.net` is set in `FLINK_PROPERTIES` of the JobManager (VM 1) and the TaskManager (VM 2), from the secret `ADLS_ACCOUNT_KEY` and the variable `ADLS_STORAGE_ACCOUNT` of this repository (ADR-0013). This replaces "managed identity in prod" of the architecture for the prototype. The storage account must have **blob soft delete, container soft delete, versioning, change feed and point-in-time restore turned off**: the Hadoop ABFS driver bundled with Flink 1.20 speaks an older storage API, and Azure answers every request on an account with those features with `409 This endpoint does not support BlobStorageEvents or SoftDelete`. The job fails at its first storage check, before any data is written.

**Where the TaskManagers read from.** The JDBC source runs on the TaskManagers, not on the JobManager, so the TaskManagers must reach the sources. Prototype: the demo sources run on VM 1 ([prod/demo-sources.yml](../../infrastructure/prod/demo-sources.yml)) with ports 3306 and 5432 published and allowed from VM 2's address; VM 2's TaskManager resolves `mysql-source` and `postgres-source` to VM 1 (`extra_hosts`). The two VMs are in different virtual networks that use the same private range, so `FLINK_JOBMANAGER_ADDRESS` and `FLINK_TASKMANAGER_ADDRESS` are the public addresses, and the Flink ports (6123, 6124, 19092 towards VM 1; 6121, 6122 towards VM 2) are allowed between exactly those two addresses.

## Consequences

- A demo job must be a plain single-table `SELECT`. It writes to `parquet/<sink path>/ingest_date=<date>/`.
- The Flink UI shows 0 records for such a job: source, projection and sink run in **one chained task**, so nothing crosses a task boundary. A row count needs the Phase 5 verify step (Parquet footers); until then the size of the Parquet file in the container is the only sign.
- The account key is a prototype shortcut: it is in the Flink configuration (visible to anyone who can read the JobManager's config) and in GitHub secrets, and is rotated by the account. Key Vault and a managed identity replace it in Phase 6.
- Firewall: the full list of ports is in [infrastructure/prod/README.md](../../infrastructure/prod/README.md).

## Alternatives considered

- **Keep staging and build the publisher now.** The right end state (ADR-0004), but it needs an ADLS client in the Airflow image and a rename step; a prototype demo only needs the data in the table path.
- **Upgrade the ABFS driver instead of turning soft delete off.** Needs a newer Hadoop than the one Flink 1.20's plugin bundles; a larger change than a storage setting.
- **Run a TaskManager on VM 1 as well, next to the sources.** Hides the network question the two-VM layout has to answer anyway.
