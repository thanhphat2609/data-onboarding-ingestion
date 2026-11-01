"""Opens a pull request that adds or changes one file of the orchestration repository (ADR-0017).

The Web UI never writes to the repository that Airflow reads: a saved connection or job becomes a branch with one
commit and a pull request against the base branch. CI there validates the file, the Data Team reviews and merges.
Only the GitHub REST API is used (branches, contents, pull requests), so no git client is needed in the image.
"""

from __future__ import annotations

import base64
import datetime as dt
from dataclasses import dataclass
from typing import Any

import httpx

API_URL = "https://api.github.com"


class GitHubError(Exception):
    """GitHub refused the request or can't be reached; the message says what to fix."""


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str
    branch: str


class PullRequestPublisher:
    def __init__(
        self,
        token: str,
        repository: str,
        base_branch: str = "main",
        client: httpx.Client | None = None,
        now: dt.datetime | None = None,
    ) -> None:
        self.repository = repository
        self.base_branch = base_branch
        self._now = now
        self._client = client or httpx.Client(timeout=20)
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(
        self,
        method: str,
        path: str,
        ok: tuple[int, ...] = (200, 201),
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = f"{API_URL}/repos/{self.repository}{path}"
        try:
            response = self._client.request(method, url, headers=self._headers, json=json, params=params)
        except httpx.HTTPError as error:
            raise GitHubError(f"GitHub is unreachable: {error}") from None
        if response.status_code not in ok:
            try:
                message = str(response.json().get("message", ""))
            except ValueError:
                message = ""
            hint = ""
            if response.status_code in (401, 403, 404):
                hint = " (check GITHUB_TOKEN: Contents and Pull requests, read and write)"
            raise GitHubError(f"GitHub {method} {path}: {response.status_code} {message}{hint}")
        return response

    def open(self, path: str, content: str, title: str, body: str, branch_prefix: str) -> PullRequest:
        """Commits ``content`` as ``path`` on a new branch and opens a pull request for it."""
        base = self._request("GET", f"/git/ref/heads/{self.base_branch}").json()["object"]["sha"]
        stamp = (self._now or dt.datetime.now(dt.UTC)).strftime("%Y%m%d-%H%M%S")
        branch = f"{branch_prefix}-{stamp}"
        self._request("POST", "/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base})

        # An existing file is replaced, which GitHub only accepts with the blob sha of the current version.
        existing = self._request("GET", f"/contents/{path}", ok=(200, 404), params={"ref": branch})
        payload: dict[str, Any] = {
            "message": title,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if existing.status_code == 200:
            payload["sha"] = existing.json()["sha"]
        self._request("PUT", f"/contents/{path}", json=payload)

        pull = self._request(
            "POST", "/pulls", json={"title": title, "head": branch, "base": self.base_branch, "body": body}
        ).json()
        return PullRequest(number=int(pull["number"]), url=str(pull["html_url"]), branch=branch)
