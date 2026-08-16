"""
Test/Regression Agent.
Generates minimal reproduction tests for suspected findings.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from app.agents.base import BaseAgent, AgentTool
from app.agents.bug_agent import _get_tool_schema
from app.agents.tools import make_repo_tools
from app.intelligence.repo_context import RepoContext
from app.github.client import GitHubClient
from app.llm.client import LLMClient


SYSTEM_PROMPT = """You are a senior software engineer who writes targeted tests to reproduce bugs.

Given a suspected finding, your job is to write the MINIMAL Python pytest test that:
1. Sets up the required code (inline — no external dependencies if possible)
2. Calls the function with the inputs that should trigger the bug
3. Asserts the WRONG behavior that the bug produces (test should FAIL on buggy code, PASS on fixed code)

Rules:
- Keep tests minimal — don't write large integration tests
- The test should be self-contained or require only stdlib + pytest
- Mock external dependencies (databases, HTTP) using unittest.mock
- The test MUST fail if the bug is present and pass if it's fixed
- Add a comment explaining what behavior the test is checking

Return a JSON object:
```json
{
  "test_code": "import pytest\\n\\ndef test_bug_name():\\n    ...",
  "test_name": "test_type_coercion_breaks_downstream",
  "description": "Tests that user_id remains a string after processing",
  "expected_behavior": "user_id should be '123' (str), not 123 (int)",
  "setup_requirements": ["pytest"],
  "should_fail_on_buggy_code": true
}
```
"""


class TestAgent(BaseAgent):
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

    async def generate_test(self, finding: dict) -> Optional[dict]:
        """Generate a reproduction test for a single finding."""
        prompt = f"""Generate a minimal pytest reproduction test for this finding:

Title: {finding.get('title')}
Description: {finding.get('description')}
File: {finding.get('file_path')}
Function: {finding.get('function_name')}
Lines: {finding.get('line_start')}-{finding.get('line_end')}
Evidence: {json.dumps(finding.get('evidence', []))}
Hypothesis: {finding.get('hypothesis')}

First, call get_function_source() to read the actual function code.
Then write a minimal test that reproduces the issue.
"""
        state = await self.run(prompt)
        return state.findings[0] if state.findings else None

    def _parse_findings(self, content: str):
        match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            try:
                self.state.findings = [json.loads(match.group(1))]
                return
            except json.JSONDecodeError:
                pass
        match = re.search(r"(\{.*\})", content, re.DOTALL)
        if match:
            try:
                self.state.findings = [json.loads(match.group(1))]
            except json.JSONDecodeError:
                pass
