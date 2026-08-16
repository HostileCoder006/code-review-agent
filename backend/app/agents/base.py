"""
Base agent with structured state, retry limits, timeout, and tool-call tracking.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable, Optional
from dataclasses import dataclass, field

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings
from app.llm.client import LLMClient

log = structlog.get_logger(__name__)


@dataclass
class AgentTool:
    name: str
    description: str
    parameters: dict
    handler: Callable


@dataclass
class ToolCall:
    tool_name: str
    arguments: dict
    result: Any = None
    error: Optional[str] = None
    duration_ms: int = 0


@dataclass
class AgentState:
    agent_name: str
    review_id: str
    messages: list[dict] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    total_tokens: int = 0
    retries: int = 0
    findings: list[dict] = field(default_factory=list)
    completed: bool = False
    error: Optional[str] = None


class BaseAgent:
    """
    Base class for all specialized investigation agents.
    Manages LLM conversation, tool dispatch, retry/timeout logic.
    """

    SYSTEM_PROMPT = "You are an expert software engineer performing code review."
    MAX_TOOL_CALLS = settings.AGENT_MAX_TOOL_CALLS
    MAX_RETRIES = settings.AGENT_MAX_RETRIES
    TIMEOUT = settings.AGENT_TIMEOUT_SECONDS

    def __init__(self, review_id: str, llm: LLMClient):
        self.review_id = review_id
        self.llm = llm
        self.state = AgentState(
            agent_name=self.__class__.__name__,
            review_id=review_id,
        )
        self._tools: dict[str, AgentTool] = {}

    def register_tool(self, tool: AgentTool):
        self._tools[tool.name] = tool

    def _tool_schemas(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    async def _dispatch_tool(self, name: str, arguments: dict) -> Any:
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")
        start = time.monotonic()
        result = await tool.handler(**arguments)
        elapsed = int((time.monotonic() - start) * 1000)
        tc = ToolCall(tool_name=name, arguments=arguments, result=result, duration_ms=elapsed)
        self.state.tool_calls.append(tc)
        log.debug("tool_called", agent=self.state.agent_name, tool=name, duration_ms=elapsed)
        return result

    async def run(self, user_prompt: str) -> AgentState:
        """Run the agent loop with tool calls until completion or limits reached."""
        self.state.messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            async with asyncio.timeout(self.TIMEOUT):
                await self._agentic_loop()
        except asyncio.TimeoutError:
            self.state.error = f"Agent timed out after {self.TIMEOUT}s"
            log.warning("agent_timeout", agent=self.state.agent_name)
        except Exception as e:
            self.state.error = str(e)
            log.error("agent_error", agent=self.state.agent_name, error=str(e))

        self.state.completed = True
        return self.state

    async def _agentic_loop(self):
        tool_call_count = 0

        while tool_call_count < self.MAX_TOOL_CALLS:
            response = await self.llm.chat(
                messages=self.state.messages,
                tools=self._tool_schemas() if self._tools else None,
            )

            self.state.total_tokens += response.get("usage", {}).get("total_tokens", 0)
            message = response["choices"][0]["message"]
            self.state.messages.append(message)

            # No more tool calls — agent is done
            if not message.get("tool_calls"):
                # Extract structured findings from final message
                self._parse_findings(message.get("content", ""))
                break

            # Dispatch all tool calls in this turn
            for tc in message["tool_calls"]:
                tool_call_count += 1
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                    result = await self._dispatch_tool(tool_name, args)
                    result_str = json.dumps(result) if not isinstance(result, str) else result
                except Exception as e:
                    result_str = f"ERROR: {e}"

                self.state.messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str[:8000],  # truncate very large results
                })

        if tool_call_count >= self.MAX_TOOL_CALLS:
            log.warning("agent_max_tool_calls_reached", agent=self.state.agent_name)

    def _parse_findings(self, content: str):
        """Subclasses override this to extract structured findings from final LLM output."""
        pass
