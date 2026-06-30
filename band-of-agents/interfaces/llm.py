"""
llm.py — LLMInterface abstract definition.

Platform implementations provide LLM calls with tool_use support.
Core business logic calls these methods for diagnosis, summary generation, etc.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: Any = None  # Platform-specific raw response


class LLMError(Exception):
    """Raised when an LLM call fails after retries."""
    pass


class LLMInterface(ABC):
    """Abstract interface for LLM calls."""

    @abstractmethod
    def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
        tools: list[dict[str, Any]] | None = None,
        tool_handler: Any = None,
    ) -> LLMResponse:
        """Call the LLM with a system prompt and user message.

        Args:
            system_prompt: System prompt text
            user_message: User message text
            max_tokens: Maximum tokens in response
            tools: Optional tool definitions for tool_use
            tool_handler: Optional callable that receives tool name + args, returns result

        Returns:
            LLMResponse with text and optional tool_calls.

        Raises:
            LLMError: If the call fails after retries (default: 1 retry).
                     Implementations must implement retry + fallback.
        """
        ...

    @abstractmethod
    def chat_with_json_output(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
    ) -> dict[str, Any] | None:
        """Call the LLM and parse JSON from the response.

        Args:
            system_prompt: System prompt text
            user_message: User message text
            max_tokens: Maximum tokens in response

        Returns:
            Parsed JSON dict, or None if parsing fails.

        Note:
            Implementations should handle common LLM JSON output issues:
            - ```json code blocks
            - Trailing commas
            - Python None vs JSON null
        """
        ...
