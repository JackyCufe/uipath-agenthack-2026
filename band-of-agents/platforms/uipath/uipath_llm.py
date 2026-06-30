"""
uipath_llm.py — UiPath LLM implementation of LLMInterface.

Reuses DeepSeek via OpenAI-compatible API (same as Feishu implementation).
Optionally switchable to UiPath AI Center via config.
"""
from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from interfaces.llm import LLMInterface, LLMResponse, LLMError
from core.config import get_settings


class UiPathLLM(LLMInterface):
    """LLM implementation for UiPath platform.

    By default uses DeepSeek (OpenAI-compatible), same as Feishu implementation.
    Can be switched to UiPath AI Center by changing config.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        self._model = settings.llm_model

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
        tools: list[dict[str, Any]] | None = None,
        tool_handler: Any = None,
    ) -> LLMResponse:
        """Call LLM with system + user message, with one retry."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            response = self._client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            text = choice.message.content or ""
            return LLMResponse(text=text, raw=response)
        except Exception as e:
            try:
                response = self._client.chat.completions.create(**kwargs)
                choice = response.choices[0]
                text = choice.message.content or ""
                return LLMResponse(text=text, raw=response)
            except Exception as e2:
                raise LLMError(f"LLM call failed after retry: {e2}") from e2

    def chat_with_json_output(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
    ) -> dict[str, Any] | None:
        """Call LLM and parse JSON from response."""
        response = self.chat(system_prompt, user_message, max_tokens)
        return self._extract_json(response.text)

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        """Extract JSON from LLM output text."""
        blocks = re.findall(r'```json\s*([\s\S]*?)\s*```', text)
        for block in blocks:
            try:
                return json.loads(block.strip())
            except json.JSONDecodeError:
                pass

        matches = re.findall(r'\{[\s\S]*\}', text)
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                repaired = self._repair_json(match)
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass
        return None

    def _repair_json(self, text: str) -> str:
        """Repair common LLM JSON output issues."""
        text = text.replace("None", "null")
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)
        return text
