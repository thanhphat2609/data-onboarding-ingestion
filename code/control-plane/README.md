# Control plane

The Python library and the **Ingestion API** (FastAPI) behind the Web UI. It is not Flink code: the generic Flink job lives in `code/runner/` (Phase 4). The control plane decides *what* to run and checks it; the runner reads the merged job and connection files and executes them.

## Why it exists

The Web UI runs in the browser. It can't read or write files in the repository, reach a database, or hold secrets. Something on the server has to do that, and the same rules must apply whether a job comes from the UI, from a pull request, or (later) from the `ingestctl` CLI and the Airflow tasks. That shared code is the control plane (architecture §3.2).

| Step | Who | What happens |
|---|---|---|
| 1. Onboard a connection | UI → API | The API checks the connection against the JSON Schema and the source template, opens a pull request with `pipelines/connections/<name>.yaml` on the orchestration repository ([ADR-0017](../../docs/adr/0017-ui-opens-pull-requests-on-orchestration.md)). Once the pull request is open the local file is deleted: the pull request is the only record, and the lists show it as `pending` until the merge ([ADR-0018](../../docs/adr/0018-saves-live-in-their-pull-request.md)) |
| 2. Test connection | UI → API → source | The API resolves `env://` secrets (the browser never sees them) and opens a short session with the read-only login |
| 3. Write the query | UI → API | sqlglot checks it: one read-only `SELECT`, named and unique columns (ADR-0005) |
| 4. Preview | UI → API → source | First 100 rows and exact column types, using the template's `preflight.preview` snippet |
| 5. Save the job | UI → API | Validated, then a pull request with `pipelines/jobs/<name>.yaml` on the orchestration repository; the API never calls Airflow |
| 6. DAG appears | Airflow | After the merge, the DAG factory there registers `ingest__<name>`. Runs and history are watched in Airflow; the Web UI only links to it |
| 7. Run | Airflow → Flink | The DAG submits the PyFlink runner through the JobManager's REST API; it copies the job's plain `SELECT … FROM table` to Parquet at the sink's table path ([ADR-0019](../../docs/adr/0019-runner-on-the-prototype-cluster.md)) |

The YAML files are the only storage: no database tables for connections or jobs, and the only place they live is the orchestration repository. The API and Airflow never talk to each other; they share the schemas in `code/templates/` and those files.

Later phases add to the same library: preflight and the renderer (Phase 3, with `ingestctl`), and the publisher used by the DAG tasks (Phase 5).

## Layout

```
src/ingestion/
  api.py        HTTP layer (/api/...), responses match code/ui/src/api/types.ts
  store.py      Config store: read (working copy, then the orchestration checkout), validate, write, invalid files
  yamlio.py     The YAML layout of written files (key order, literal blocks) and atomic writes
  pending.py    Saves waiting for their merge: the open pull requests, listed as `pending` (cached 15 s)
  specs.py      JSON Schema + template parameter validation
  templates.py  Template registry, parameter checks, Jinja2 rendering of template snippets
  sql.py        sqlglot checks and the query wrapping used by preview
  sources/      Test connection and preview, one client per source template
    base.py       errors, result types, the protocol, JSON-safe values
    sqlserver.py  pymssql      postgres.py  psycopg      mysql.py  PyMySQL
  github.py     Opens the pull request on the orchestration repository and lists the open ones (GitHub REST API)
  rest_api.py   Fetch of REST API sources into Redpanda (used by the Airflow task `fetch`)
  secrets.py    env:// resolution (kv:// in Phase 6)
  settings.py   Environment variables
```

## Endpoints

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Liveness |
| `GET /api/templates`, `GET /api/schemas/{name}` | Templates and JSON Schemas |
| `GET /api/connections`, `GET /api/connections/{name}` | Valid connection files; the list also holds the saves whose pull request is open, each with `pending: {number, url, branch}` |
| `POST /api/connections`, `PUT /api/connections/{name}` | Create (409 if the file exists), update (name can't change) |
| `POST /api/connections/{name}/test` | Test the parameters in the body, saved or not |
| `GET /api/jobs` | Valid jobs with their DAG id; the saves whose pull request is open come last, with `pending` |
| `GET /api/jobs/{name}`, `POST /api/jobs`, `PUT /api/jobs/{name}` | Read, create, update a job file |
| `GET /api/invalid-files` | Invalid files of the working copy, with a one-line reason |
| `POST /api/sql/validate`, `POST /api/sql/preview` | Body `{"connection", "query"}` |

OpenAPI docs: `/api/docs`. Errors are `{"detail": "..."}` with 404, 409, 422 (plus `errors`, one per problem) or 502 when GitHub refuses the pull request. With `SAVE_MODE=pull_request`, `POST` and `PUT` of connections and jobs also return `pullRequest` (`number`, `url`, `branch`). An error after the pull request is open is logged and the save still answers `201` with it: the pull request can't be taken back, so the user must not see a failure.

## Configuration

| Variable | Default | |
|---|---|---|
| `INGESTION_PIPELINES_DIR` | `<repo>/pipelines` | Working copy with `connections/` and `jobs/` (git-ignored): where a save is written for a moment before its pull request is open |
| `INGESTION_REFERENCE_PIPELINES_DIR` | empty | Read-only checkout of the orchestration repository's `pipelines/`: what is merged. Prod mounts it at `/workspace/orchestration-pipelines` |
| `INGESTION_TEMPLATES_DIR` | `<repo>/code/templates` | |
| `SAVE_MODE` | `disk` | `pull_request` also opens a pull request on every save (non-prod Compose sets it) |
| `GITHUB_TOKEN` | empty | Required for `pull_request`: fine-grained, Contents and Pull requests (read and write) on one repository |
| `ORCHESTRATION_REPOSITORY`, `ORCHESTRATION_BASE_BRANCH`, `ORCHESTRATION_PIPELINES_PATH` | `thanhphat2609/data-onboarding-orchestration`, `main`, `pipelines` | Where the pull request goes |
| Every `env://<VAR>` a connection uses | | Must be set in the API container (see the Compose file) |

## Development

```bash
cd code/control-plane
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
uvicorn ingestion.api:create_app --factory --reload --port 8000
ruff check src && ruff format --check src && mypy src
```

Then run the UI dev server against it: `cd code/ui && VITE_API_MODE=http npm run dev -- --port 5173`. Delete `.venv` and caches when done.

## Known limits (Phase 1)

- Test connection with `encrypt: true` encrypts but does not verify the server certificate (FreeTDS). Runs use the JDBC driver, which applies `trust_server_certificate`.
- The DAG factory still has its own copy of the file checks (`dags/common/ingestion_jobs.py` in the orchestration repository); it moves to this library in Phase 5.
- The job wizard works only on merged connections: the API can test and preview a connection that exists as a merged file, not one that waits for its pull request.
- One API process; writes are serialized with a lock in that process.
