"""
LLM client abstraction supporting OpenAI (and Anthropic as fallback).
Uses structured outputs and tool calling.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

log = structlog.get_logger(__name__)


class LLMClient:
    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.OPENAI_MODEL
        self._openai = None

    def _get_openai(self):
        if self._openai is None:
            from openai import AsyncOpenAI
            self._openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict:
        """Send a chat completion request and return the raw response dict."""
        client = self._get_openai()

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await client.chat.completions.create(**kwargs)

        # Convert to dict for uniform handling
        result = {
            "choices": [
                {
                    "message": {
                        "role": response.choices[0].message.role,
                        "content": response.choices[0].message.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in (response.choices[0].message.tool_calls or [])
                        ],
                    }
                }
            ],
            "usage": {
                "total_tokens": response.usage.total_tokens if response.usage else 0,
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        }

        log.debug(
            "llm_response",
            model=self.model,
            total_tokens=result["usage"]["total_tokens"],
            tool_calls=len(result["choices"][0]["message"]["tool_calls"]),
        )
        return result

    async def embed(self, text: str) -> list[float]:
        """Generate embeddings for semantic search."""
        client = self._get_openai()
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000],
        )
        return response.data[0].embedding
