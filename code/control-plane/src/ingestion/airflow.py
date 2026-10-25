"""Airflow 3 REST API client: "Run now", latest runs per DAG and pools per connection (ADR-0008)."""

from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass
from typing import Any, Literal

import httpx

DAG_PREFIX = "ingest__"
# Asia/Ho_Chi_Minh has no daylight saving time; a fixed offset avoids needing tzdata on every host.
PLATFORM_TZ = dt.timezone(dt.timedelta(hours=7), "Asia/Ho_Chi_Minh")
DEFAULT_MAX_CONCURRENT_RUNS = 2  # same default as code/airflow/scripts/sync_pools.py


def dag_id(job_name: str) -> str:
    return f"{DAG_PREFIX}{job_name}"


def pool_name(connection_name: str) -> str:
    return f"conn__{connection_name}"


class AirflowError(Exception):
    pass


class DagNotFound(AirflowError):
    pass


@dataclass
class RunSummary:
    run_id: str
    dag_id: str
    ingest_date: str
    state: Literal["queued", "running", "success", "failed"]
    started_at: str
    trigger: Literal["manual", "schedule"]


def _parse_time(value: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def to_run_summary(run: dict[str, Any]) -> RunSummary:
    conf = run.get("conf") or {}
    moment = _parse_time(run.get("logical_date")) or _parse_time(run.get("run_after"))
    ingest_date = conf.get("ingest_date") or (moment.astimezone(PLATFORM_TZ).date().isoformat() if moment else "")
    state = run.get("state")
    return RunSummary(
        run_id=run["dag_run_id"],
        dag_id=run["dag_id"],
        ingest_date=str(ingest_date),
        state=state if state in ("running", "success", "failed") else "queued",
        started_at=run.get("start_date") or run.get("queued_at") or run.get("run_after") or "",
        trigger="manual" if run.get("run_type") == "manual" else "schedule",
    )


class AirflowClient:
    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url
        self._username = username
        self._password = password
        self._http = httpx.Client(base_url=base_url, timeout=10, transport=transport)
        self._token: str | None = None
        self._lock = threading.Lock()

    def _login(self) -> str:
        # With a user: the simple auth manager's login. Without: all-admins mode (non-prod) hands out a token.
        if self._username:
            response = self._http.post("/auth/token", json={"username": self._username, "password": self._password})
        else:
            response = self._http.get("/auth/token")
        if response.status_code >= 400:
            raise AirflowError(f"Airflow login failed ({response.status_code}); check AIRFLOW_USERNAME/PASSWORD")
        return str(response.json()["access_token"])

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            for attempt in range(2):
                with self._lock:
                    if self._token is None:
                        self._token = self._login()
                    token = self._token
                response = self._http.request(
                    method, f"/api/v2{path}", headers={"Authorization": f"Bearer {token}"}, **kwargs
                )
                if response.status_code == 401 and attempt == 0:
                    with self._lock:
                        self._token = None  # expired token: log in again once
                    continue
                return response
        except httpx.HTTPError as error:
            raise AirflowError(f"Airflow is not reachable at {self.base_url}: {error}") from None
        return response

    @staticmethod
    def _detail(response: httpx.Response) -> str:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        return f"{response.status_code} {detail or response.text[:200]}"

    def _dag(self, dag: str) -> dict[str, Any]:
        response = self._request("GET", f"/dags/{dag}")
        if response.status_code == 404:
            raise DagNotFound(
                f"DAG {dag} is not in Airflow yet. A new job file appears within one DAG-processor cycle "
                "(about 30 seconds); if it doesn't, the file is listed under invalid files."
            )
        if response.status_code >= 400:
            raise AirflowError(f"Reading DAG {dag} failed: {self._detail(response)}")
        result: dict[str, Any] = response.json()
        return result

    def latest_runs(self, dag: str, limit: int = 5) -> list[RunSummary]:
        """Latest runs, oldest first. A DAG Airflow hasn't parsed yet has no runs."""
        response = self._request("GET", f"/dags/{dag}/dagRuns", params={"limit": limit, "order_by": "-run_after"})
        if response.status_code == 404:
            return []
        if response.status_code >= 400:
            raise AirflowError(f"Reading runs of {dag} failed: {self._detail(response)}")
        return [to_run_summary(run) for run in reversed(response.json().get("dag_runs", []))]

    def trigger(self, dag: str, ingest_date: str | None = None) -> RunSummary:
        """Triggers a run now. Like the Airflow UI's trigger form, it unpauses the DAG first (new DAGs start paused)."""
        if self._dag(dag).get("is_paused"):
            response = self._request("PATCH", f"/dags/{dag}", json={"is_paused": False})
            if response.status_code >= 400:
                raise AirflowError(f"Unpausing {dag} failed: {self._detail(response)}")
        body: dict[str, Any] = {"logical_date": None, "note": "Triggered from the Ingestion Web UI"}
        if ingest_date:
            body["conf"] = {"ingest_date": ingest_date}
        response = self._request("POST", f"/dags/{dag}/dagRuns", json=body)
        if response.status_code >= 400:
            raise AirflowError(f"Triggering {dag} failed: {self._detail(response)}")
        run = to_run_summary(response.json())
        if not ingest_date and not run.ingest_date:
            run.ingest_date = dt.datetime.now(PLATFORM_TZ).date().isoformat()
        return run

    def upsert_pool(self, connection: dict[str, Any]) -> None:
        """Creates or resizes ``conn__<name>`` with the same settings as sync_pools.py."""
        name = pool_name(connection["name"])
        body = {
            "slots": (connection.get("limits") or {}).get("max_concurrent_runs", DEFAULT_MAX_CONCURRENT_RUNS),
            "description": f"Concurrent runs on connection {connection['name']} "
            f"(pipelines/connections/{connection['name']}.yaml)",
            "include_deferred": True,
        }
        response = self._request("PATCH", f"/pools/{name}", json=body)
        if response.status_code == 404:
            response = self._request("POST", "/pools", json={"name": name, **body})
        if response.status_code >= 400:
            raise AirflowError(f"Saving pool {name} failed: {self._detail(response)}")
