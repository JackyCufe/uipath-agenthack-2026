"""
knowledge_logic.py — Core knowledge query business logic.

Platform-agnostic. Searches knowledge base and generates AI summary.
No platform SDK imports.
"""
from __future__ import annotations

import json
from typing import Any

from core.i18n import t, get_lang
from interfaces.llm import LLMInterface
from interfaces.knowledge_base import KnowledgeBaseInterface
from interfaces.card import CardInterface
from interfaces.messaging import MessagingInterface


class KnowledgeLogic:
    """Core knowledge query logic, platform-agnostic.

    Injected dependencies:
        llm: LLMInterface — for AI summary generation
        kb: KnowledgeBaseInterface — for searching historical requirements
        card: CardInterface — for building knowledge result cards
        messaging: MessagingInterface — for sending cards
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

    def query(
        self,
        keyword: str,
        recipient_id: str = "",
    ) -> dict[str, Any]:
        """Execute a knowledge query and send result card.

        Args:
            keyword: Search keyword
            recipient_id: Platform-specific recipient ID for the result card

        Returns:
            {"ok": bool, "message": str, "card_sent": bool}
        """
        # Step 1: Search
        results = self.kb.search(keyword, top_k=5)

        if not results:
            # Send no-result card
            card_json = self.card.build_knowledge_card(keyword, {}, "")
            send_result = self.messaging.send_card(recipient_id, card_json)
            return {"ok": True, "message": "No results", "card_sent": send_result.get("ok", False)}

        # Step 2: Get full chain for best match
        best_match = results[0]
        full_chain = self.kb.get_chain(best_match.get("requirement_id", ""))
        if full_chain:
            best_match = full_chain

        # Step 3: Generate AI summary
        ai_summary = self._generate_answer(keyword, best_match)

        # Step 4: Build and send card
        card_json = self.card.build_knowledge_card(keyword, best_match, ai_summary)
        send_result = self.messaging.send_card(recipient_id, card_json)

        return {
            "ok": True,
            "message": "Query complete",
            "card_sent": send_result.get("ok", False),
        }

    def _generate_answer(self, keyword: str, requirement: dict[str, Any]) -> str:
        """Generate a natural language answer using LLM."""
        stage_data = requirement.get("stage_data", {})

        # Collect key info
        info: dict[str, Any] = {
            "requirement_id": requirement.get("requirement_id", ""),
            "title": requirement.get("title", ""),
            "stages": {},
        }
        for stage, data in stage_data.items():
            stage_info: dict[str, Any] = {}
            for k, v in data.items():
                if isinstance(v, str) and v:
                    stage_info[k] = v[:200]
                elif isinstance(v, list) and v:
                    for item in v:
                        if isinstance(item, dict):
                            stage_info[k] = item.get("en_name", item.get("name", ""))
                            break
                elif isinstance(v, (int, float)) and v:
                    stage_info[k] = str(v)
            if stage_info:
                info["stages"][stage] = stage_info

        if get_lang() == "en":
            prompt = f"""You are a knowledge base assistant for a new employee. A colleague asks: "{keyword}"
Here is the historical requirement record found:

{json.dumps(info, ensure_ascii=False, indent=2)[:3000]}

Please generate a natural language answer (under 200 words) covering:
1. What was the requirement about?
2. What was the technical solution?
3. What were the acceptance criteria?
4. What was the final result?
5. Any notes or lessons learned?

Write in English. Be concise and helpful."""
            system = "You are a knowledge base assistant."
        else:
            prompt = f"""你是一个新员工知识库助手。同事问："{keyword}"
以下是找到的历史需求记录：

{json.dumps(info, ensure_ascii=False, indent=2)[:3000]}

请生成一段自然语言回答（200字以内），涵盖：
1. 这个需求是关于什么的？
2. 技术方案是什么？
3. 验收标准是什么？
4. 最终结果如何？
5. 有什么注意事项或经验教训？

用中文回答，简洁有帮助。"""
            system = "你是一个知识库助手。"

        try:
            response = self.llm.chat(system, prompt, max_tokens=512)
            return response.text.strip()
        except Exception:
            return ""
