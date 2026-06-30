"""
uipath_card.py — UiPath Action Center implementation of CardInterface.

Builds Action Center Form JSON for interactive task cards.
Replaces Feishu interactive cards with Action Center Task forms.
"""
from __future__ import annotations

from typing import Any

from interfaces.card import CardInterface, CardAction, CardError


class UiPathCard(CardInterface):
    """UiPath Action Center card/form implementation.

    Translates platform-agnostic CardData into Action Center Form JSON
    that can be used to create Action Center tasks.
    """

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
        """Build a routing notification card for Action Center."""
        stage_labels = {
            1: "S1 Gatekeeping",
            2: "S2 Value Transform",
            3: "S3 Engineering",
            4: "S4 Release Review",
            5: "S5 Feedback",
        }
        severity_icons = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}
        diag_labels = {
            "tech_bug": "Technical Bug",
            "service_issue": "Service Issue",
            "new_requirement": "New Requirement",
            "complaint": "Complaint",
        }

        return {
            "title": f"{severity_icons.get(severity, '🟡')} Customer Feedback Routed — {diag_labels.get(diagnosis_type, diagnosis_type)}",
            "type": "routing_notification",
            "sections": [
                {
                    "label": "Customer",
                    "value": customer_id,
                },
                {
                    "label": "Feedback",
                    "value": feedback_text,
                    "type": "textarea",
                },
                {
                    "label": "Diagnosis",
                    "value": diag_labels.get(diagnosis_type, diagnosis_type),
                },
                {
                    "label": "Routed To",
                    "value": f"{stage_labels.get(entry_stage, f'S{entry_stage}')} — {role_name}",
                },
                {
                    "label": "Routing Reason",
                    "value": entry_reason,
                    "type": "textarea",
                },
                {
                    "label": "Context Summary",
                    "value": context_summary,
                    "type": "textarea",
                },
                {
                    "label": "Matched Requirement",
                    "value": matched_requirement_id or "None (new)",
                },
            ],
            "actions": self._actions_to_list(actions) if actions else [
                {"action": "acknowledge", "label": "Acknowledge & Start"},
                {"action": "escalate", "label": "Escalate to Lead"},
            ],
        }

    def build_confirm_card(
        self,
        feedback_text: str,
        product_model: str,
        customer_id: str,
        ai_summary: str,
    ) -> dict[str, Any]:
        """Build a customer confirmation card."""
        return {
            "title": "Confirm Customer Feedback",
            "type": "confirm_feedback",
            "sections": [
                {"label": "Customer", "value": customer_id},
                {"label": "Product Model", "value": product_model or "Unknown"},
                {"label": "Feedback", "value": feedback_text, "type": "textarea"},
                {"label": "AI Summary", "value": ai_summary, "type": "textarea"},
            ],
            "actions": [
                {"action": "confirm", "label": "Confirm & Route"},
                {"action": "edit", "label": "Edit Feedback"},
                {"action": "cancel", "label": "Cancel"},
            ],
        }

    def build_resolved_card(
        self,
        customer_id: str,
        requirement_id: str,
        resolved_by: str,
        resolution_note: str,
    ) -> dict[str, Any]:
        """Build a resolution notification card."""
        return {
            "title": "Issue Resolved",
            "type": "resolution_notification",
            "sections": [
                {"label": "Customer", "value": customer_id},
                {"label": "Requirement", "value": requirement_id},
                {"label": "Resolved By", "value": resolved_by},
                {"label": "Resolution", "value": resolution_note, "type": "textarea"},
            ],
            "actions": [
                {"action": "acknowledge", "label": "Acknowledge"},
            ],
        }

    def build_knowledge_card(
        self,
        keyword: str,
        requirement: dict[str, Any],
        ai_summary: str,
    ) -> dict[str, Any]:
        """Build a knowledge query result card."""
        return {
            "title": f"Knowledge Search: {keyword}",
            "type": "knowledge_query_result",
            "sections": [
                {"label": "Keyword", "value": keyword},
                {"label": "Requirement ID", "value": requirement.get("requirement_id", "")},
                {"label": "Title", "value": requirement.get("title", "")},
                {"label": "AI Summary", "value": ai_summary, "type": "textarea"},
                {
                    "label": "Stage Data",
                    "value": str(requirement.get("stage_data", {}))[:500],
                    "type": "textarea",
                },
            ],
            "actions": [
                {"action": "view_full", "label": "View Full Record"},
                {"action": "search_again", "label": "Search Again"},
            ],
        }

    def build_transfer_card(
        self,
        requirement_id: str,
        feedback_text: str,
        contacts: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Build a transfer card for selecting a colleague."""
        contact_options = [
            {"label": f"{c.get('name', c.get('open_id', 'Unknown'))}", "value": c.get("open_id", "")}
            for c in contacts
        ]
        return {
            "title": "Transfer to Colleague",
            "type": "transfer_card",
            "sections": [
                {"label": "Requirement", "value": requirement_id},
                {"label": "Feedback", "value": feedback_text, "type": "textarea"},
                {"label": "Select Colleague", "value": "", "type": "dropdown", "options": contact_options},
            ],
            "actions": [
                {"action": "transfer", "label": "Transfer"},
                {"action": "cancel", "label": "Cancel"},
            ],
        }

    def _actions_to_list(self, actions: list[CardAction]) -> list[dict[str, str]]:
        """Convert CardAction list to plain dict list."""
        return [{"action": a.action, "label": a.label} for a in actions]
