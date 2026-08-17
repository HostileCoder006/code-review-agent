"""
Thin async GitHub REST client used by all agents and the orchestrator.
"""
from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote

import httpx
import structlog

from app.github.auth import get_installation_token

log = structlog.get_logger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubClient:
    def __init__(self, installation_id: int):
        self.installation_id = installation_id
        self._token: str | None = None

    async def _headers(self) -> dict[str, str]:
        self._token = await get_installation_token(self.installation_id)
        return {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def get(self, path: str, **kwargs) -> Any:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{GITHUB_API}{path}", headers=await self._headers(), **kwargs
            )
            resp.raise_for_status()
            return resp.json()

    async def post(self, path: str, json: dict, **kwargs) -> Any:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{GITHUB_API}{path}", headers=await self._headers(), json=json, **kwargs
            )
            resp.raise_for_status()
            return resp.json()

    async def patch(self, path: str, json: dict, **kwargs) -> Any:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(
                f"{GITHUB_API}{path}", headers=await self._headers(), json=json, **kwargs
            )
            resp.raise_for_status()
            return resp.json()

    # ── PR helpers ────────────────────────────────────────────────────────────

    async def get_pull_request(self, owner: str, repo: str, pr_number: int) -> dict:
        return await self.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")

    async def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        """Returns list of changed file objects with patch/diff."""
        files = []
        page = 1
        while True:
            batch = await self.get(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
                params={"per_page": 100, "page": page},
            )
            files.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return files

    async def get_pr_commits(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        return await self.get(f"/repos/{owner}/{repo}/pulls/{pr_number}/commits")

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str | None:
        try:
            encoded_path = quote(path, safe="/")
            data = await self.get(
                f"/repos/{owner}/{repo}/contents/{encoded_path}", params={"ref": ref}
            )
            if isinstance(data, dict) and data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        return None

    async def get_repo_tree(self, owner: str, repo: str, sha: str) -> list[dict]:
        commit = await self.get(f"/repos/{owner}/{repo}/git/commits/{sha}")
        tree_sha = commit.get("tree", {}).get("sha", sha)
        data = await self.get(
            f"/repos/{owner}/{repo}/git/trees/{tree_sha}",
            params={"recursive": "1"},
        )
        return data.get("tree", [])

    async def search_code(self, query: str, owner: str, repo: str) -> list[dict]:
        data = await self.get(
            "/search/code",
            params={"q": f"{query} repo:{owner}/{repo}", "per_page": 30},
        )
        return data.get("items", [])

    async def get_commit_history(self, owner: str, repo: str, path: str, per_page: int = 20) -> list[dict]:
        return await self.get(
            f"/repos/{owner}/{repo}/commits",
            params={"path": path, "per_page": per_page},
        )

    async def list_issues(self, owner: str, repo: str, state: str = "all", per_page: int = 30) -> list[dict]:
        return await self.get(
            f"/repos/{owner}/{repo}/issues",
            params={"state": state, "per_page": per_page},
        )

    # ── Review / checks ───────────────────────────────────────────────────────

    async def create_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        event: str = "COMMENT",
        comments: list[dict] | None = None,
    ) -> dict:
        payload: dict[str, Any] = {"body": body, "event": event}
        if comments:
            payload["comments"] = comments
        return await self.post(f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews", json=payload)

    async def create_check_run(self, owner: str, repo: str, payload: dict) -> dict:
        return await self.post(f"/repos/{owner}/{repo}/check-runs", json=payload)

    async def update_check_run(self, owner: str, repo: str, check_run_id: int, payload: dict) -> dict:
        return await self.patch(f"/repos/{owner}/{repo}/check-runs/{check_run_id}", json=payload)

