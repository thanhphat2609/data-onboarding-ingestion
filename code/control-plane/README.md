# Control plane

The Python library and the **Ingestion API** (FastAPI) behind the Web UI. It is not Flink code: the generic Flink job lives in `code/runner/` (Phase 4). The control plane decides *what* to run and checks it; the runner reads the merged job and connection files and executes them.

## Why it exists

The Web UI runs in the browser. It can't read or write files in the repository, reach a database, or hold secrets. Something on the server has to do that, and the same rules must apply whether a job comes from the UI, from a pull request, or (later) from the `ingestctl` CLI and the Airflow tasks. That shared code is the control plane (architecture §3.2).

| Step | Who | What happens |
|---|---|---|
| 1. Onboard a connection | UI → API | The API checks the connection against the JSON Schema and the source template, opens a pull request with `pipelines/connections/<name>.yaml` on the orchestration repository ([ADR-0017](../../docs/adr/0017-ui-opens-pull-requests-on-orchestration.md)), and keeps a working copy in `pipelines/` |
| 2. Test connection | UI → API → source | The API resolves `env://` secrets (the browser never sees them) and opens a short session with the read-only login |
| 3. Write the query | UI → API | sqlglot checks it: one read-only `SELECT`, named and unique columns (ADR-0005) |
| 4. Preview | UI → API → source | First 100 rows and exact column types, using the template's `preflight.preview` snippet |
| 5. Save the job | UI → API | Validated, then a pull request with `pipelines/jobs/<name>.yaml` on the orchestration repository; the API never calls Airflow |
| 6. DAG appears | Airflow | After the merge, the DAG factory there registers `ingest__<name>`. Runs and history are watched in Airflow; the Web UI only links to it |
| 7. Run | Airflow → Flink | The DAG submits the Flink job: a smoke job in Phase 1, the PyFlink runner from Phase 4 |

The YAML files are the only storage: no database tables for connections or jobs. The API and Airflow never talk to each other; they share the schemas in `code/templates/` and the files in the orchestration repository.

Later phases add to the same library: preflight and the renderer (Phase 3, with `ingestctl`), and the publisher used by the DAG tasks (Phase 5).

## Layout

```
src/ingestion/
  api.py        HTTP layer (/api/...), responses match code/ui/src/api/types.ts
  store.py      Config store: read, validate, write pipelines/*.yaml; invalid files
  specs.py      JSON Schema + template parameter validation
  templates.py  Template registry, parameter checks, Jinja2 rendering of template snippets
  sql.py        sqlglot checks and the query wrapping used by preview
  sources.py    Test connection and preview, one client per source template (SQL Server: pymssql, PostgreSQL: psycopg, MySQL: PyMySQL)
  github.py     Opens the pull request on the orchestration repository (GitHub REST API)
  secrets.py    env:// resolution (kv:// in Phase 6)
  settings.py   Environment variables
```

## Endpoints

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Liveness |
| `GET /api/templates`, `GET /api/schemas/{name}` | Templates and JSON Schemas |
| `GET /api/connections`, `GET /api/connections/{name}` | Valid connection files |
| `POST /api/connections`, `PUT /api/connections/{name}` | Create (409 if the file exists), update (name can't change) |
| `POST /api/connections/{name}/test` | Test the parameters in the body, saved or not |
| `GET /api/jobs` | Valid jobs of the working copy with their DAG id |
| `GET /api/jobs/{name}`, `POST /api/jobs`, `PUT /api/jobs/{name}` | Read, create, update a job file |
| `GET /api/invalid-files` | Invalid files of the working copy, with a one-line reason |
| `POST /api/sql/validate`, `POST /api/sql/preview` | Body `{"connection", "query"}` |

OpenAPI docs: `/api/docs`. Errors are `{"detail": "..."}` with 404, 409, 422 (plus `errors`, one per problem) or 502 when GitHub refuses the pull request. With `SAVE_MODE=pull_request`, `POST` and `PUT` of connections and jobs also return `pullRequest` (`number`, `url`, `branch`).

## Configuration

| Variable | Default | |
|---|---|---|
| `INGESTION_PIPELINES_DIR` | `<repo>/pipelines` | Working copy with `connections/` and `jobs/` (git-ignored); point it at a checkout of the orchestration repository's `pipelines/` to see what is merged |
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
- The DAG factory still has its own copy of the file checks; it moves to this library in Phase 5.
- One API process; writes are serialized with a lock in that process.
