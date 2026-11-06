"""Saving in the Web UI opens a pull request on the orchestration repository (ADR-0017), with a fake GitHub."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from fake_github import FakeGitHub
from fastapi.testclient import TestClient

from ingestion.api import create_app
from ingestion.github import PullRequestPublisher
from ingestion.settings import REPO_ROOT, Settings
from ingestion.store import ConfigStore, StorageError
from ingestion.yamlio import to_yaml

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


def test_saved_connection_stays_visible_as_pending_until_its_pull_request_is_merged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ingestion.pending.CACHE_SECONDS", 0)
    github = FakeGitHub()
    api = client(tmp_path, github)
    pull = api.post("/api/connections", json=CONNECTION).json()["pullRequest"]

    listed = api.get("/api/connections").json()

    assert [c["name"] for c in listed] == ["sales-postgresql"]
    assert listed[0]["pending"] == pull
    assert not (tmp_path / "pipelines" / "connections" / "sales-postgresql.yaml").exists()

    github.merged.add(pull["branch"])  # no longer an open pull request
    assert api.get("/api/connections").json() == []


def test_merged_connection_is_not_listed_twice_while_its_update_is_open(tmp_path: Path) -> None:
    github = FakeGitHub()
    api = client(tmp_path, github, {"connections/sales-postgresql.yaml": yaml_text(CONNECTION)})
    api.put("/api/connections/sales-postgresql", json={**CONNECTION, "owner": "other-team"})

    listed = api.get("/api/connections").json()

    assert [c["name"] for c in listed] == ["sales-postgresql"]
    assert "pending" not in listed[0]


def test_a_job_with_an_open_pull_request_is_listed_as_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ingestion.pending.CACHE_SECONDS", 0)
    github = FakeGitHub()
    github.pulls.append({"head": "ui/job-shop-orders-20261106-090000"})
    github.branches["ui/job-shop-orders-20261106-090000"] = {
        "pipelines/jobs/shop-orders.yaml": "kind: IngestionJob\nname: shop-orders\nowner: de-team\nconnection: x\n"
    }
    listed = client(tmp_path, github).get("/api/jobs").json()

    assert listed[0]["job"]["name"] == "shop-orders"
    assert listed[0]["dagId"] == "ingest__shop-orders"
    assert listed[0]["pending"]["number"] == 1


def test_github_failure_does_not_break_the_lists(tmp_path: Path) -> None:
    github = FakeGitHub()
    github.fail_with = 401
    api = client(tmp_path, github)

    assert api.get("/api/connections").json() == []
    assert api.get("/api/jobs").json() == []
