"""
data_models.py — Core business data structures.

Platform-agnostic data models used throughout the system.
No platform SDK imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EscalationDecision:
    """Escalation decision replacing cross-stage rollback.

    BPMN-compatible: flow always moves forward. When a stage reviewer
    disagrees, the decision is escalated to a team lead who can:
    - approve → advance to next stage
    - reject → terminate pipeline
    - info_needed → retry current stage (in-place loopback)
    """
    action: str = "escalate"  # escalate
    target_role: str = "team_lead"
    from_stage: int = 0
    on_approve: int | None = None  # next stage
    on_reject: int | None = None  # None = terminate
    on_info_needed: int = 0  # retry current stage

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target_role": self.target_role,
            "from_stage": self.from_stage,
            "on_approve": self.on_approve,
            "on_reject": self.on_reject,
            "on_info_needed": self.on_info_needed,
        }


@dataclass
class RoutingDecision:
    """The output of routing-agent's diagnosis and routing logic."""
    diagnosis_type: str = ""  # tech_bug | service_issue | new_requirement | complaint
    matched_requirement_id: str | None = None
    matched_requirement_title: str | None = None
    entry_stage: int = 0  # 1-6
    entry_reason: str = ""
    severity: str = "normal"  # urgent | normal | low
    context_summary: str = ""
    target_agent: str = ""  # @s1-agent etc

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "diagnosis_type": self.diagnosis_type,
            "matched_requirement_id": self.matched_requirement_id,
            "matched_requirement_title": self.matched_requirement_title,
            "entry_stage": self.entry_stage,
            "entry_reason": self.entry_reason,
            "severity": self.severity,
            "context_summary": self.context_summary,
            "target_agent": self.target_agent,
        }


@dataclass
class FeedbackTrace:
    """A feedback trace record for knowledge continuity."""
    original_feedback: str = ""
    customer_id: str = ""
    diagnosis_type: str = ""
    matched_requirement_id: str | None = None
    entry_stage: int = 0
    severity: str = "normal"
    routing_target: str = ""
    resolution: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "original_feedback": self.original_feedback,
            "customer_id": self.customer_id,
            "diagnosis_type": self.diagnosis_type,
            "matched_requirement_id": self.matched_requirement_id,
            "entry_stage": self.entry_stage,
            "severity": self.severity,
            "routing_target": self.routing_target,
            "resolution": self.resolution,
        }


# ── Diagnosis type → entry stage mapping (deterministic, no LLM) ──

DIAGNOSIS_TO_STAGE: dict[str, dict[str, Any]] = {
    "tech_bug":        {"entry_stage": 3, "target_agent": "@s3-agent"},
    "service_issue":   {"entry_stage": 2, "target_agent": "@s2-agent"},
    "new_requirement": {"entry_stage": 1, "target_agent": "@s1-agent"},
    "complaint":       {"entry_stage": 5, "target_agent": "@s5-agent"},
}


# ── Pipeline stage definitions ──

PIPELINE_STAGES: list[dict[str, str]] = [
    {"stage": 1, "name": "Gatekeeping", "name_zh": "守门"},
    {"stage": 2, "name": "Value Transform", "name_zh": "价值转化"},
    {"stage": 3, "name": "Engineering", "name_zh": "场景测试"},
    {"stage": 4, "name": "Release Review", "name_zh": "发版评审"},
    {"stage": 5, "name": "Feedback Collection", "name_zh": "反馈收集"},
    {"stage": 6, "name": "Retrospective", "name_zh": "复盘分析"},
]

# Hard gate: Stage 4 cannot proceed without scenario verification
HARD_GATE_STAGE = 4
HARD_GATE_FIELD = "scenario_verified"
HARD_GATE_REQUIRED_VALUE = True

# Max retry rounds before forced rejection at S1
S1_MAX_RETRIES = 3

# Session TTL in seconds
SESSION_TTL = 900  # 15 minutes
