# Infrastructure

Everything that defines containers and environments ([ADR-0009](../docs/adr/0009-environments.md)).

```
docker/ui/       Web UI image (static build served by nginx, proxies /api)
docker/api/      Ingestion API image (code/control-plane)
docker/flink/    Flink image: JDBC connector and drivers, Parquet, ADLS plugin; target jobmanager adds PyFlink
non-prod/        One Compose project with the platform's services, for GitHub Codespaces
non-prod/example-sources/  Test sources (SQL Server, PostgreSQL, MySQL, a REST API), started by hand for demos
prod/            Two VMs, deployed by GitHub Actions (draft until the VMs exist, see prod/README.md)
```

Airflow uses `docker/airflow/` (the upstream image plus `confluent-kafka` for API jobs, [ADR-0015](../docs/adr/0015-rest-api-source-via-redpanda.md)); Flink uses `docker/flink/` from Phase 2.

## Non-prod

| Service | Port | Notes |
|---|---|---|
| Web UI | 3000 | Calls the Ingestion API through `/api` on the same port; `API_MODE=mock` in `.env` switches back to the in-browser mock |
| Ingestion API | 8000 | Writes `pipelines/connections/` and `pipelines/jobs/`, which Airflow reads; docs at `/api/docs` |
| Airflow | 8080 | Airflow 3 in standalone mode (one container); no login in non-prod. Runs the `fetch` task of API jobs |
| Flink web UI | 8081 | Session cluster: one JobManager, one TaskManager with 4 slots |
| Redpanda | internal | Landing for API sources: Kafka API `redpanda:9092`, one topic `ingest.<job>` per API job, 7-day retention. `docker compose -f infrastructure/non-prod/docker-compose.yml exec redpanda rpk topic consume ingest.<job> -n 3` |
| PostgreSQL | internal | Databases `airflow` and `platform`. The shared server or a local container, see below |

After pulling new services, run `bootstrap.sh` again: it adds new variables from the `.env.example` files to the existing `.env` files.

### Source secrets: `sources.env`

Connections reference passwords and tokens as `env://<VAR>`. The values are in `infrastructure/non-prod/sources.env`, read by the API (Test connection, preview), Airflow (the `fetch` task) and Flink. It is the non-prod twin of prod's `vm1/sources.env`, which the Deploy workflow writes from GitHub secrets ([ADR-0013](../docs/adr/0013-prod-settings-in-github.md)). `bootstrap.sh` fills the keys of `sources.env.example` from `example-sources/.env`. For another source, add its line to `sources.env`, then `docker compose -f infrastructure/non-prod/docker-compose.yml up -d` to recreate the containers that read it.

### Test sources: `example-sources/`

SQL Server, PostgreSQL, MySQL and a REST API, each with a read-only login, in its own folder with its own Compose file and `.env`. Like the company's real systems, they are not part of the platform: start them by hand, then onboard them in the Web UI. `pipelines/` starts empty. Demo, step by step, and the example connection and job files: [non-prod/example-sources/README.md](non-prod/example-sources/README.md).

```bash
docker compose -f infrastructure/non-prod/example-sources/docker-compose.yml up -d              # all of them
docker compose -f infrastructure/non-prod/example-sources/postgresql/docker-compose.yml up -d   # or one
```

They reach the platform over the Docker network `ingestion-sources`, created by `bootstrap.sh`.

### Metadata DB: shared server or local

The platform has one PostgreSQL server ([ADR-0011](../docs/adr/0011-shared-postgresql-server.md)). The [data-onboarding-agent](https://github.com/thanhphat2609/data-onboarding-agent) stack hosts it, with the databases `airflow`, `platform` and the agent's own `onboarding_agent`. Airflow joins that stack's Docker network `data-platform` and connects to `postgres:5432`. That only works when both stacks run on one Docker host.

| Where | `COMPOSE_PROFILES` in `.env` | Metadata DB |
|---|---|---|
| Standalone Codespace of this repo (default) | `local-db` | Local `postgres` container in this project, created as before |
| Both stacks on one host (demo VM 1: agent stack + Airflow + Flink JobManager) | empty | The agent stack's server. Start that stack first, and set `AIRFLOW_DB_PASSWORD` / `PLATFORM_DB_PASSWORD` to its `POSTGRES_AIRFLOW_PASSWORD` / `POSTGRES_PLATFORM_PASSWORD` |

How to connect to either one and check every table: [docs/postgresql.md](../docs/postgresql.md).

`bootstrap.sh` creates the `data-platform` network if it is missing, writes `COMPOSE_PROFILES=local-db` into a new `.env`, and adds it to an `.env` from before this change. In an existing Codespace, run `bash infrastructure/non-prod/bootstrap.sh` once after pulling. In shared mode Airflow waits up to 5 minutes for the server (`start.sh`), because Compose can't wait for a service of another project.

### Start

In a Codespace this happens automatically: `bootstrap.sh` runs once on create and the stack starts on every start. Elsewhere, from the repository root:

```bash
bash infrastructure/non-prod/bootstrap.sh     # creates the .env files with random secrets, and sources.env
docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build
```

The first start pulls about 3 GB of images; Airflow needs one to two minutes before it is healthy.

### Daily use

```bash
cd infrastructure/non-prod
docker compose ps                       # health of every service
docker compose logs -f airflow          # follow one service
docker compose stop                     # free memory, keep data
docker compose up -d --build ui         # rebuild the UI after changes
```

### Try a job

`pipelines/` starts empty. Start the example sources and create a connection and a job in the Web UI, step by step: [non-prod/example-sources/README.md](non-prod/example-sources/README.md). The job appears in Airflow as DAG `ingest__<name>` (new DAGs start paused); in Phase 1 a run executes Flink's WordCount example on the session cluster, visible in the Flink web UI.

After adding or changing a connection file by hand (the Web UI does this for you), refresh its pool (or restart Airflow):

```bash
docker compose exec airflow bash -c "python /opt/airflow/scripts/sync_pools.py > /tmp/pools.json && airflow pools import /tmp/pools.json"
```

To work on the UI with hot reload, run `npm ci && npm run dev -- --port 5173` in `code/ui/` (see [code/ui/README.md](../code/ui/README.md)).

### Reset

```bash
docker compose -f infrastructure/non-prod/docker-compose.yml down -v                    # deletes all data volumes
docker compose -f infrastructure/non-prod/example-sources/docker-compose.yml down -v    # and the example sources
rm -rf infrastructure/non-prod/data
```

On one host the two stacks don't clash: the agent stack publishes only `127.0.0.1:7860` (app) and `127.0.0.1:5432` (PostgreSQL); its SearXNG container has no host port. This stack uses 3000, 8000, 8080 and 8081 (and 1433 while the example sources run). Never combine `local-db` with the agent stack on one host: Airflow would see two `postgres` containers.

`.env` is kept; delete it as well to get new secrets. In shared mode `down -v` doesn't touch the metadata DB, which lives in the agent stack's volume. Reset it there, or drop and recreate the `airflow` database.

### Memory

Limits per service add up to about 7.5 GB: Airflow 2 GB, SQL Server 2 GB, TaskManager 1.75 GB, JobManager 1.25 GB, PostgreSQL 256 MB (local-db only), UI 64 MB. Use the 4-core / 16 GB Codespace machine type, and stop the Codespace when idle.
