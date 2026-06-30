"""
feishu_card.py — Feishu Card 2.0 implementation of CardInterface.

Builds Feishu-specific card JSON from platform-agnostic parameters.
"""
from __future__ import annotations

import os
from typing import Any

from interfaces.card import CardInterface, CardAction, CardError
from core.i18n import t, get_lang
from core.config import get_settings


class FeishuCard(CardInterface):
    """Feishu Card 2.0 implementation."""

    def _pt(self, content: str) -> dict[str, str]:
        return {"tag": "plain_text", "content": content}

    def _md(self, content: str) -> dict[str, str]:
        return {"tag": "lark_md", "content": content}

    def _div(self, text: dict[str, str]) -> dict[str, str]:
        return {"tag": "div", "text": text}

    def _hr(self) -> dict[str, str]:
        return {"tag": "hr"}

    def _field_row(self, label: str, value: str) -> dict[str, Any]:
        return {
            "tag": "column_set", "flex_mode": "none",
            "columns": [
                {"tag": "column", "width": "weighted", "weight": 1,
                 "elements": [self._div(self._md(f"**{label}**"))]},
                {"tag": "column", "width": "weighted", "weight": 3,
                 "elements": [self._div(self._pt(str(value) if value else "—"))]},
            ],
        }

    def build_routing_card(
        self,
        feedback_text: str,
        customer_id: str,
        diagnosis_type: str,
        matched_requirement_id: str | None,
        entry_stage: int,
        severity: str,
        entry_reason: str,
        context_summary: str,
        role_name: str,
        actions: list[CardAction] | None = None,
    ) -> dict[str, Any]:
        """Build a routing notification card."""
        diag_label = t(f"diagnosis.{diagnosis_type}") if diagnosis_type and diagnosis_type != "unknown" else t("diagnosis.unknown")
        matched_req = matched_requirement_id or t("placeholder.no_match")
        template = "red" if severity == "urgent" else "yellow"
        severity_icon = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}.get(severity, "🟡")

        elements: list[dict[str, Any]] = [
            self._div(self._md(f"📋 **{t('card.feedback_original')}**")),
            self._div(self._pt(feedback_text if feedback_text else t("placeholder.empty"))),
            self._hr(),
        ]

        if customer_id:
            elements.append(self._field_row(t("label.customer"), customer_id))
        elements.append(self._field_row(t("label.diagnosis_type"), diag_label))
        elements.append(self._field_row(t("label.matched_requirement"), matched_req))
        elements.append(self._field_row(t("label.entry_stage"), f"S{entry_stage}"))
        elements.append(self._field_row(t("label.severity"), severity))
        elements.append(self._hr())

        elements.append(self._div(self._md(f"🔍 **{t('card.routing_reason')}**")))
        reason_points = [s.strip() for s in entry_reason.replace("；", "。").split("。") if s.strip()]
        if len(reason_points) > 1:
            for pt_text in reason_points:
                elements.append(self._div(self._md(f"• {pt_text}")))
        else:
            elements.append(self._div(self._pt(entry_reason)))
        elements.append(self._hr())

        elements.append(self._div(self._md(f"📎 **{t('card.context_summary')}**")))
        elements.append(self._div(self._pt(context_summary)))
        elements.append(self._hr())

        elements.append(self._div(self._md(f"👉 **{t('prompt.handle', role=role_name)}**")))

        # Default actions if not provided
        if actions is None:
            req_id = matched_req if matched_req != t("placeholder.no_match") else ""
            btn_value = {
                "requirement_id": req_id,
                "entry_stage": entry_stage,
                "diagnosis_type": diag_label,
                "customer_id": customer_id,
            }
            actions = [
                CardAction(action="resolved", label=t("btn.resolved"), button_type="primary", value=btn_value),
                CardAction(action="escalate", label=t("btn.escalate"), button_type="default", value=btn_value),
                CardAction(action="transfer", label=t("btn.transfer"), button_type="default", value=btn_value),
            ]

        # Build buttons
        button_elements = []
        for act in actions:
            button_elements.append({
                "tag": "button",
                "text": self._pt(act.label),
                "type": act.button_type,
                "behaviors": [{"type": "callback", "value": {"action": act.action, **act.value}}],
            })

        elements.append({
            "tag": "column_set", "flex_mode": "none",
            "columns": [{"tag": "column", "width": "weighted", "weight": 1, "elements": button_elements}],
        })

        return {
            "schema": "2.0",
            "header": {"title": self._pt(f"{severity_icon} {t('card.routing_title')}"), "template": template},
            "body": {"elements": elements},
        }

    def build_confirm_card(self, feedback_text: str, product_model: str, customer_id: str, ai_summary: str) -> dict[str, Any]:
        """Build a customer confirmation card."""
        elements = [
            self._div(self._md(f"📋 **{t('card.confirm_prompt')}**")),
            self._hr(),
            self._field_row(t("label.customer"), customer_id or t("placeholder.dash")),
            self._field_row(t("label.product_model"), product_model or t("placeholder.dash")),
            self._div(self._md(f"**{t('label.feedback_text')}**")),
            self._div(self._pt(feedback_text)),
        ]
        if ai_summary:
            elements.append(self._hr())
            elements.append(self._div(self._md(f"🤖 **{t('card.ai_summary')}**")))
            elements.append(self._div(self._pt(ai_summary)))
        elements.append(self._hr())
        elements.append({
            "tag": "column_set", "flex_mode": "none",
            "columns": [{"tag": "column", "width": "weighted", "weight": 1, "elements": [
                {"tag": "button", "text": self._pt(t("btn.confirm")), "type": "primary",
                 "behaviors": [{"type": "callback", "value": {"action": "customer_confirm", "feedback_text": feedback_text, "product_model": product_model, "customer_id": customer_id}}]},
                {"tag": "button", "text": self._pt(t("btn.edit")), "type": "default",
                 "behaviors": [{"type": "callback", "value": {"action": "customer_edit", "feedback_text": feedback_text, "product_model": product_model, "customer_id": customer_id}}]},
            ]}],
        })
        return {"schema": "2.0", "header": {"title": self._pt(f"📝 {t('card.confirm_title')}"), "template": "blue"}, "body": {"elements": elements}}

    def build_resolved_card(self, customer_id: str, requirement_id: str, resolved_by: str, resolution_note: str) -> dict[str, Any]:
        """Build a resolution notification card."""
        elements = [
            self._div(self._md(f"✅ **{t('card.resolved_prompt')}**")),
            self._hr(),
            self._field_row(t("label.related_requirement"), requirement_id or t("placeholder.dash")),
            self._field_row(t("label.resolved_by"), resolved_by),
        ]
        if resolution_note:
            elements.append(self._hr())
            elements.append(self._div(self._md(f"**{t('label.resolution_note')}**")))
            elements.append(self._div(self._pt(resolution_note)))
        elements.append(self._hr())
        elements.append(self._div(self._md(t("card.thank_you"))))
        return {"schema": "2.0", "header": {"title": self._pt(f"✅ {t('card.resolved_title')}"), "template": "green"}, "body": {"elements": elements}}

    def build_knowledge_card(self, keyword: str, requirement: dict[str, Any], ai_summary: str) -> dict[str, Any]:
        """Build a knowledge query result card."""
        stage_data = requirement.get("stage_data", {})
        req_id = requirement.get("requirement_id", "")
        title = requirement.get("title", "")

        def _extract(fields_dict: dict, keywords: list[str]) -> str:
            for k, v in fields_dict.items():
                for kw in keywords:
                    if kw in k:
                        if isinstance(v, str):
                            return v
                        elif isinstance(v, list) and v:
                            for item in v:
                                if isinstance(item, dict):
                                    return item.get("en_name", item.get("name", ""))
            return ""

        s1 = stage_data.get("S1", {})
        s2 = stage_data.get("S2", {})
        s3 = stage_data.get("S3", {})
        s4 = stage_data.get("S4", {})
        s5 = stage_data.get("S5", {})
        s6 = stage_data.get("S6", {})

        if get_lang() == "en":
            labels = {"query": "Search Keyword", "req_id": "Requirement ID", "title": "Title",
                       "problem": "Problem", "expected": "Expected Outcome", "acceptance": "Acceptance Criteria",
                       "tech": "Technical Solution", "workload": "Workload", "test": "Test Result",
                       "version": "Version", "satisfaction": "Customer Satisfaction", "retro": "Retrospective",
                       "summary": "AI Summary"}
            card_title = "🔍 Knowledge Query Result"
        else:
            labels = {"query": "搜索关键词", "req_id": "需求ID", "title": "需求标题",
                       "problem": "问题描述", "expected": "期望结果", "acceptance": "验收标准",
                       "tech": "技术方案", "workload": "工作量", "test": "测试结论",
                       "version": "发版版本", "satisfaction": "客户满意度", "retro": "复盘结论",
                       "summary": "AI 摘要"}
            card_title = "🔍 知识查询结果"

        elements = [self._div(self._md(f"**{card_title}**")), self._hr(),
                     self._field_row(labels["query"], keyword),
                     self._field_row(labels["req_id"], req_id),
                     self._field_row(labels["title"], title), self._hr()]

        for label_key, stage, extract_kws in [
            ("problem", s1, ["问题", "problem"]), ("expected", s1, ["期望", "expected"]),
            ("acceptance", s2, ["验收", "标准", "acceptance"]), ("tech", s3, ["技术方案", "方案", "tech"]),
            ("workload", s3, ["工作量", "workload"]), ("test", s3, ["结论", "result", "自测"]),
            ("version", s4, ["版本", "version"]), ("satisfaction", s5, ["满意度", "satisfaction"]),
            ("retro", s6, ["复盘", "结论", "retro"])]:
            val = _extract(stage, extract_kws)
            if val:
                elements.append(self._field_row(labels[label_key], val[:100]))

        if ai_summary:
            elements.append(self._hr())
            elements.append(self._div(self._md(f"**🤖 {labels['summary']}**")))
            elements.append(self._div(self._pt(ai_summary)))

        return {"schema": "2.0", "header": {"title": self._pt(card_title), "template": "blue"}, "body": {"elements": elements}}

    def build_transfer_card(self, requirement_id: str, feedback_text: str, contacts: list[dict[str, str]]) -> dict[str, Any]:
        """Build a transfer card."""
        elements = [
            self._div(self._md(f"↗️ **{t('card.transfer_title')}**")),
            self._div(self._pt(t("card.transfer_original_req", req_id=requirement_id or t("placeholder.dash")))),
            self._div(self._pt(t("card.transfer_original_feedback", text=feedback_text[:80] + "..." if len(feedback_text) > 80 else feedback_text))),
            self._hr(),
            self._div(self._md(f"**Select a colleague to transfer to:**")),
        ]

        buttons = []
        for contact in contacts:
            buttons.append({
                "tag": "button", "text": self._pt(f"👤 {contact.get('name', '')}"), "type": "default",
                "behaviors": [{"type": "callback", "value": {
                    "action": "transfer_submit", "requirement_id": requirement_id,
                    "feedback_text": feedback_text,
                    "target_name": contact.get("name", ""),
                    "target_open_id": contact.get("open_id", ""),
                }}],
            })

        elements.append({
            "tag": "column_set", "flex_mode": "none",
            "columns": [{"tag": "column", "width": "weighted", "weight": 1, "elements": buttons}],
        })
        return {"schema": "2.0", "header": {"title": self._pt(f"↗️ {t('card.transfer_title')}"), "template": "orange"}, "body": {"elements": elements}}
