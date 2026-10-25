# Infrastructure

Everything that defines containers and environments ([ADR-0009](../docs/adr/0009-environments.md)).

```
docker/ui/       Web UI image (static build served by nginx, proxies /api)
docker/api/      Ingestion API image (code/control-plane)
non-prod/        One Compose project with every service, for GitHub Codespaces
prod/            Phase 6, once the prod VMs exist
```

Airflow and Flink use the upstream images until they need extra dependencies.

## Non-prod

| Service | Port | Notes |
|---|---|---|
| Web UI | 3000 | Calls the Ingestion API through `/api` on the same port; `API_MODE=mock` in `.env` switches back to the in-browser mock |
| Ingestion API | 8000 | Writes `pipelines/connections/` and `pipelines/jobs/`, which Airflow reads; docs at `/api/docs`. Every `env://<VAR>` a connection uses must be listed in its `environment` |
| Airflow | 8080 | Airflow 3 in standalone mode (one container); no login in non-prod |
| Flink web UI | 8081 | Session cluster: one JobManager, one TaskManager with 4 slots |
| SQL Server | 1433 | Sample database `crm`, read-only login `svc_ingest_ro` |
| PostgreSQL | internal | Databases `airflow` and `platform`. The shared server or a local container, see below |

### Metadata DB: shared server or local

The platform has one PostgreSQL server ([ADR-0011](../docs/adr/0011-shared-postgresql-server.md)). The [data-onboarding-agent](https://github.com/thanhphat2609/data-onboarding-agent) stack hosts it, with the databases `airflow`, `platform` and the agent's own `onboarding_agent`. Airflow joins that stack's Docker network `data-platform` and connects to `postgres:5432`. That only works when both stacks run on one Docker host.

| Where | `COMPOSE_PROFILES` in `.env` | Metadata DB |
|---|---|---|
| Standalone Codespace of this repo (default) | `local-db` | Local `postgres` container in this project, created as before |
| Both stacks on one host (demo VM 1: Agent + Airflow + Flink JobManager) | empty | The agent stack's server. Start that stack first, and set `AIRFLOW_DB_PASSWORD` / `PLATFORM_DB_PASSWORD` to its `POSTGRES_AIRFLOW_PASSWORD` / `POSTGRES_PLATFORM_PASSWORD` |

`bootstrap.sh` creates the `data-platform` network if it is missing, writes `COMPOSE_PROFILES=local-db` into a new `.env`, and adds it to an `.env` from before this change. In an existing Codespace, run `bash infrastructure/non-prod/bootstrap.sh` once after pulling. In shared mode Airflow waits up to 5 minutes for the server (`start.sh`), because Compose can't wait for a service of another project.

### Start

In a Codespace this happens automatically: `bootstrap.sh` runs once on create and the stack starts on every start. Elsewhere, from the repository root:

```bash
bash infrastructure/non-prod/bootstrap.sh     # creates .env with random secrets
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

### Try the sample job

The sample `pipelines/jobs/crm-customers-daily.yaml` appears in Airflow as DAG `ingest__crm-customers-daily` (new DAGs start paused). Unpause it and trigger it; in Phase 1 it runs Flink's WordCount example on the session cluster, visible in the Flink web UI.

After adding or changing a connection file, refresh its pool (or restart Airflow):

```bash
docker compose exec airflow bash -c "python /opt/airflow/scripts/sync_pools.py > /tmp/pools.json && airflow pools import /tmp/pools.json"
```

To work on the UI with hot reload, run `npm ci && npm run dev -- --port 5173` in `code/ui/` (see [code/ui/README.md](../code/ui/README.md)).

### Reset

```bash
docker compose -f infrastructure/non-prod/docker-compose.yml down -v   # deletes all data volumes
rm -rf infrastructure/non-prod/data
```

`.env` is kept; delete it as well to get new secrets. In shared mode `down -v` doesn't touch the metadata DB, which lives in the agent stack's volume. Reset it there, or drop and recreate the `airflow` database.

### Memory

Limits per service add up to about 7.5 GB: Airflow 2 GB, SQL Server 2 GB, TaskManager 1.75 GB, JobManager 1.25 GB, PostgreSQL 256 MB (local-db only), UI 64 MB. Use the 4-core / 16 GB Codespace machine type, and stop the Codespace when idle.
