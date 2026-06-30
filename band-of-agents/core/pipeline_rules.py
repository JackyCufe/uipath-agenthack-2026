"""
pipeline_rules.py — Core 6-stage pipeline rules.

Platform-agnostic. Defines flow rules, hard gates, rollback logic.
No platform SDK imports.
"""
from __future__ import annotations

from core.data_models import PIPELINE_STAGES, HARD_GATE_STAGE, HARD_GATE_FIELD, HARD_GATE_REQUIRED_VALUE, S1_MAX_RETRIES
from typing import Any


class PipelineRules:
    """Core pipeline flow rules, platform-agnostic."""

    @staticmethod
    def can_advance(current_stage: int, stage_data: dict[str, Any]) -> tuple[bool, str]:
        """Check if a requirement can advance to the next stage.

        Args:
            current_stage: Current stage number (1-6)
            stage_data: Current stage's form data

        Returns:
            (can_advance: bool, reason: str)
        """
        # Hard gate check at Stage 4
        if current_stage == HARD_GATE_STAGE:
            verified = stage_data.get(HARD_GATE_FIELD, False)
            if not verified:
                return False, "Hard gate: scenario not verified. Cannot proceed to release."

        # Normal advance
        if current_stage < 1 or current_stage >= 6:
            return False, f"Invalid stage: {current_stage}"

        return True, "OK"

    @staticmethod
    def get_next_stage(current_stage: int) -> int | None:
        """Get the next stage number.

        Args:
            current_stage: Current stage (1-6)

        Returns:
            Next stage number, or None if at final stage.
        """
        if current_stage < 1 or current_stage >= 6:
            return None
        return current_stage + 1

    @staticmethod
    def can_escalate(current_stage: int) -> tuple[bool, str]:
        """Check if escalation is allowed.

        Escalation replaces cross-stage rollback for BPMN compatibility.
        Instead of returning to a previous stage, the decision is escalated
        to a team lead who can approve, reject (terminate), or request info.

        Args:
            current_stage: Current stage

        Returns:
            (can_escalate: bool, reason: str)
        """
        if current_stage <= 1:
            return False, "Cannot escalate from Stage 1. Use retry or abandon."

        return True, "OK"

    @staticmethod
    def get_escalation_target(current_stage: int) -> dict[str, Any]:
        """Get the escalation decision structure.

        Replaces get_rollback_target(). Instead of returning to a previous
        stage, escalates to team lead. This is BPMN-compatible (forward flow
        with gateway branches) rather than cross-stage rollback.

        Args:
            current_stage: Current stage

        Returns:
            Dict with escalation details:
            - action: 'escalate'
            - target_role: 'team_lead'
            - on_approve: next stage number (forward)
            - on_reject: None (terminate pipeline)
            - on_info_needed: current stage (retry in place)
        """
        next_stage = current_stage + 1 if current_stage < 6 else None
        return {
            "action": "escalate",
            "target_role": "team_lead",
            "from_stage": current_stage,
            "on_approve": next_stage,
            "on_reject": None,  # terminate
            "on_info_needed": current_stage,  # retry in place
        }

    # ── Legacy rollback (deprecated, kept for backward compat) ──

    @staticmethod
    def can_rollback(current_stage: int, rework_count: int) -> tuple[bool, str]:
        """DEPRECATED: Use can_escalate() instead.

        Kept for backward compatibility with existing harness tests.
        Cross-stage rollback is not BPMN-compatible.
        """
        if current_stage <= 1:
            return False, "Cannot rollback from Stage 1."

        return True, "OK"

    @staticmethod
    def get_rollback_target(current_stage: int) -> int:
        """DEPRECATED: Use get_escalation_target() instead.

        Kept for backward compatibility. Cross-stage rollback violates
        BPMN 'no return to earlier phases for rework' principle.
        """
        if current_stage <= 1:
            return 1
        return current_stage - 1

    @staticmethod
    def check_s1_retry_limit(retry_count: int) -> tuple[bool, str]:
        """Check if S1 has exceeded the retry limit.

        Args:
            retry_count: Number of retries at S1

        Returns:
            (can_retry: bool, reason: str)
        """
        if retry_count >= S1_MAX_RETRIES:
            return False, f"S1 retry limit ({S1_MAX_RETRIES}) exceeded. Requirement rejected."
        return True, "OK"

    @staticmethod
    def get_stage_info(stage: int) -> dict[str, str]:
        """Get stage metadata.

        Args:
            stage: Stage number (1-6)

        Returns:
            Dict with 'stage', 'name', 'name_zh'.
        """
        for s in PIPELINE_STAGES:
            if s["stage"] == stage:
                return s
        return {"stage": str(stage), "name": "Unknown", "name_zh": "未知"}

    @staticmethod
    def get_entry_stage_for_diagnosis(diagnosis_type: str) -> int:
        """Get the entry stage for a diagnosis type.

        Args:
            diagnosis_type: tech_bug, service_issue, new_requirement, complaint

        Returns:
            Entry stage number (1-5).
        """
        from core.data_models import DIAGNOSIS_TO_STAGE
        info = DIAGNOSIS_TO_STAGE.get(diagnosis_type, DIAGNOSIS_TO_STAGE["new_requirement"])
        return info["entry_stage"]

    @staticmethod
    def extract_product_model(text: str, known_models: list[str] | None = None) -> str:
        """Extract product model from text.

        Args:
            text: Input text to search
            known_models: List of known product models (default: 9100, 8200, X1)

        Returns:
            Extracted product model string, or empty string if not found.
        """
        if known_models is None:
            known_models = ["9100", "8200", "X1"]
        for model in known_models:
            if model in text:
                return model
        return ""

    @staticmethod
    def extract_stage_owner(
        matched_requirement: dict[str, Any] | None,
        entry_stage: int,
        fallback_open_id: str = "",
        fallback_name: str = "",
    ) -> tuple[str, str]:
        """Extract the stage owner from a matched requirement's stage data.

        Args:
            matched_requirement: The matched requirement dict with stage_data
            entry_stage: The entry stage number
            fallback_open_id: Fallback open_id if not found in history
            fallback_name: Fallback name if not found in history

        Returns:
            (open_id, name)
        """
        if matched_requirement:
            stage_data = matched_requirement.get("stage_data", {})
            stage_key = f"S{entry_stage}"
            stage_fields = stage_data.get(stage_key, {})

            # Look for owner field
            for k, v in stage_fields.items():
                if "owner" in k.lower() or "负责人" in k:
                    if isinstance(v, list) and v:
                        person = v[0]
                        open_id = person.get("id", "")
                        name = person.get("en_name", person.get("name", ""))
                        if open_id:
                            return open_id, name

        return fallback_open_id, fallback_name
