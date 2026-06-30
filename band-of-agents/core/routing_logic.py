"""
routing_logic.py — Core routing agent business logic.

Platform-agnostic. Receives injected interfaces (KB, LLM, Card, Messaging).
No platform SDK imports.

This is the brain: intent recognition → search history → AI diagnosis →
routing decision → notify handler.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.data_models import RoutingDecision, FeedbackTrace, DIAGNOSIS_TO_STAGE
from core.i18n import t, get_lang
from core.config import get_settings
from interfaces.llm import LLMInterface, LLMResponse
from interfaces.knowledge_base import KnowledgeBaseInterface
from interfaces.card import CardInterface
from interfaces.messaging import MessagingInterface


class RoutingLogic:
    """Core routing logic, platform-agnostic.

    Injected dependencies:
        llm: LLMInterface — for AI diagnosis and summary generation
        kb: KnowledgeBaseInterface — for searching historical requirements
        card: CardInterface — for building notification cards
        messaging: MessagingInterface — for sending cards to recipients
    """

    def __init__(
        self,
        llm: LLMInterface,
        kb: KnowledgeBaseInterface,
        card: CardInterface,
        messaging: MessagingInterface,
    ) -> None:
        self.llm = llm
        self.kb = kb
        self.card = card
        self.messaging = messaging
        self._settings = get_settings()

        # Load routing prompt based on language
        if get_lang() == "en":
            prompt_path = Path(__file__).parent.parent / "band-routing" / "prompts" / "routing_prompt_en.md"
        else:
            prompt_path = Path(__file__).parent.parent / "band-routing" / "prompts" / "routing_prompt.md"

        if prompt_path.exists():
            self._routing_prompt: str = prompt_path.read_text(encoding="utf-8")
        else:
            self._routing_prompt = ""

    def identify_intent(self, content: str) -> str:
        """Identify the intent of a message.

        Args:
            content: The message content

        Returns:
            "query" if content starts with "?", "feedback" otherwise.
        """
        if content.strip().startswith("?"):
            return "query"
        return "feedback"

    def process_feedback(
        self,
        feedback_text: str,
        customer_id: str = "",
        product_model: str = "",
    ) -> RoutingDecision:
        """Process customer feedback and return a routing decision.

        This is the core method. Harness tests call this directly.

        Args:
            feedback_text: Customer feedback text
            customer_id: Customer identifier
            product_model: Product model for hard constraint filtering

        Returns:
            RoutingDecision with diagnosis, entry stage, and target agent.
        """
        # Step 1: Search history
        history_results: list[dict[str, Any]] = self.kb.search(
            feedback_text, top_k=5, product_model=product_model
        )

        matched_requirement: dict[str, Any] | None = None
        if history_results:
            matched_requirement = history_results[0]
            # Step 2: Get full chain
            full_chain = self.kb.get_chain(matched_requirement.get("requirement_id", ""))
            if full_chain:
                matched_requirement = full_chain

        # Step 3: AI diagnosis
        diagnosis = self._diagnose(feedback_text, matched_requirement)

        # Step 4: Determine entry stage (deterministic mapping)
        diag_type = diagnosis.get("diagnosis_type", "new_requirement")
        stage_info = DIAGNOSIS_TO_STAGE.get(diag_type, DIAGNOSIS_TO_STAGE["new_requirement"])

        decision = RoutingDecision(
            diagnosis_type=diag_type,
            matched_requirement_id=matched_requirement.get("requirement_id") if matched_requirement else None,
            matched_requirement_title=matched_requirement.get("title") if matched_requirement else None,
            entry_stage=stage_info["entry_stage"],
            entry_reason=diagnosis.get("entry_reason", ""),
            severity=diagnosis.get("severity", "normal"),
            context_summary=self._build_context_summary(feedback_text, matched_requirement, diag_type),
            target_agent=stage_info["target_agent"],
        )

        # Step 5: Write feedback trace
        trace = FeedbackTrace(
            original_feedback=feedback_text,
            customer_id=customer_id,
            diagnosis_type=decision.diagnosis_type,
            matched_requirement_id=decision.matched_requirement_id,
            entry_stage=decision.entry_stage,
            severity=decision.severity,
            routing_target=decision.target_agent,
        )
        self.kb.write_trace(trace.to_dict())

        return decision

    def notify_handler(
        self,
        decision: RoutingDecision,
        feedback_text: str,
        customer_id: str,
        owner_open_id: str,
        owner_name: str,
    ) -> dict[str, Any]:
        """Send a routing notification card to the handler.

        Args:
            decision: The routing decision
            feedback_text: Original feedback text
            customer_id: Customer identifier
            owner_open_id: Handler's platform-specific ID
            owner_name: Handler's display name

        Returns:
            {"ok": bool, "message_id": str, "error": str | None}
        """
        card_json = self.card.build_routing_card(
            feedback_text=feedback_text,
            customer_id=customer_id,
            diagnosis_type=decision.diagnosis_type,
            matched_requirement_id=decision.matched_requirement_id,
            entry_stage=decision.entry_stage,
            severity=decision.severity,
            entry_reason=decision.entry_reason,
            context_summary=decision.context_summary,
            role_name=owner_name,
        )
        return self.messaging.send_card(owner_open_id, card_json)

    def send_confirm_card(
        self,
        feedback_text: str,
        product_model: str,
        customer_id: str,
        customer_open_id: str,
    ) -> dict[str, Any]:
        """Send a confirmation card to the customer before routing.

        Args:
            feedback_text: Original feedback
            product_model: Product model
            customer_id: Customer identifier
            customer_open_id: Customer's platform-specific ID

        Returns:
            {"ok": bool, "message_id": str, "error": str | None}
        """
        ai_summary = self._generate_feedback_summary(feedback_text)
        card_json = self.card.build_confirm_card(
            feedback_text=feedback_text,
            product_model=product_model,
            customer_id=customer_id,
            ai_summary=ai_summary,
        )
        return self.messaging.send_card(customer_open_id, card_json)

    def _diagnose(self, feedback_text: str, matched_requirement: dict[str, Any] | None) -> dict[str, Any]:
        """Call LLM to diagnose the issue type."""
        # Build context
        context = ""
        if matched_requirement:
            stage_data = matched_requirement.get("stage_data", {})
            if get_lang() == "en":
                context = f"\n\nHistorical Requirement Archive:\n"
                context += f"Requirement ID: {matched_requirement.get('requirement_id', '')}\n"
                context += f"Title: {matched_requirement.get('title', '')}\n"
            else:
                context = f"\n\n历史需求档案:\n"
                context += f"需求ID: {matched_requirement.get('requirement_id', '')}\n"
                context += f"标题: {matched_requirement.get('title', '')}\n"
            for stage, data in stage_data.items():
                context += f"{stage}: {json.dumps(data, ensure_ascii=False)[:200]}\n"
        else:
            if get_lang() == "en":
                context = "\n\nNo matching historical requirement (new requirement).\n"
            else:
                context = "\n\n无匹配的历史需求档案（全新需求）。\n"

        if get_lang() == "en":
            user_message = f"Customer feedback: {feedback_text}\nCustomer ID: {matched_requirement.get('requirement_id', 'unknown') if matched_requirement else 'unknown'}{context}\n\nPlease diagnose the issue type and return a routing decision JSON."
        else:
            user_message = f"客户反馈: {feedback_text}\n客户标识: {matched_requirement.get('requirement_id', 'unknown') if matched_requirement else 'unknown'}{context}\n\n请诊断问题类型并返回路由决策 JSON。"

        result = self.llm.chat_with_json_output(
            system_prompt=self._routing_prompt,
            user_message=user_message,
            max_tokens=1024,
        )

        if result:
            return result

        # Fallback: default to new_requirement
        return {
            "diagnosis_type": "new_requirement",
            "severity": "normal",
            "entry_reason": "LLM diagnosis failed, fallback to new requirement",
        }

    def _generate_feedback_summary(self, feedback_text: str) -> str:
        """Generate a short AI summary of the feedback for the confirm card."""
        if get_lang() == "en":
            system = "You are a customer service assistant. Summarize the customer's feedback in one sentence, under 50 words."
            user = f"Customer feedback: {feedback_text}\n\nSummarize in one sentence."
        else:
            system = "你是一个客服助手。用一句话总结客户的反馈内容，不超过50字。"
            user = f"客户反馈：{feedback_text}\n\n请用一句话总结。"

        try:
            response = self.llm.chat(system, user, max_tokens=128)
            return response.text.strip()
        except Exception:
            return ""

    def _build_context_summary(
        self,
        feedback_text: str,
        matched_requirement: dict[str, Any] | None,
        diag_type: str,
    ) -> str:
        """Generate a context summary using LLM, tailored to the routing target."""
        entry_stage = DIAGNOSIS_TO_STAGE.get(diag_type, {}).get("entry_stage", 1)

        raw_data: dict[str, Any] = {"feedback": feedback_text}
        if matched_requirement:
            raw_data["requirement_id"] = matched_requirement.get("requirement_id", "")
            raw_data["title"] = matched_requirement.get("title", "")
            raw_data["stage_data"] = matched_requirement.get("stage_data", {})
        else:
            raw_data["requirement_id"] = None
            raw_data["stage_data"] = {}

        if get_lang() == "en":
            role_hints = {
                1: "Highlight: who is the customer, what scenario, what problem, what expected outcome",
                2: "Highlight: acceptance criteria, priority, core value",
                3: "Highlight: technical solution, workload, test cases, how it was implemented",
                4: "Highlight: release version, release date, scenario verification",
                5: "Highlight: customer satisfaction, historical feedback summary",
            }
            role_hint = role_hints.get(entry_stage, "Highlight key information")
            prompt = f"""You are a requirement management assistant. Based on the following data, generate a concise context summary for a {diag_type} type issue.

