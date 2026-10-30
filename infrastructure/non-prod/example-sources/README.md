# Example sources (non-prod only)

Test sources for demos and spikes: SQL Server, PostgreSQL, MySQL and a REST API, each with a read-only login. They play the company's real systems, so they live outside the platform:

- The platform stack (`../docker-compose.yml`) doesn't start them. You start them by hand, as the first step of a demo.
- `pipelines/` starts empty: no connection points at them until you create one in the Web UI, step by step, as you would in prod.
- Prod never has them. There, connections point at the real systems.

Each source is a folder with its own `docker-compose.yml`, `.env` (from `.env.example`, filled by `../bootstrap.sh`) and seed. The `docker-compose.yml` here only includes the four, to start them all at once.

| Folder | Host name | Template | Database / endpoint | Read-only login | Secret (`env://`) |
|---|---|---|---|---|---|
| [sqlserver/](sqlserver/) | `sqlserver` (port 1433 on the host) | `sqlserver@1` | `crm` | `svc_ingest_ro` | `CRM_SQLSERVER_RO_PASSWORD` |
| [postgresql/](postgresql/) | `postgres-source` | `postgresql@1` | `sales` | `svc_ingest_ro` | `SALES_POSTGRES_RO_PASSWORD` |
| [mysql/](mysql/) | `mysql-source` | `mysql@1` | `shop` | `svc_ingest_ro` | `SHOP_MYSQL_RO_PASSWORD` |
| [rest-api/](rest-api/) | `api-source` | `rest_api@1` | `http://api-source:8000/v1/orders` (paged JSON, a 429 on every 7th request) | bearer token | `SHOP_API_TOKEN` |

SQL Server needs about 2 GB of memory; start only the sources you demo.

The three databases share one model: `segments`, `customers` (10,000 rows) and `orders` (empty until `bash infrastructure/non-prod/example-sources/seed-large.sh` fills it with 10M rows).

The platform and these sources meet on the Docker network `ingestion-sources`, which `../bootstrap.sh` creates.

## Demo, step by step

Each step says what happens in prod. Saving in prod opens a pull request ([ADR-0014](../../../docs/adr/0014-prod-save-flow.md), not built yet); here the Web UI writes the file directly. Everything else is the same.

### 0. Platform running

In a Codespace, `bootstrap.sh` and the platform stack start by themselves. Elsewhere:

```bash
bash infrastructure/non-prod/bootstrap.sh
```

```bash
docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build
```

Show that `pipelines/connections/` and `pipelines/jobs/` are empty, and that Airflow (port 8080) has no `ingest__` DAG.

### 1. The source exists

Start the source you demo. It plays "the CRM", "the sales database", and so on:

```bash
docker compose -f infrastructure/non-prod/example-sources/postgresql/docker-compose.yml up -d
```

Or all four at once:

```bash
docker compose -f infrastructure/non-prod/example-sources/docker-compose.yml up -d
```

Wait until it is `healthy` (`docker compose -f infrastructure/non-prod/example-sources/docker-compose.yml ps` lists every source, however it was started). SQL Server takes about a minute, then `sqlserver-seed` runs once and exits.

*Prod:* the system already exists. The DE team gets a read-only login from its owner.

### 2. The secret

The connection refers to the password as `env://NAME`; the value lives in `infrastructure/non-prod/sources.env`, which `bootstrap.sh` filled from the source's `.env` (e.g. `postgresql/.env`). Show the key names in it (not the values).

*Prod:* the Data Team adds the GitHub secret `NAME` and runs **Actions → Deploy**, which writes `sources.env` on VM 1 ([ADR-0013](../../../docs/adr/0013-prod-settings-in-github.md)). For a source that isn't in the file yet, here: add the line to `sources.env`, then run `docker compose -f infrastructure/non-prod/docker-compose.yml up -d` to recreate the containers that read it.

### 3. Create the connection

Web UI (port 3000) → **Connections** → **New connection**. Pick the template and fill in the values of the example file, then **Test connection** (databases only; the API template has no live test yet) and **Save connection**.

| Source | Example to copy |
|---|---|
| SQL Server | [examples/connections/crm-sqlserver-nonprod.yaml](examples/connections/crm-sqlserver-nonprod.yaml) |
| PostgreSQL | [examples/connections/sales-postgresql-nonprod.yaml](examples/connections/sales-postgresql-nonprod.yaml) |
| MySQL | [examples/connections/shop-mysql-nonprod.yaml](examples/connections/shop-mysql-nonprod.yaml) |
| REST API | [examples/connections/shop-api-nonprod.yaml](examples/connections/shop-api-nonprod.yaml) |

The UI shows `Saved pipelines/connections/<name>.yaml`. Show the file: the password is only a reference.

*Prod:* **Save** opens a pull request with that file; CI validates it, the Data Team reviews and merges.

### 4. Create the ingestion job

**Ingestion jobs** → **New job**: pick the connection, paste the query, **Validate** and **Preview** (databases), then the destination, the schedule, and **Save job**.

| Source | Example to copy | What it shows |
|---|---|---|
| SQL Server | [examples/jobs/crm-customers-daily.yaml](examples/jobs/crm-customers-daily.yaml) | Table mode, partitioned read |
| PostgreSQL | [examples/jobs/sales-orders-daily.yaml](examples/jobs/sales-orders-daily.yaml) | Table mode, partitioned read |
| MySQL | [examples/jobs/shop-customers-by-segment-daily.yaml](examples/jobs/shop-customers-by-segment-daily.yaml) | Query mode (a JOIN) |
| REST API | [examples/jobs/shop-api-orders-daily.yaml](examples/jobs/shop-api-orders-daily.yaml) | `endpoint`, `pagination`, and Flink SQL over `landing` ([ADR-0015](../../../docs/adr/0015-rest-api-source-via-redpanda.md)) |

*Prod:* a second pull request (`pipelines/jobs/` only). After the merge, the `pipelines/` sync puts it on VM 1 without a redeploy.

### 5. The DAG appears and runs

Airflow shows `ingest__<job>` within about 30 seconds. Its docs list the tasks:
- database jobs: `validate → submit → wait`;
- API jobs: `validate → fetch → submit → wait`.

Click **Run now** in the Web UI (it unpauses the DAG first), or unpause and **Trigger** it in Airflow.

For an API job, open the `fetch` log: it lists the pages, a retried 429, and `Landed N record(s) … offsets [start, end)`. The records are on Redpanda:

```bash
docker compose -f infrastructure/non-prod/docker-compose.yml exec redpanda rpk topic consume ingest.shop-api-orders-daily -n 3
```

Until the runner exists (roadmap Phase 4), `submit` runs Flink's WordCount smoke job. The real read is shown with the Phase 2 spikes ([code/spikes/phase-2/](../../../code/spikes/phase-2/README.md)).

### Reset

Delete the files you created in `pipelines/connections/` and `pipelines/jobs/`; the DAGs disappear on the next parse. Stop the example sources and drop their data:

```bash
docker compose -f infrastructure/non-prod/example-sources/docker-compose.yml down -v
```
