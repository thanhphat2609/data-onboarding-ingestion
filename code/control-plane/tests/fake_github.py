"""A fake GitHub REST API for the pull request tests: one base commit, branches, files on branches, pull requests."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx


class FakeGitHub:
    """Just enough of the GitHub REST API: one base commit, branches, files on branches, pull requests."""

    def __init__(self, existing: dict[str, str] | None = None) -> None:
        self.files = existing or {}
        self.branches: dict[str, dict[str, str]] = {}
        self.pulls: list[dict[str, Any]] = []
        self.fail_with: int | None = None
        self.merged: set[str] = set()  # branches of pull requests that are no longer open

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
                if name not in branch:
                    return httpx.Response(404, json={})
                content = base64.b64encode(branch[name].encode()).decode()
                return httpx.Response(200, json={"sha": "blob1", "content": content})
            if name in self.branches[body["branch"]]:
                assert body["sha"] == "blob1", "replacing a file needs its current sha"
            self.branches[body["branch"]][name] = base64.b64decode(body["content"]).decode()
            return httpx.Response(201, json={})
        if path == "/pulls" and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "number": n,
                        "html_url": f"https://github.com/acme/orchestration/pull/{n}",
                        "head": {"ref": p["head"]},
                    }
                    for n, p in enumerate(self.pulls, start=1)
                    if p["head"] not in self.merged
                ],
            )
        if path.startswith("/pulls/") and path.endswith("/files"):
            branch = self.pulls[int(path.split("/")[2]) - 1]["head"]
            return httpx.Response(
                200, json=[{"filename": f, "status": "added"} for f in self.branches[branch] if f not in self.files]
            )
        if path == "/pulls":
            self.pulls.append(body)
            number = len(self.pulls)
            return httpx.Response(
                201, json={"number": number, "html_url": f"https://github.com/acme/orchestration/pull/{number}"}
            )
        raise AssertionError(f"unexpected {request.method} {path}")
