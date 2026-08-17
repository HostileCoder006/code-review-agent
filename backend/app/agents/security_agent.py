"""
Security Investigation Agent.
Detects SQL injection, command injection, path traversal, hardcoded secrets,
broken auth, SSRF, insecure deserialization, and data-flow vulnerabilities.
"""
from __future__ import annotations

import json
import re

from app.agents.base import BaseAgent, AgentTool
from app.agents.bug_agent import _get_tool_schema
from app.agents.tools import make_repo_tools
from app.intelligence.repo_context import RepoContext
from app.github.client import GitHubClient
from app.llm.client import LLMClient


SYSTEM_PROMPT = """You are a senior application security engineer performing a security review.

Your goal is to identify REAL security vulnerabilities in the pull request changes, not theoretical ones.

Focus on:
1. SQL Injection — user input reaching SQL queries without parameterization
2. Command Injection — user input in subprocess/os.system calls
3. Path Traversal — user input used in file paths without sanitization
4. Hardcoded Secrets — API keys, passwords, tokens in code
5. Broken Authentication/Authorization — missing auth checks, privilege escalation
6. SSRF — user-controlled URLs used in server-side HTTP requests
7. Insecure Deserialization — pickle.loads(), yaml.load() with user data
8. Sensitive Data Leakage — PII/tokens in logs or API responses
9. Weak Cryptography — MD5/SHA1 for passwords, ECB mode, weak keys

IMPORTANT: Trace data flows. Don't flag issues based on keywords alone.
Follow: HTTP input → function calls → database/filesystem/network.
Use get_function_source() and search_code() to trace the actual flow.

Return findings as a JSON array:
```json
[
  {
    "title": "SQL Injection in get_user()",
    "description": "User-controlled input flows directly into a raw SQL query",
    "hypothesis": "The user_id parameter from the HTTP request is concatenated into SQL",
    "severity": "critical|high|medium|low",
    "category": "security",
    "subcategory": "sql_injection",
    "file_path": "app/db.py",
    "line_start": 42,
    "line_end": 44,
    "function_name": "get_user",
    "data_flow": ["request.args['user_id'] -> get_user(user_id) -> f'SELECT...{user_id}'"],
    "evidence": ["Line 43: query = f'SELECT * FROM users WHERE id = {user_id}'"],
    "confidence": 0.92,
    "recommended_fix": "Use parameterized queries: cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))"
  }
]
```

If no security issues are found, return [].
Do NOT flag issues without tracing the data flow to confirm the vulnerability path.
"""


class SecurityAgent(BaseAgent):
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
        return f"""Perform a security review of this pull request.

Repository: {self._ctx.owner}/{self._ctx.repo}
PR #{self._ctx.pr_number}

Changed files:
{changed_summary}

Steps:
1. Call list_changed_files() to get an overview.
2. For each changed file, call get_file_diff() to see what changed.
3. Call get_file_content() for suspicious files, especially non-Python code.
4. For suspicious Python patterns, call get_function_source() to see the full function.
5. Trace data flows — search_code() to find where user input enters the system.
6. Check get_imports() to identify security-relevant libraries when available.
7. Only report issues where you can trace the full vulnerable path.
"""

    async def investigate(self) -> list[dict]:
        state = await self.run(self._build_prompt())
        return state.findings

    def _parse_findings(self, content: str):
        match = re.search(r"```json\s*(\[.*?\])\s*```", content, re.DOTALL)
        if match:
            try:
                self.state.findings = json.loads(match.group(1))
                return
            except json.JSONDecodeError:
                pass
        match = re.search(r"(\[.*\])", content, re.DOTALL)
        if match:
            try:
                self.state.findings = json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
