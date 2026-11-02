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
    save_mode: str  # "disk": write pipelines/ only; "pull_request": also open a pull request (ADR-0017)
    github_token: str | None
    github_repository: str
    github_base_branch: str
    repository_pipelines_path: str

    @property
    def connections_dir(self) -> Path:
        """Folder of the connection files."""
        return self.pipelines_dir / "connections"

    @property
    def jobs_dir(self) -> Path:
        """Folder of the job files."""
        return self.pipelines_dir / "jobs"

    @classmethod
    def from_env(cls) -> Settings:
        """Settings from environment variables, with defaults for a checkout of the repository."""
        return cls(
            pipelines_dir=Path(os.environ.get("INGESTION_PIPELINES_DIR", REPO_ROOT / "pipelines")),
            templates_dir=Path(os.environ.get("INGESTION_TEMPLATES_DIR", REPO_ROOT / "code" / "templates")),
            save_mode=os.environ.get("SAVE_MODE", "disk"),
            github_token=os.environ.get("GITHUB_TOKEN") or None,
            github_repository=os.environ.get("ORCHESTRATION_REPOSITORY", "thanhphat2609/data-onboarding-orchestration"),
            github_base_branch=os.environ.get("ORCHESTRATION_BASE_BRANCH", "main"),
            repository_pipelines_path=os.environ.get("ORCHESTRATION_PIPELINES_PATH", "pipelines"),
        )
