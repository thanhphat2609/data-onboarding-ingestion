"""Saving in the Web UI opens a pull request on the orchestration repository (ADR-0017), with a fake GitHub."""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from ingestion.api import create_app
from ingestion.github import PullRequestPublisher
from ingestion.settings import REPO_ROOT, Settings

CONNECTION = {
    "kind": "Connection",
    "name": "sales-postgresql",
    "template": "postgresql@1",
    "owner": "data-team",
    "params": {
        "host": "postgres-source",
        "port": 5432,
        "database": "sales",
        "username": "svc_ingest_ro",
        "password": "env://SALES_POSTGRES_RO_PASSWORD",
    },
}


class FakeGitHub:
    """Just enough of the GitHub REST API: one base commit, branches, files on branches, pull requests."""

    def __init__(self, existing: dict[str, str] | None = None) -> None:
        self.files = existing or {}
        self.branches: dict[str, dict[str, str]] = {}
        self.pulls: list[dict[str, Any]] = []
        self.fail_with: int | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer t0ken"
        if self.fail_with:
            return httpx.Response(self.fail_with, json={"message": "Bad credentials"})
        path = request.url.path.removeprefix("/repos/acme/orchestration")
        body = json.loads(request.content) if request.content else {}
        if path == "/git/ref/heads/main":
            return httpx.Response(200, json={"object": {"sha": "base"}})
        if path == "/git/refs":
            self.branches[body["ref"].removeprefix("refs/heads/")] = dict(self.files)
            return httpx.Response(201, json={})
        if path.startswith("/contents/"):
            name = path.removeprefix("/contents/")
            if request.method == "GET":
                branch = self.branches[request.url.params["ref"]]
                return httpx.Response(200, json={"sha": "blob1"}) if name in branch else httpx.Response(404, json={})
            if name in self.branches[body["branch"]]:
                assert body["sha"] == "blob1", "replacing a file needs its current sha"
            self.branches[body["branch"]][name] = base64.b64decode(body["content"]).decode()
            return httpx.Response(201, json={})
        if path == "/pulls":
            self.pulls.append(body)
            number = len(self.pulls)
            return httpx.Response(
                201, json={"number": number, "html_url": f"https://github.com/acme/orchestration/pull/{number}"}
            )
        raise AssertionError(f"unexpected {request.method} {path}")


def client(tmp_path: Path, github: FakeGitHub) -> TestClient:
    settings = replace(
        Settings.from_env(),
        pipelines_dir=tmp_path / "pipelines",
        templates_dir=REPO_ROOT / "code" / "templates",
        save_mode="pull_request",
        repository_pipelines_path="pipelines",
    )
    publisher = PullRequestPublisher(
        "t0ken", "acme/orchestration", client=httpx.Client(transport=httpx.MockTransport(github))
    )
    return TestClient(create_app(settings, publisher))


def test_saving_a_connection_opens_a_pull_request_with_the_file(tmp_path: Path) -> None:
    github = FakeGitHub()
    response = client(tmp_path, github).post("/api/connections", json=CONNECTION)

    assert response.status_code == 201
    pull = response.json()["pullRequest"]
    assert pull["url"] == "https://github.com/acme/orchestration/pull/1"
    assert pull["branch"].startswith("ui/connection-sales-postgresql-")
    assert "name: sales-postgresql" in github.branches[pull["branch"]]["pipelines/connections/sales-postgresql.yaml"]
    assert github.pulls[0]["base"] == "main"
    # The working copy keeps the file, so the job wizard can use the connection before the merge.
    assert (tmp_path / "pipelines" / "connections" / "sales-postgresql.yaml").exists()


def test_changing_an_existing_file_sends_its_sha(tmp_path: Path) -> None:
    github = FakeGitHub({"pipelines/connections/sales-postgresql.yaml": "old"})
    api = client(tmp_path, github)
    api.post("/api/connections", json=CONNECTION)

    changed = {**CONNECTION, "owner": "other-team"}
    response = api.put("/api/connections/sales-postgresql", json=changed)

    assert response.status_code == 200
    assert (
        "owner: other-team"
        in github.branches[response.json()["pullRequest"]["branch"]]["pipelines/connections/sales-postgresql.yaml"]
    )


def test_invalid_file_opens_no_pull_request(tmp_path: Path) -> None:
    github = FakeGitHub()
    response = client(tmp_path, github).post("/api/connections", json={**CONNECTION, "template": "nope@1"})

    assert response.status_code == 422
    assert github.pulls == []


def test_github_failure_saves_nothing(tmp_path: Path) -> None:
    github = FakeGitHub()
    github.fail_with = 401
    response = client(tmp_path, github).post("/api/connections", json=CONNECTION)

    assert response.status_code == 502
    assert "GITHUB_TOKEN" in response.json()["detail"]
    assert not (tmp_path / "pipelines" / "connections").exists()


def test_pull_request_mode_needs_a_token(tmp_path: Path) -> None:
    settings = replace(Settings.from_env(), pipelines_dir=tmp_path, save_mode="pull_request", github_token=None)
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        create_app(settings)


def test_disk_mode_has_no_pull_request(tmp_path: Path) -> None:
    settings = replace(Settings.from_env(), pipelines_dir=tmp_path / "pipelines", save_mode="disk")
    response = TestClient(create_app(settings)).post("/api/connections", json=CONNECTION)

    assert response.status_code == 201
    assert "pullRequest" not in response.json()
