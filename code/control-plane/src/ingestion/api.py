"""Ingestion API (FastAPI): the HTTP layer the Web UI calls, at ``/api``.

Responses follow ``code/ui/src/api/types.ts``. Errors are ``{"detail": "<message>"}`` with 404 (not found),
409 (already exists), 422 (invalid input, ``errors`` lists each problem) or 502 (Airflow unavailable).
Run: ``uvicorn ingestion.api:create_app --factory --host 0.0.0.0 --port 8000``
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ingestion.airflow import AirflowClient, AirflowError, DagNotFound, RunSummary, dag_id
from ingestion.settings import Settings
from ingestion.sources import SourceClient, SourceError, client_for
from ingestion.specs import InvalidSpec, validate_connection
from ingestion.sql import check_sql
from ingestion.store import ConfigStore, Conflict, NotFound
from ingestion.templates import Template, TemplateNotFound, TemplateRegistry

log = logging.getLogger("ingestion.api")

Document = dict[str, Any]


class SqlRequest(BaseModel):
    connection: str
    query: str


class RunRequest(BaseModel):
    ingestDate: str | None = None  # noqa: N815 - JSON field name used by the Web UI


def _run_json(run: RunSummary) -> Document:
    return {
        "runId": run.run_id,
        "dagId": run.dag_id,
        "ingestDate": run.ingest_date,
        "state": run.state,
        "startedAt": run.started_at,
        "trigger": run.trigger,
    }


def create_app(
    settings: Settings | None = None,
    airflow: AirflowClient | None = None,
    source_factory: Callable[[Document, Template], SourceClient] = client_for,
) -> FastAPI:
    settings = settings or Settings.from_env()
    registry = TemplateRegistry(settings.templates_dir)
    store = ConfigStore(settings, registry)
    airflow = airflow or AirflowClient(settings.airflow_url, settings.airflow_username, settings.airflow_password)
    app = FastAPI(title="Ingestion API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.exception_handler(InvalidSpec)
    def invalid_spec(_: Request, error: InvalidSpec) -> JSONResponse:
        return JSONResponse({"detail": str(error), "errors": error.errors}, status_code=422)

    @app.exception_handler(NotFound)
    @app.exception_handler(TemplateNotFound)
    def not_found(_: Request, error: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(error).strip("'\"")}, status_code=404)

    @app.exception_handler(Conflict)
    def conflict(_: Request, error: Conflict) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(SourceError)
    def source_error(_: Request, error: SourceError) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.exception_handler(DagNotFound)
    def dag_not_found(_: Request, error: DagNotFound) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(AirflowError)
    def airflow_error(_: Request, error: AirflowError) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=502)

    def require_name(path_name: str, document: Document) -> None:
        if document.get("name") != path_name:
            raise InvalidSpec([f'name: must be "{path_name}"; names can\'t be changed after creation'])

    # --- health, templates, schemas ------------------------------------------------------------------

    @app.get("/api/health")
    def health() -> Document:
        return {"status": "ok"}

    @app.get("/api/templates")
    def templates() -> Document:
        return {"sources": [t.body for t in registry.sources()], "sinks": [t.body for t in registry.sinks()]}

    @app.get("/api/schemas/{name}")
    def schema(name: str) -> Document:
        return registry.schema(name)

    # --- connections ---------------------------------------------------------------------------------

    @app.get("/api/connections")
    def list_connections() -> list[Document]:
        return store.list_connections()

    @app.get("/api/connections/{name}")
    def get_connection(name: str) -> Document:
        return store.get_connection(name)

    def save_connection(connection: Document, is_new: bool) -> Document:
        saved = store.save_connection(connection, is_new)
        try:
            airflow.upsert_pool(saved)
        except AirflowError as error:
            # The file is saved; Airflow also creates pools from the files on its next start.
            log.warning("Connection %s saved, pool not updated: %s", saved["name"], error)
        return saved

    @app.post("/api/connections", status_code=201)
    def create_connection(connection: Annotated[Document, Body()]) -> Document:
        return save_connection(connection, is_new=True)

    @app.put("/api/connections/{name}")
    def update_connection(name: str, connection: Annotated[Document, Body()]) -> Document:
        require_name(name, connection)
        return save_connection(connection, is_new=False)

    @app.post("/api/connections/{name}/test")
    def test_connection(name: str, connection: Annotated[Document, Body()]) -> Document:
        """Tests the parameters as sent (the form may be unsaved)."""
        require_name(name, connection)
        validate_connection(connection, registry)
        result = source_factory(connection, registry.source(connection["template"])).test()
        return {"ok": result.ok, "message": result.message, "latencyMs": result.latency_ms}

    # --- jobs and runs -------------------------------------------------------------------------------

    @app.get("/api/jobs")
    def list_jobs() -> list[Document]:
        jobs = store.list_jobs()

        def runs(job: Document) -> list[Document]:
            try:
                return [_run_json(r) for r in airflow.latest_runs(dag_id(job["name"]))]
            except AirflowError as error:
                log.warning("Runs of %s unavailable: %s", job["name"], error)
                return []

        with ThreadPoolExecutor(max_workers=8) as pool:
            all_runs = list(pool.map(runs, jobs))
        return [{"job": job, "dagId": dag_id(job["name"]), "runs": r} for job, r in zip(jobs, all_runs, strict=True)]

    @app.get("/api/jobs/{name}")
    def get_job(name: str) -> Document:
        return store.get_job(name)

    @app.post("/api/jobs", status_code=201)
    def create_job(job: Annotated[Document, Body()]) -> Document:
        return store.save_job(job, is_new=True)

    @app.put("/api/jobs/{name}")
    def update_job(name: str, job: Annotated[Document, Body()]) -> Document:
        require_name(name, job)
        return store.save_job(job, is_new=False)

    @app.post("/api/jobs/{name}/runs", status_code=201)
    def trigger_run(name: str, request: RunRequest | None = None) -> Document:
        store.get_job(name)
        return _run_json(airflow.trigger(dag_id(name), request.ingestDate if request else None))

    @app.get("/api/invalid-files")
    def invalid_files() -> list[Document]:
        return [asdict(f) for f in store.invalid_files()]

    # --- SQL -----------------------------------------------------------------------------------------

    def connection_template(name: str) -> tuple[Document, Template]:
        connection = store.get_connection(name)
        validate_connection(connection, registry)
        return connection, registry.source(connection["template"])

    @app.post("/api/sql/validate")
    def validate_sql(request: SqlRequest) -> Document:
        _, template = connection_template(request.connection)
        result = check_sql(request.query, str(template.body["dialect"]))
        return {"ok": result.ok, "mode": result.mode, "issues": [asdict(i) for i in result.issues]}

    @app.post("/api/sql/preview")
    def preview(request: SqlRequest) -> Document:
        connection, template = connection_template(request.connection)
        check = check_sql(request.query, str(template.body["dialect"]))
        if not check.ok:
            errors = [i.message for i in check.issues if i.severity == "error"]
            raise InvalidSpec(errors)
        result = source_factory(connection, template).preview(request.query)
        return {"columns": result.columns, "rows": result.rows}

    return app
