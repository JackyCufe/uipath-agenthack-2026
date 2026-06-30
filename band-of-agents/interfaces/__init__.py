"""
interfaces package — platform-agnostic abstract interfaces.

Four interfaces that platform implementations must satisfy:
- MessagingInterface: send/receive messages
- CardInterface: build/send/update interactive cards
- KnowledgeBaseInterface: search/read/write knowledge records
- LLMInterface: call LLM with tool_use loop
"""
from __future__ import annotations

from interfaces.messaging import MessagingInterface, MessageCallback
from interfaces.card import CardInterface, CardData, CardAction
from interfaces.knowledge_base import KnowledgeBaseInterface, SearchResult, RequirementChain
from interfaces.llm import LLMInterface, LLMResponse, LLMError

__all__ = [
    "MessagingInterface", "MessageCallback",
    "CardInterface", "CardData", "CardAction",
    "KnowledgeBaseInterface", "SearchResult", "RequirementChain",
    "LLMInterface", "LLMResponse", "LLMError",
]
