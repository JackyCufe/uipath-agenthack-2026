#!/usr/bin/env python3
"""
main_slack.py — Slack platform entry point (skeleton).

Demonstrates that switching platforms only requires:
1. A new main_<platform>.py entry file
2. Implementing the 4 interfaces for the new platform

This is a skeleton — interface implementations are stubs.
To make it functional, implement SlackSlackLLM, SlackKnowledgeBase, etc.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.routing_logic import RoutingLogic
from core.knowledge_logic import KnowledgeLogic
from interfaces.llm import LLMInterface, LLMResponse
from interfaces.knowledge_base import KnowledgeBaseInterface
from interfaces.card import CardInterface, CardAction
from interfaces.messaging import MessagingInterface, MessageCallback
from typing import Any, Callable, Awaitable


# ── Stub implementations (replace with real Slack SDK code) ──

class SlackLLM(LLMInterface):
    """Stub: Replace with Slack-compatible LLM (e.g., OpenAI, Claude)."""
    def chat(self, system_prompt: str, user_message: str, max_tokens: int = 1024,
             tools: list[dict[str, Any]] | None = None, tool_handler: Any = None) -> LLMResponse:
        raise NotImplementedError("Implement LLM call for Slack platform")

    def chat_with_json_output(self, system_prompt: str, user_message: str,
                              max_tokens: int = 1024) -> dict[str, Any] | None:
        raise NotImplementedError("Implement LLM JSON call for Slack platform")


class SlackKnowledgeBase(KnowledgeBaseInterface):
    """Stub: Replace with Slack-compatible KB (e.g., Pinecone, Notion)."""
    def search(self, keyword: str, top_k: int = 5, product_model: str = "") -> list[dict[str, Any]]:
        raise NotImplementedError("Implement knowledge base search for Slack platform")

    def get_chain(self, requirement_id: str) -> dict[str, Any] | None:
        raise NotImplementedError("Implement knowledge base get_chain for Slack platform")

    def update_record(self, requirement_id: str, fields: dict[str, Any]) -> bool:
        raise NotImplementedError

    def write_trace(self, trace: dict[str, Any]) -> bool:
        raise NotImplementedError


class SlackCard(CardInterface):
    """Stub: Replace with Slack Block Kit card builder."""
    def build_routing_card(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("Implement Slack Block Kit routing card")

    def build_confirm_card(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def build_resolved_card(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def build_knowledge_card(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def build_transfer_card(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError


class SlackMessaging(MessagingInterface):
    """Stub: Replace with Slack Bolt SDK messaging."""
    def send_message(self, recipient_id: str, content: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("Implement Slack message send")

    def send_card(self, recipient_id: str, card: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def start_listening(self, callback_handler: Callable[[MessageCallback], Awaitable[dict[str, Any]]]) -> None:
        raise NotImplementedError("Implement Slack Bolt WebSocket/Socket Mode listener")


def create_routing_logic() -> RoutingLogic:
    """Create RoutingLogic with Slack implementations."""
    return RoutingLogic(
        llm=SlackLLM(),
        kb=SlackKnowledgeBase(),
        card=SlackCard(),
        messaging=SlackMessaging(),
    )


def main():
    print("Slack platform skeleton — implement the 4 interfaces to activate.")
    print("See main_feishu.py for a working example.")


if __name__ == "__main__":
    main()
