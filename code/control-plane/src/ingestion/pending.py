"""Saves that wait for their merge: the open pull requests of the Web UI on the orchestration repository.

The pull request is the only record of a save, so a connection or job that isn't merged yet exists only there. The lists
show it (marked ``pending``) so nobody saves it twice; nothing can use it until the merge. GitHub is asked at most once
every ``CACHE_SECONDS`` per kind, and a save clears the cache so its own pull request shows at once.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import yaml

from ingestion.github import GitHubError, PendingFile, PullRequestPublisher

logger = logging.getLogger(__name__)

CACHE_SECONDS = 15
Document = dict[str, Any]


class PendingSaves:
    def __init__(self, publisher: PullRequestPublisher | None, pipelines_path: str) -> None:
        """``publisher`` is None unless saves open pull requests; then nothing is ever pending."""
        self._publisher = publisher
        self._pipelines_path = pipelines_path
        self._cache: dict[str, tuple[float, list[PendingFile]]] = {}

    def clear(self) -> None:
        """Forgets what GitHub said, so the next list asks again."""
        self._cache.clear()

    def files(self, kind: str) -> list[PendingFile]:
        """Open pull requests' files of one kind (``connection`` or ``job``); empty if GitHub can't be asked."""
        if self._publisher is None:
            return []
        cached = self._cache.get(kind)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
        try:
            files = self._publisher.pending_files(f"ui/{kind}-", f"{self._pipelines_path}/{kind}s/")
        except GitHubError:
            logger.exception("Can't list the open pull requests; the lists show merged files only")
            files = []
        self._cache[kind] = (time.monotonic(), files)
        return files

    def documents(self, kind: str, merged: set[str]) -> list[tuple[Document, Document]]:
        """(document, pull request) of the saves waiting for a merge, without the names that are already merged."""
        documents: list[tuple[Document, Document]] = []
        for file in self.files(kind):
            try:
                document = yaml.safe_load(file.text)
            except yaml.YAMLError:
                continue
            if not isinstance(document, dict) or document.get("name") in merged:
                continue
            documents.append((document, {"number": file.pull.number, "url": file.pull.url, "branch": file.pull.branch}))
        return documents
