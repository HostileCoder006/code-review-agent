"""
Self-Review Agent — Reviewer of the Reviewer.
Audits all findings before publishing. Discards weak, speculative, or duplicate findings.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.agents.base import BaseAgent
from app.llm.client import LLMClient


SYSTEM_PROMPT = """You are a rigorous quality gate for a code review system.

You receive a list of findings from specialized agents. Your job is to:
1. Evaluate each finding critically
2. Discard findings that are weak, speculative, duplicate, or style-only
3. Downgrade severity where the evidence doesn't support it
4. Confirm findings that are well-supported

For each finding, answer:
- Is this actually a bug? (not just suspicious code)
- Is the severity justified by the evidence?
- Is the evidence sufficient? (real code quoted, not paraphrased)
- Could this behavior be intentional/by design?
- Is there already a test covering this?
- Is this merely a style preference?
- Is it a duplicate of another finding?
- Is the suggested fix safe and correct?

Return a JSON array with only the findings that pass review,
with an added "self_review_notes" field explaining your decision:

```json
[
  {
    ...original finding fields...,
    "self_review_notes": "Confirmed: traced data flow from HTTP input to raw SQL. No sanitization.",
    "severity": "high",
    "confidence": 0.91
  }
]
```

Discard findings by omitting them from the output.
It is better to publish 2 high-quality findings than 10 speculative ones.
Optimize for PRECISION over quantity.
"""


class SelfReviewAgent(BaseAgent):
    SYSTEM_PROMPT = SYSTEM_PROMPT

    def __init__(self, review_id: str, llm: LLMClient):
        super().__init__(review_id, llm)

    async def review_findings(self, findings: list[dict]) -> list[dict]:
        """Filter and improve findings before publishing."""
        if not findings:
            return []

        prompt = f"""Review these {len(findings)} finding(s) from our code review agents.
Apply the quality criteria strictly. Discard weak findings.

Findings to review:
```json
{json.dumps(findings, indent=2)}
```

Return only high-confidence, evidence-backed findings.
"""
        state = await self.run(prompt)
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
