"""
Builds a full repository context map from GitHub data.
Combines AST, dependency graph, git history, and PR diff.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

import structlog

from app.github.client import GitHubClient
from app.intelligence.ast_parser import parse_file, FileAST
from app.intelligence.dependency_graph import DependencyGraph

log = structlog.get_logger(__name__)

MAX_FILES_TO_PARSE = 200
PYTHON_EXTENSIONS = {".py"}


@dataclass
class ChangedFile:
    filename: str
    status: str          # added, modified, removed, renamed
    additions: int
    deletions: int
    patch: Optional[str]
    previous_filename: Optional[str]
    raw_content: Optional[str] = None
    previous_content: Optional[str] = None
    ast: Optional[FileAST] = None


@dataclass
class RepoContext:
    owner: str
    repo: str
    pr_number: int
    base_sha: str
    head_sha: str
    changed_files: list[ChangedFile] = field(default_factory=list)
    file_asts: dict[str, FileAST] = field(default_factory=dict)
    dependency_graph: Optional[DependencyGraph] = None
    commit_messages: list[str] = field(default_factory=list)
    recent_issues: list[dict] = field(default_factory=list)
    api_endpoints: list[dict] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    impact_map: dict[str, list[str]] = field(default_factory=dict)


async def build_repo_context(
    client: GitHubClient,
    owner: str,
    repo: str,
    pr_number: int,
    base_sha: str,
    head_sha: str,
) -> RepoContext:
    ctx = RepoContext(
        owner=owner, repo=repo, pr_number=pr_number,
        base_sha=base_sha, head_sha=head_sha,
    )

    # Fetch PR files, commits, and issues in parallel
    pr_files, commits, issues = await asyncio.gather(
        client.get_pr_files(owner, repo, pr_number),
        client.get_pr_commits(owner, repo, pr_number),
        client.list_issues(owner, repo, state="all", per_page=50),
        return_exceptions=True,
    )

    ctx.commit_messages = [
        c["commit"]["message"] for c in (commits if isinstance(commits, list) else [])
    ]
    ctx.recent_issues = issues if isinstance(issues, list) else []

    # Parse changed files
    changed: list[ChangedFile] = []
    for f in (pr_files if isinstance(pr_files, list) else []):
        cf = ChangedFile(
            filename=f["filename"],
            status=f["status"],
            additions=f.get("additions", 0),
            deletions=f.get("deletions", 0),
            patch=f.get("patch"),
            previous_filename=f.get("previous_filename"),
        )
        changed.append(cf)

    # Fetch file contents for Python files (head and base)
    async def fetch_contents(cf: ChangedFile):
        ext = "." + cf.filename.rsplit(".", 1)[-1] if "." in cf.filename else ""
        if ext not in PYTHON_EXTENSIONS:
            return
        cf.raw_content = await client.get_file_content(owner, repo, cf.filename, head_sha)
        if cf.status in ("modified", "renamed") and cf.previous_filename:
            cf.previous_content = await client.get_file_content(
                owner, repo, cf.previous_filename or cf.filename, base_sha
            )
        elif cf.status == "modified":
            cf.previous_content = await client.get_file_content(owner, repo, cf.filename, base_sha)

    await asyncio.gather(*[fetch_contents(cf) for cf in changed], return_exceptions=True)

    ctx.changed_files = changed

    # Parse ASTs for changed Python files
    for cf in changed:
        if cf.raw_content:
            ast = parse_file(cf.raw_content, cf.filename)
            ctx.file_asts[cf.filename] = ast

    # Fetch repo tree and parse a broader set for dependency analysis
    try:
        tree = await client.get_repo_tree(owner, repo, head_sha)
        py_files = [
            item["path"] for item in tree
            if item["type"] == "blob" and item["path"].endswith(".py")
        ]
        ctx.test_files = [p for p in py_files if "test" in p.lower()]
        ctx.config_files = [
            p for p in tree
            if isinstance(p, dict) and p.get("path", "").endswith(
                (".yaml", ".yml", ".toml", ".cfg", ".ini", ".env")
            )
        ]

        # Parse up to MAX_FILES for dep graph
        to_parse = [p for p in py_files if p not in ctx.file_asts][:MAX_FILES_TO_PARSE]
        async def parse_repo_file(path: str):
            content = await client.get_file_content(owner, repo, path, head_sha)
            if content:
                ctx.file_asts[path] = parse_file(content, path)

        await asyncio.gather(*[parse_repo_file(p) for p in to_parse], return_exceptions=True)
    except Exception as e:
        log.warning("repo_tree_fetch_failed", error=str(e))

    # Build dependency graph
    dg = DependencyGraph()
    dg.build(list(ctx.file_asts.values()))
    ctx.dependency_graph = dg

    # Build impact map for changed functions
    for cf in ctx.changed_files:
        if cf.filename not in ctx.file_asts:
            continue
        ast = ctx.file_asts[cf.filename]
        for fn in ast.functions:
            impacted = dg.get_impact_set(fn.name, cf.filename)
            if impacted:
                ctx.impact_map[f"{cf.filename}::{fn.name}"] = impacted

    log.info(
        "repo_context_built",
        changed_files=len(ctx.changed_files),
        parsed_files=len(ctx.file_asts),
        functions_impacted=sum(len(v) for v in ctx.impact_map.values()),
    )
    return ctx
