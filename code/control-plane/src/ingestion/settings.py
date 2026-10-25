"""Settings from environment variables, with defaults for running from a repository checkout."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# code/control-plane/src/ingestion/settings.py -> repository root
REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Settings:
    pipelines_dir: Path
    templates_dir: Path
    airflow_url: str
    airflow_username: str | None
    airflow_password: str | None

    @property
    def connections_dir(self) -> Path:
        return self.pipelines_dir / "connections"

    @property
    def jobs_dir(self) -> Path:
        return self.pipelines_dir / "jobs"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            pipelines_dir=Path(os.environ.get("INGESTION_PIPELINES_DIR", REPO_ROOT / "pipelines")),
            templates_dir=Path(os.environ.get("INGESTION_TEMPLATES_DIR", REPO_ROOT / "code" / "templates")),
            airflow_url=os.environ.get("AIRFLOW_API_URL", "http://localhost:8080").rstrip("/"),
            # Empty in non-prod: Airflow's simple auth manager makes everyone admin (all_admins mode).
            airflow_username=os.environ.get("AIRFLOW_USERNAME") or None,
            airflow_password=os.environ.get("AIRFLOW_PASSWORD") or None,
        )
