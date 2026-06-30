"""
no_match_fallback.py — 无匹配降级场景

客户反馈在 Bitable 历史中找不到匹配，应降级为"全新需求"，路由到 S1。
验证：diagnosis_type=new_requirement, entry_stage=1, target=@s1-agent。
"""
from __future__ import annotations

from harness.core.loop_engine import ScriptedStep, run_scripted
from harness.core.asserts import (
    assert_routed,
    assert_routing_target,
    assert_entry_stage,
    assert_diagnosis_type,
)
from harness.core.protocol import TestInput
from harness.adapters.band_routing import BandRoutingHarness

# ── 测试数据：空历史，确保无匹配 ──
BITABLE_HISTORY = []

FEEDBACK_TEXT = "我们想要一个全新的数据导出功能，支持Excel格式"
CUSTOMER_ID = "NewClient"


async def run() -> bool:
    harness = BandRoutingHarness(bitable_history=BITABLE_HISTORY)

    steps = [
        ScriptedStep(
            description="注入客户反馈：全新需求（无历史匹配）",
            action=lambda h: h.inject(TestInput(
                kind="feedback",
                content=FEEDBACK_TEXT,
                customer_id=CUSTOMER_ID,
            )),
        ),
        ScriptedStep(
            description="验证系统已完成路由",
            action=lambda h: None,
            assertion=assert_routed,
        ),
        ScriptedStep(
            description="验证诊断类型为 new_requirement",
            action=lambda h: None,
            assertion=lambda h: assert_diagnosis_type(h, "new_requirement"),
        ),
        ScriptedStep(
            description="验证路由切入阶段为 S1",
            action=lambda h: None,
            assertion=lambda h: assert_entry_stage(h, 1),
        ),
        ScriptedStep(
            description="验证路由目标为 @s1-agent",
            action=lambda h: None,
            assertion=lambda h: assert_routing_target(h, "@s1-agent"),
        ),
    ]

    report = await run_scripted(harness, steps, "no_match_fallback")
    return report.passed
