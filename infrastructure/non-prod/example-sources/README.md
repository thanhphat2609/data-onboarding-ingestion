# Example sources (non-prod only)

Test sources for demos and spikes: SQL Server, PostgreSQL, MySQL and a REST API, each with a read-only login. They play the company's real systems, so they live outside the platform:

- The platform stack (`../docker-compose.yml`) doesn't start them. You start them by hand, as the first step of a demo.
- The repository has no example connection or job files: you type them into the Web UI by hand, as you would in prod.
- Prod never has them. There, connections point at the real systems.

Each source is a folder with its own `docker-compose.yml`, `.env` (from `.env.example`, filled by `../bootstrap.sh`) and seed. The `docker-compose.yml` here only includes the four, to start them all at once.

| Folder | Host name | Template | Database / endpoint | Read-only login | Secret (`env://`) |
|---|---|---|---|---|---|
| [sqlserver/](sqlserver/) | `sqlserver` (port 1433 on the host) | `sqlserver@1` | `crm` | `svc_ingest_ro` | `CRM_SQLSERVER_RO_PASSWORD` |
| [postgresql/](postgresql/) | `postgres-source` | `postgresql@1` | `sales` | `svc_ingest_ro` | `SALES_POSTGRES_RO_PASSWORD` |
| [mysql/](mysql/) | `mysql-source` | `mysql@1` | `shop` | `svc_ingest_ro` | `SHOP_MYSQL_RO_PASSWORD` |
| [rest-api/](rest-api/) | `api-source` | `rest_api@1` | `http://api-source:8000/v1/orders` (paged JSON, a 429 on every 7th request) | bearer token | `SHOP_API_TOKEN` |

SQL Server needs about 2 GB of memory; start only the sources you demo.

The three databases share one model, so one connection serves several jobs (one job per table): `segments` (3 rows), `customers` (10,000 rows) and `orders` (5,000 rows; `bash infrastructure/non-prod/example-sources/seed-large.sh` refills it with 10M rows for throughput tests). On a source that was already running, run `docker compose ... down -v` for it once to get the 5,000 orders (PostgreSQL and MySQL seed only an empty volume).

The platform and these sources meet on the Docker network `ingestion-sources`, which `../bootstrap.sh` creates.

## Demo, step by step

Saving in the Web UI opens a pull request on [data-onboarding-orchestration](https://github.com/thanhphat2609/data-onboarding-orchestration) ([ADR-0017](../../../docs/adr/0017-ui-opens-pull-requests-on-orchestration.md)); the job becomes a DAG after the merge. This repository only has the Web UI, the API and Flink.

### 0. Platform running, token set

In a Codespace, `bootstrap.sh` and the platform stack start by themselves. Elsewhere:

```bash
bash infrastructure/non-prod/bootstrap.sh
docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build
```

Saving needs a GitHub token for the orchestration repository: a fine-grained personal access token limited to it, with Contents and Pull requests (read and write). In a Codespace add it as the user secret `ORCHESTRATION_GITHUB_TOKEN` (and give it access to this repository), then rebuild the Codespace; elsewhere put it in `infrastructure/non-prod/.env`. Without a token, set `SAVE_MODE=disk` in `.env` to keep the files local only.

Start Airflow from the orchestration repository (port 8080) if you want to see the DAG after the merge.

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

The connection refers to the password as `env://NAME`; the value lives in `infrastructure/non-prod/sources.env`, which `bootstrap.sh` filled from the source's `.env`. Show the key names in it (not the values).

*Prod:* the Data Team adds the GitHub secret `NAME` and runs **Actions → Deploy** ([ADR-0013](../../../docs/adr/0013-prod-settings-in-github.md)).

### 3. Create the connection

Web UI (port 3000) → **Connections** → **New connection**. Pick the template and fill in the table below, then **Test connection** (databases only) and **Save connection**.

| Source | Template | Host | Database | Login | Password reference |
|---|---|---|---|---|---|
| SQL Server | `sqlserver@1` | `sqlserver` | `crm` | `svc_ingest_ro` | `env://CRM_SQLSERVER_RO_PASSWORD` |
| PostgreSQL | `postgresql@1` | `postgres-source` | `sales` | `svc_ingest_ro` | `env://SALES_POSTGRES_RO_PASSWORD` |
| MySQL | `mysql@1` | `mysql-source` | `shop` | `svc_ingest_ro` | `env://SHOP_MYSQL_RO_PASSWORD` |
| REST API | `rest_api@1` | `base_url` `http://api-source:8000/v1`, auth `bearer` | | | token `env://SHOP_API_TOKEN` |

The toast shows **Pull request #N opened** with a link. Open it: the file holds only the `env://` reference, never the password. The connection is usable in the job wizard at once (the API keeps a working copy), before anyone merges.

### 4. Create the ingestion jobs

One connection, several jobs: the three databases each have `segments`, `customers` and `orders`. **Ingestion jobs** → **New job**: pick the connection, write the query (for example `SELECT * FROM dbo.customers` on SQL Server, `SELECT * FROM public.orders` on PostgreSQL), **Validate** and **Preview**, then the destination, the schedule, and **Save job**. Create a second job on the same connection for another table. Each save opens its own pull request.

For the REST API, the job sets `endpoint`, `pagination` and a Flink SQL query over `landing` ([ADR-0015](../../../docs/adr/0015-rest-api-source-via-redpanda.md)).

### 5. Merge, then watch Airflow

CI in the orchestration repository validates the files; merge the pull requests. Airflow shows `ingest__<job>` within about a minute (new DAGs start paused):
- database jobs: `validate → submit → wait`;
- API jobs: `validate → fetch → submit → wait`.

Unpause and trigger it in Airflow; the Web UI's **Airflow** button on the jobs page opens the DAG. Until the runner exists (roadmap Phase 4), `submit` runs Flink's WordCount smoke job. The real read is shown with the Phase 2 spikes ([code/spikes/phase-2/](../../../code/spikes/phase-2/README.md)).

### Reset

Close the pull requests you opened, and delete `pipelines/` here (the working copy). Stop the example sources and drop their data:

```bash
docker compose -f infrastructure/non-prod/example-sources/docker-compose.yml down -v
```
