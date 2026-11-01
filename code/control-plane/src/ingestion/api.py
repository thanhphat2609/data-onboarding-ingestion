"""Ingestion API (FastAPI): the HTTP layer the Web UI calls, at ``/api``.

Responses follow ``code/ui/src/api/types.ts``. Errors are ``{"detail": "<message>"}`` with 404 (not found),
409 (already exists), 422 (invalid input, ``errors`` lists each problem) or 502 (GitHub unavailable).
With ``SAVE_MODE=pull_request`` a saved connection or job also opens a pull request on the orchestration repository
(ADR-0017); the response then carries ``pullRequest``.
Run: ``uvicorn ingestion.api:create_app --factory --host 0.0.0.0 --port 8000``
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ingestion.github import GitHubError, PullRequest, PullRequestPublisher
from ingestion.settings import Settings
from ingestion.sources import SourceClient, SourceError, client_for
from ingestion.specs import InvalidSpec, validate_connection
from ingestion.sql import check_sql
from ingestion.store import ConfigStore, Conflict, NotFound, Publish
from ingestion.templates import Template, TemplateNotFound, TemplateRegistry

Document = dict[str, Any]


class SqlRequest(BaseModel):
    connection: str
    query: str


def dag_id(job_name: str) -> str:
    """The DAG that the orchestration repository's factory builds for a job; the Web UI only links to it."""
    return f"ingest__{job_name}"


def create_app(
    settings: Settings | None = None,
    publisher: PullRequestPublisher | None = None,
    source_factory: Callable[[Document, Template], SourceClient] = client_for,
) -> FastAPI:
    settings = settings or Settings.from_env()
    registry = TemplateRegistry(settings.templates_dir)
    store = ConfigStore(settings, registry)
    if settings.save_mode == "pull_request" and publisher is None:
        if not settings.github_token:
            raise RuntimeError("SAVE_MODE=pull_request needs GITHUB_TOKEN (Contents and Pull requests, read and write)")
        publisher = PullRequestPublisher(settings.github_token, settings.github_repository, settings.github_base_branch)
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

    @app.exception_handler(GitHubError)
    def github_error(_: Request, error: GitHubError) -> JSONResponse:
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

    # --- saving: a file in pipelines/, plus a pull request in pull_request mode -----------------------

    def publication(kind: str, name: str, owner: object, is_new: bool) -> tuple[Publish | None, list[PullRequest]]:
        """The store calls it with the validated file; it opens the pull request before the file is written."""
        opened: list[PullRequest] = []
        if publisher is None:
            return None, opened

        def publish(relative_path: str, text: str) -> None:
            action = "add" if is_new else "update"
            opened.append(
                publisher.open(
                    path=f"{settings.repository_pipelines_path}/{relative_path}",
                    content=text,
                    title=f"feat(ingestion): {action} {kind} {name}",
                    body=f"{action.capitalize()} {kind} `{name}` (owner: {owner}), saved in the Ingestion Web UI.\n\n"
                    "CI validates the file against the schemas; merging puts it in front of Airflow.",
                    branch_prefix=f"ui/{kind}-{name}",
                )
            )

        return publish, opened

    def with_pull_request(saved: Document, opened: list[PullRequest]) -> Document:
        if not opened:
            return saved
        pull = opened[0]
        return {**saved, "pullRequest": {"number": pull.number, "url": pull.url, "branch": pull.branch}}

    # --- connections ---------------------------------------------------------------------------------

    @app.get("/api/connections")
    def list_connections() -> list[Document]:
        return store.list_connections()

    @app.get("/api/connections/{name}")
    def get_connection(name: str) -> Document:
        return store.get_connection(name)

    def save_connection(connection: Document, is_new: bool) -> Document:
        publish, opened = publication("connection", str(connection.get("name")), connection.get("owner"), is_new)
        return with_pull_request(store.save_connection(connection, is_new, publish), opened)

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

    # --- jobs ----------------------------------------------------------------------------------------

    @app.get("/api/jobs")
    def list_jobs() -> list[Document]:
        return [{"job": job, "dagId": dag_id(job["name"])} for job in store.list_jobs()]

    @app.get("/api/jobs/{name}")
    def get_job(name: str) -> Document:
        return store.get_job(name)

    def save_job(job: Document, is_new: bool) -> Document:
        publish, opened = publication("job", str(job.get("name")), job.get("owner"), is_new)
        return with_pull_request(store.save_job(job, is_new, publish), opened)

    @app.post("/api/jobs", status_code=201)
    def create_job(job: Annotated[Document, Body()]) -> Document:
        return save_job(job, is_new=True)

    @app.put("/api/jobs/{name}")
    def update_job(name: str, job: Annotated[Document, Body()]) -> Document:
        require_name(name, job)
        return save_job(job, is_new=False)

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
