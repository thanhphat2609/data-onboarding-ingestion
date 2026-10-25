"""Checks every file in pipelines/connections/ and pipelines/jobs/ with the same rules as the API and Airflow.

Exit code 1 when a file is invalid, so CI blocks the merge. Phase 3 folds this into ``ingestctl validate``.
Usage: python -m ingestion.validate
"""

from __future__ import annotations

import sys

from ingestion.settings import Settings
from ingestion.store import ConfigStore
from ingestion.templates import TemplateRegistry


def main() -> int:
    settings = Settings.from_env()
    store = ConfigStore(settings, TemplateRegistry(settings.templates_dir))
    connections, jobs = store.list_connections(), store.list_jobs()
    invalid = store.invalid_files()
    for file in invalid:
        print(f"::error file={file.path}::{file.error}")
    print(f"{len(connections)} valid connection(s), {len(jobs)} valid job(s), {len(invalid)} invalid file(s)")
    return 1 if invalid else 0


if __name__ == "__main__":
    sys.exit(main())
