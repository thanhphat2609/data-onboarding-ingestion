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

Flink uses `docker/flink/` from Phase 2. Airflow and its metadata database are in [data-onboarding-orchestration](https://github.com/thanhphat2609/data-onboarding-orchestration) ([ADR-0016](../docs/adr/0016-airflow-moves-to-orchestration.md)): that stack starts after this one, mounts this checkout read-only and reaches Flink, Redpanda and the API over the Docker network `data-platform`. Without it the Web UI and Flink work, but jobs don't become DAGs and **Run now** fails.

## Non-prod

| Service | Port | Notes |
|---|---|---|
| Web UI | 3000 | Calls the Ingestion API through `/api` on the same port; `API_MODE=mock` in `.env` switches back to the in-browser mock |
| Ingestion API | 8000 | Writes `pipelines/connections/` and `pipelines/jobs/`, which Airflow reads; docs at `/api/docs` |
| Flink web UI | 8081 | Session cluster: one JobManager, one TaskManager with 4 slots |
| Redpanda | internal | Landing for API sources: Kafka API `redpanda:9092`, one topic `ingest.<job>` per API job, 7-day retention. `docker compose -f infrastructure/non-prod/docker-compose.yml exec redpanda rpk topic consume ingest.<job> -n 3` |

After pulling new services, run `bootstrap.sh` again: it adds new variables from the `.env.example` files to the existing `.env` files.

### Source secrets: `sources.env`

Connections reference passwords and tokens as `env://<VAR>`. The values are in `infrastructure/non-prod/sources.env`, read by the API (Test connection, preview), Flink and Airflow (the `fetch` task; the orchestration stack mounts this file). It is the non-prod twin of prod's `vm1/sources.env`, which the Deploy workflow writes from GitHub secrets ([ADR-0013](../docs/adr/0013-prod-settings-in-github.md)). `bootstrap.sh` fills the keys of `sources.env.example` from `example-sources/.env`. For another source, add its line to `sources.env`, then `docker compose -f infrastructure/non-prod/docker-compose.yml up -d` to recreate the containers that read it.

### Test sources: `example-sources/`

SQL Server, PostgreSQL, MySQL and a REST API, each with a read-only login, in its own folder with its own Compose file and `.env`. Like the company's real systems, they are not part of the platform: start them by hand, then onboard them in the Web UI. `pipelines/` starts empty. Demo, step by step, and the example connection and job files: [non-prod/example-sources/README.md](non-prod/example-sources/README.md).

```bash
docker compose -f infrastructure/non-prod/example-sources/docker-compose.yml up -d              # all of them
docker compose -f infrastructure/non-prod/example-sources/postgresql/docker-compose.yml up -d   # or one
```

They reach the platform over the Docker network `ingestion-sources`, created by `bootstrap.sh`.

### Start

In a Codespace this happens automatically: `bootstrap.sh` runs once on create and the stack starts on every start. Elsewhere, from the repository root:

```bash
bash infrastructure/non-prod/bootstrap.sh     # creates the .env files with random secrets, and sources.env
docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build
```

The first start pulls about 3 GB of images.

### Daily use

```bash
cd infrastructure/non-prod
docker compose ps                       # health of every service
docker compose logs -f api              # follow one service
docker compose stop                     # free memory, keep data
docker compose up -d --build ui         # rebuild the UI after changes
```

### Try a job

`pipelines/` starts empty. Start the example sources and create a connection and a job in the Web UI, step by step: [non-prod/example-sources/README.md](non-prod/example-sources/README.md). The job appears in Airflow as DAG `ingest__<name>` (new DAGs start paused); in Phase 1 a run executes Flink's WordCount example on the session cluster, visible in the Flink web UI.

After adding or changing a connection file by hand, the orchestration stack updates its pool within a minute.

To work on the UI with hot reload, run `npm ci && npm run dev -- --port 5173` in `code/ui/` (see [code/ui/README.md](../code/ui/README.md)).

### Reset

```bash
docker compose -f infrastructure/non-prod/docker-compose.yml down -v                    # deletes all data volumes
docker compose -f infrastructure/non-prod/example-sources/docker-compose.yml down -v    # and the example sources
rm -rf infrastructure/non-prod/data
```

On one host the stacks don't clash: the agent stack publishes only `127.0.0.1:7860` (app) and `127.0.0.1:5432` (PostgreSQL); its SearXNG container has no host port. This stack uses 3000, 8000 and 8081 (and 1433 while the example sources run); the orchestration stack uses 8080.

`.env` is kept; delete it as well to get new secrets. Stop the orchestration stack first: it holds the volume `ingestion-flink-examples`.

### Memory

Limits per service add up to about 7.5 GB with the orchestration stack: Airflow 2 GB, SQL Server 2 GB, TaskManager 1.75 GB, JobManager 1.75 GB, PostgreSQL 256 MB (local-db only), UI 64 MB. Use the 4-core / 16 GB Codespace machine type, and stop the Codespace when idle.
