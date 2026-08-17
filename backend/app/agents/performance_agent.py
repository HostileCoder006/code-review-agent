"""
Performance Investigation Agent.
Detects N+1 queries, O(n²) algorithms, unnecessary DB calls, memory leaks, etc.
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


SYSTEM_PROMPT = """You are a senior performance engineer reviewing a pull request.

Identify REAL performance issues, not theoretical ones. Focus on:

1. N+1 Queries — database queries inside loops
2. O(n²)/O(n³) algorithms — nested loops over large collections
3. Missing pagination — fetching unbounded result sets
4. Repeated expensive computations — same DB/API call in a loop
5. Unnecessary serialization/deserialization in hot paths
6. Missing caching for expensive, frequently-called operations
7. Memory accumulation — large lists built up without streaming
8. Synchronous blocking calls in async code
9. Missing database indexes (inferred from query patterns)
10. Inefficient data structures (list.index(), set vs list for lookups)

Use tools to:
- Read the actual function code before claiming it has a performance issue
- Check how the function is called (get_callers) to understand the usage pattern
- Estimate the complexity with evidence from the code

Return findings as JSON:
```json
[
  {
    "title": "N+1 query in get_orders_with_items()",
    "description": "SQL query executed inside a loop over orders",
    "hypothesis": "For N orders, this executes N+1 database queries",
    "severity": "high|medium|low",
    "category": "performance",
    "subcategory": "n_plus_one",
    "file_path": "app/orders.py",
    "line_start": 55,
    "line_end": 62,
    "function_name": "get_orders_with_items",
    "evidence": ["Line 57: for order in orders:", "Line 58:   items = db.query(Item).filter_by(order_id=order.id).all()"],
    "estimated_complexity": "O(n) queries",
    "confidence": 0.88,
    "recommended_fix": "Use a JOIN query or prefetch items in a single query"
  }
]
```

If no performance issues, return [].
"""


class PerformanceAgent(BaseAgent):
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
        return f"""Analyze this pull request for performance issues.

Repository: {self._ctx.owner}/{self._ctx.repo}
PR #{self._ctx.pr_number}

Changed files:
{changed_summary}

For each changed file:
1. Get the diff with get_file_diff()
2. Read the file with get_file_content(), then read full Python function source where available
3. Look for loops, database calls, and expensive operations
4. Check get_callers() to understand call frequency
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
