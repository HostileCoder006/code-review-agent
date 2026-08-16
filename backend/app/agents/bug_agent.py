"""
Bug/Logic Investigation Agent.
Investigates logic errors, type issues, race conditions, null dereferences, etc.
"""
from __future__ import annotations

import json
from typing import Any

from app.agents.base import BaseAgent, AgentTool
from app.agents.tools import make_repo_tools
from app.intelligence.repo_context import RepoContext
from app.github.client import GitHubClient
from app.llm.client import LLMClient


SYSTEM_PROMPT = """You are a senior software engineer specializing in bug detection.
Your job is to investigate the changed code in a GitHub pull request for logic errors,
type mismatches, race conditions, null dereferences, incorrect error handling,
off-by-one errors, and other correctness issues.

You MUST:
1. Use tools to inspect actual code before making claims.
2. Trace data flows — follow function calls across files.
3. Check callers of changed functions to find compatibility breaks.
4. Look at git history to see if similar code has broken before.
5. Only report issues you can support with code evidence.
6. Return findings as a JSON array in this EXACT format at the end:

```json
[
  {
    "title": "Short title",
    "description": "Detailed description of the issue",
    "hypothesis": "Why this is a bug",
    "severity": "critical|high|medium|low",
    "category": "bug",
    "file_path": "path/to/file.py",
    "line_start": 42,
    "line_end": 45,
    "function_name": "function_name",
    "evidence": ["evidence item 1", "evidence item 2"],
    "confidence": 0.85,
    "recommended_fix": "How to fix it"
  }
]
```

If you find no issues, return an empty array: []
Never invent bugs. If uncertain, set confidence below 0.6 and note the uncertainty.
"""


class BugAgent(BaseAgent):
    SYSTEM_PROMPT = SYSTEM_PROMPT

    def __init__(self, review_id: str, llm: LLMClient, ctx: RepoContext, client: GitHubClient):
        super().__init__(review_id, llm)
        tools = make_repo_tools(ctx, client)
        for name, handler in tools.items():
            schema = _get_tool_schema(name)
            if schema:
                self.register_tool(AgentTool(
                    name=name,
                    description=schema["description"],
                    parameters=schema["parameters"],
                    handler=handler,
                ))
        self._ctx = ctx

    def _build_prompt(self) -> str:
        changed_summary = "\n".join(
            f"- {cf.filename} ({cf.status}, +{cf.additions}/-{cf.deletions})"
            for cf in self._ctx.changed_files
        )
        return f"""Investigate this pull request for bugs and logic errors.

Repository: {self._ctx.owner}/{self._ctx.repo}
PR #{self._ctx.pr_number}

Changed files:
{changed_summary}

Start by calling list_changed_files(), then examine each changed file's diff with get_file_diff().
For any suspicious change, use get_function_source() and get_callers() to understand the full impact.
Use search_code() to find other usages of changed APIs.
Use get_git_history() to check if similar code has broken before.

Think carefully. Only report what you can prove with code evidence.
"""

    async def investigate(self) -> list[dict]:
        state = await self.run(self._build_prompt())
        return state.findings

    def _parse_findings(self, content: str):
        """Extract JSON findings array from final LLM response."""
        import re
        match = re.search(r"```json\s*(\[.*?\])\s*```", content, re.DOTALL)
        if match:
            try:
                self.state.findings = json.loads(match.group(1))
                return
            except json.JSONDecodeError:
                pass
        # Try bare JSON array
        match = re.search(r"(\[.*\])", content, re.DOTALL)
        if match:
            try:
                self.state.findings = json.loads(match.group(1))
            except json.JSONDecodeError:
                pass


def _get_tool_schema(name: str) -> dict | None:
    schemas = {
        "search_code": {
            "description": "Search for a regex pattern across all repository files",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Regex pattern to search for"},
                    "file_pattern": {"type": "string", "description": "Optional file path filter"},
                },
                "required": ["query"],
            },
        },
        "get_function_source": {
            "description": "Get source code of a specific function",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "function_name": {"type": "string"},
                },
                "required": ["file_path", "function_name"],
            },
        },
        "get_callers": {
            "description": "Find all callers of a function across the repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "function_name": {"type": "string"},
                },
                "required": ["file_path", "function_name"],
            },
        },
        "get_impact_set": {
            "description": "Get the full set of functions impacted by a change",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "function_name": {"type": "string"},
                },
                "required": ["file_path", "function_name"],
            },
        },
        "get_file_diff": {
            "description": "Get the PR diff patch for a specific file",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        },
        "get_git_history": {
            "description": "Get recent commit history for a file",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        },
        "get_imports": {
            "description": "List all imports in a file",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        },
        "list_changed_files": {
            "description": "List all files changed in this PR",
            "parameters": {"type": "object", "properties": {}},
        },
        "get_existing_tests": {
            "description": "Get test files related to a source file",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        },
        "search_similar_issues": {
            "description": "Search GitHub issues for similar bug reports",
            "parameters": {
                "type": "object",
                "properties": {"keywords": {"type": "string"}},
                "required": ["keywords"],
            },
        },
    }
    return schemas.get(name)
