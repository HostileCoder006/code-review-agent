"""
Shared agent tools: repository search, AST navigation, git history, etc.
These are injected into specialized agents.
"""
from __future__ import annotations

import re
from typing import Optional

import structlog

from app.intelligence.repo_context import RepoContext
from app.github.client import GitHubClient

log = structlog.get_logger(__name__)


def make_repo_tools(ctx: RepoContext, client: GitHubClient):
    """Return a dict of tool handlers bound to the current repo context."""

    async def search_code(query: str, file_pattern: Optional[str] = None) -> dict:
        """Search for a pattern across all parsed files in the repository."""
        results = []
        for path, ast in ctx.file_asts.items():
            if file_pattern and file_pattern not in path:
                continue
            # Search in raw content (if we have it)
            cf = next((f for f in ctx.changed_files if f.filename == path), None)
            content = (cf.raw_content if cf else None) or ""
            matches = []
            for i, line in enumerate(content.splitlines(), 1):
                if re.search(query, line, re.IGNORECASE):
                    matches.append({"line": i, "content": line.strip()})
            if matches:
                results.append({"file": path, "matches": matches[:10]})
        return {"results": results[:20], "total_files_searched": len(ctx.file_asts)}

    async def get_function_source(file_path: str, function_name: str) -> dict:
        """Return source code of a specific function."""
        ast = ctx.file_asts.get(file_path)
        if not ast:
            return {"error": f"File not found: {file_path}"}

        fn = next((f for f in ast.functions if f.name == function_name), None)
        if not fn:
            return {"error": f"Function '{function_name}' not found in {file_path}"}

        cf = next((f for f in ctx.changed_files if f.filename == file_path), None)
        if cf and cf.raw_content:
            lines = cf.raw_content.splitlines()
            source = "\n".join(lines[fn.line_start - 1:fn.line_end])
            return {"source": source, "line_start": fn.line_start, "line_end": fn.line_end}

        return {"error": "Source content not available"}

    async def get_callers(file_path: str, function_name: str) -> dict:
        """Find all callers of a function in the repository."""
        if not ctx.dependency_graph:
            return {"callers": []}
        callers = ctx.dependency_graph.get_callers_of(function_name)
        return {"function": function_name, "callers": callers}

    async def get_impact_set(file_path: str, function_name: str) -> dict:
        """Return the full impact set of changing a function."""
        key = f"{file_path}::{function_name}"
        impact = ctx.impact_map.get(key, [])
        return {"function": key, "impacted": impact, "count": len(impact)}

    async def get_file_diff(file_path: str) -> dict:
        """Return the PR diff patch for a specific file."""
        cf = next((f for f in ctx.changed_files if f.filename == file_path), None)
        if not cf:
            return {"error": "File not in PR diff"}
        return {
            "filename": cf.filename,
            "status": cf.status,
            "additions": cf.additions,
            "deletions": cf.deletions,
            "patch": cf.patch or "(no patch available)",
        }

    async def get_git_history(file_path: str) -> dict:
        """Retrieve recent commit history for a file."""
        try:
            commits = await client.get_commit_history(ctx.owner, ctx.repo, file_path)
            return {
                "file": file_path,
                "commits": [
                    {
                        "sha": c["sha"][:8],
                        "message": c["commit"]["message"][:200],
                        "author": c["commit"]["author"]["name"],
                        "date": c["commit"]["author"]["date"],
                    }
                    for c in commits[:15]
                ],
            }
        except Exception as e:
            return {"error": str(e)}

    async def get_imports(file_path: str) -> dict:
        """List all imports in a file."""
        ast = ctx.file_asts.get(file_path)
        if not ast:
            return {"error": "File not found"}
        return {
            "file": file_path,
            "imports": [
                {"module": i.module, "names": i.names, "line": i.line, "is_from": i.is_from}
                for i in ast.imports
            ],
        }

    async def list_changed_files() -> dict:
        """List all files changed in this PR."""
        return {
            "files": [
                {
                    "filename": cf.filename,
                    "status": cf.status,
                    "additions": cf.additions,
                    "deletions": cf.deletions,
                }
                for cf in ctx.changed_files
            ]
        }

    async def get_existing_tests(file_path: str) -> dict:
        """Return test files related to a given source file."""
        basename = file_path.replace("/", "_").replace(".py", "")
        related = [t for t in ctx.test_files if basename in t or basename.lstrip("_") in t]
        tests = []
        for tp in related[:3]:
            content = await client.get_file_content(ctx.owner, ctx.repo, tp, ctx.head_sha)
            if content:
                tests.append({"file": tp, "content": content[:3000]})
        return {"test_files": tests}

    async def search_similar_issues(keywords: str) -> dict:
        """Search existing issues for similar bug reports."""
        results = []
        for issue in ctx.recent_issues:
            text = f"{issue.get('title','')} {issue.get('body','')}"
            if any(kw.lower() in text.lower() for kw in keywords.split()):
                results.append({
                    "number": issue.get("number"),
                    "title": issue.get("title"),
                    "state": issue.get("state"),
                    "url": issue.get("html_url"),
                })
        return {"issues": results[:10]}

    return {
        "search_code": search_code,
        "get_function_source": get_function_source,
        "get_callers": get_callers,
        "get_impact_set": get_impact_set,
        "get_file_diff": get_file_diff,
        "get_git_history": get_git_history,
        "get_imports": get_imports,
        "list_changed_files": list_changed_files,
        "get_existing_tests": get_existing_tests,
        "search_similar_issues": search_similar_issues,
    }
