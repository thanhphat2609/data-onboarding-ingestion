"""Saving in the Web UI opens a pull request on the orchestration repository (ADR-0017), with a fake GitHub."""

from __future__ import annotations

import base64
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from ingestion.api import create_app
from ingestion.github import PullRequestPublisher
from ingestion.settings import REPO_ROOT, Settings
from ingestion.store import ConfigStore, StorageError, to_yaml

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


def client(tmp_path: Path, github: FakeGitHub, merged: dict[str, str] | None = None) -> TestClient:
    """``merged``: files of the orchestration checkout (path under pipelines/ -> text), read-only for the API."""
    reference = tmp_path / "orchestration" / "pipelines"
    for name, text in (merged or {}).items():
        (reference / name).parent.mkdir(parents=True, exist_ok=True)
        (reference / name).write_text(text, encoding="utf-8")
    settings = replace(
        Settings.from_env(),
        reference_pipelines_dir=reference,
        pipelines_dir=tmp_path / "pipelines",
        templates_dir=REPO_ROOT / "code" / "templates",
        save_mode="pull_request",
        repository_pipelines_path="pipelines",
    )
    publisher = PullRequestPublisher(
        "t0ken", "acme/orchestration", client=httpx.Client(transport=httpx.MockTransport(github))
    )
    return TestClient(create_app(settings, publisher))


def yaml_text(document: dict[str, Any]) -> str:
    """A document as the YAML the store writes."""
    return to_yaml(document, ["kind", "name", "template", "owner", "params"])


def test_saving_a_connection_opens_a_pull_request_with_the_file(tmp_path: Path) -> None:
    github = FakeGitHub()
    response = client(tmp_path, github).post("/api/connections", json=CONNECTION)

    assert response.status_code == 201
    pull = response.json()["pullRequest"]
    assert pull["url"] == "https://github.com/acme/orchestration/pull/1"
    assert pull["branch"].startswith("ui/connection-sales-postgresql-")
    assert "name: sales-postgresql" in github.branches[pull["branch"]]["pipelines/connections/sales-postgresql.yaml"]
    assert github.pulls[0]["base"] == "main"
    # The pull request is the record: nothing stays in the working copy.
    assert not (tmp_path / "pipelines" / "connections" / "sales-postgresql.yaml").exists()
    assert response.json()["name"] == "sales-postgresql"


def test_changing_an_existing_file_sends_its_sha(tmp_path: Path) -> None:
    github = FakeGitHub({"pipelines/connections/sales-postgresql.yaml": "old"})
    api = client(tmp_path, github, {"connections/sales-postgresql.yaml": "old"})

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
    assert not (tmp_path / "pipelines" / "connections" / "sales-postgresql.yaml").exists()


def test_github_failure_leaves_the_merged_file_alone(tmp_path: Path) -> None:
    github = FakeGitHub()
    api = client(tmp_path, github, {"connections/sales-postgresql.yaml": "old"})
    github.fail_with = 401

    response = api.put("/api/connections/sales-postgresql", json={**CONNECTION, "owner": "other-team"})

    assert response.status_code == 502
    assert not (tmp_path / "pipelines" / "connections" / "sales-postgresql.yaml").exists()
    assert (tmp_path / "orchestration" / "pipelines" / "connections" / "sales-postgresql.yaml").read_text() == "old"


def test_error_after_the_pull_request_is_open_still_answers_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure once the PR exists must not show as an error: the PR can't be taken back."""
    github = FakeGitHub()
    save = ConfigStore.save_connection

    def save_then_fail(self: ConfigStore, connection: dict[str, Any], is_new: bool, publish: Any = None) -> Any:
        """The real save (which opens the pull request), then an error."""
        save(self, connection, is_new, publish)
        raise RuntimeError("boom")

    monkeypatch.setattr(ConfigStore, "save_connection", save_then_fail)
    response = client(tmp_path, github).post("/api/connections", json=CONNECTION)

    assert response.status_code == 201
    assert response.json()["pullRequest"]["url"] == "https://github.com/acme/orchestration/pull/1"
    assert len(github.pulls) == 1


def test_connection_of_the_orchestration_checkout_is_listed_and_found(tmp_path: Path) -> None:
    api = client(tmp_path, FakeGitHub(), {"connections/sales-postgresql.yaml": yaml_text(CONNECTION)})

    assert [c["name"] for c in api.get("/api/connections").json()] == ["sales-postgresql"]
    assert api.get("/api/connections/sales-postgresql").status_code == 200
    assert api.post("/api/connections", json=CONNECTION).status_code == 409


def test_unwritable_working_copy_opens_no_pull_request(tmp_path: Path) -> None:
    github = FakeGitHub()
    api = client(tmp_path, github)
    # The directory turns into a file after startup: the write fails like it does on a mount that became read-only.
    shutil.rmtree(tmp_path / "pipelines")
    (tmp_path / "pipelines").write_text("not a directory")
    response = api.post("/api/connections", json=CONNECTION)

    assert response.status_code == 500
    assert "nothing was saved and no pull request was opened" in response.json()["detail"]
    assert github.pulls == []


def test_unwritable_working_copy_stops_the_api_at_startup(tmp_path: Path) -> None:
    (tmp_path / "pipelines").write_text("not a directory")
    with pytest.raises(StorageError, match="isn't writable"):
        client(tmp_path, FakeGitHub())


def test_pull_request_mode_needs_a_token(tmp_path: Path) -> None:
    settings = replace(Settings.from_env(), pipelines_dir=tmp_path, save_mode="pull_request", github_token=None)
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        create_app(settings)


def test_disk_mode_has_no_pull_request(tmp_path: Path) -> None:
    settings = replace(Settings.from_env(), pipelines_dir=tmp_path / "pipelines", save_mode="disk")
    response = TestClient(create_app(settings)).post("/api/connections", json=CONNECTION)

    assert response.status_code == 201
    assert "pullRequest" not in response.json()