Requirements:
- {role_hint}
- Write in natural language, no pipe-delimited fields
- Keep under 100 words
- Help the handler quickly understand the background

Data:
{json.dumps(raw_data, ensure_ascii=False, indent=2)[:2000]}

Output the summary text directly, no markers."""
            system = "You are a requirement management assistant skilled at generating concise context summaries."
        else:
            role_hints = {
                1: "突出：客户是谁、什么场景、遇到什么问题、期望什么结果",
                2: "突出：验收标准是什么、优先级如何、核心价值是什么",
                3: "突出：技术方案是什么、工作量多少、测试用例是什么、当时怎么实现的",
                4: "突出：发版版本、发版日期、场景验证情况",
                5: "突出：客户满意度、历史反馈摘要",
            }
            role_hint = role_hints.get(entry_stage, "突出关键信息")
            prompt = f"""你是一个需求管理系统的助手。请根据以下信息，为{diag_type}类型的问题生成一段简洁的上下文摘要。

要求：
- {role_hint}
- 用自然语言写，不要用竖线拼接
- 控制在100字以内
- 让接手的人快速了解背景

数据：
{json.dumps(raw_data, ensure_ascii=False, indent=2)[:2000]}

直接输出摘要文本，不要加任何标记。"""
            system = "你是一个需求管理助手，擅长生成简洁的上下文摘要。"

        try:
            response = self.llm.chat(system, prompt, max_tokens=256)
            summary = response.text.strip()
            if summary:
                return summary
        except Exception:
            pass

        # Fallback: mechanical concatenation
        parts = [f"{'Customer feedback' if get_lang() == 'en' else '客户反馈'}: {feedback_text[:100]}"]
        if matched_requirement:
            parts.append(f"{'Matched' if get_lang() == 'en' else '匹配需求'}: {matched_requirement.get('requirement_id', '')}")
        parts.append(f"{'Diagnosis' if get_lang() == 'en' else '诊断'}: {diag_type}")
        return " | ".join(parts)

    def _format_routing_message(self, decision: RoutingDecision) -> str:
        """Format a routing message for Band Room or logging."""
        return (
            f"[ROUTING] {json.dumps(decision.to_dict(), ensure_ascii=False)}\n\n"
            f"Routing decision: {decision.diagnosis_type} → S{decision.entry_stage}\n"
            f"Matched: {decision.matched_requirement_id or 'None'}\n"
            f"Severity: {decision.severity}\n"
            f"Context: {decision.context_summary}"
        )
