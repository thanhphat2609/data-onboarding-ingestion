"""The demo's example files (infrastructure/non-prod/sample_database/examples/): what a demo types into the Web UI."""

from __future__ import annotations

from dataclasses import replace

from ingestion.settings import REPO_ROOT, Settings
from ingestion.sql import check_sql
from ingestion.store import ConfigStore
from ingestion.templates import TemplateRegistry

REGISTRY = TemplateRegistry(REPO_ROOT / "code" / "templates")


def test_demo_examples_are_valid() -> None:
    # The files a demo creates in the Web UI (sample_database/README.md); pipelines/ itself starts empty.
    examples = REPO_ROOT / "infrastructure" / "non-prod" / "sample_database" / "examples"
    store = ConfigStore(replace(Settings.from_env(), pipelines_dir=examples), REGISTRY)
    assert store.invalid_files() == []
    assert {c["template"] for c in store.list_connections()} == {"sqlserver@1", "postgresql@1", "mysql@1", "rest_api@1"}
    assert {j["name"] for j in store.list_jobs()} == {
        "crm-customers-daily",
        "sales-orders-daily",
        "shop-customers-by-segment-daily",
        "shop-api-orders-daily",
    }
    connections = {c["name"]: c for c in store.list_connections()}
    for job in store.list_jobs():
        dialect = str(REGISTRY.source(connections[job["connection"]]["template"]).body["dialect"])
        assert check_sql(job["source"]["query"], dialect).ok, job["name"]
