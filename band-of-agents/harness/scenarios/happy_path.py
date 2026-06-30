"""
happy_path.py — 正向路由场景

客户反馈匹配到历史需求，诊断为 tech_bug，路由到 S3。
验证：routing-agent 正确诊断、@mention @s3-agent、飞书卡片已发、feedback_trace 已写。
"""
from __future__ import annotations

from harness.core.loop_engine import ScriptedStep, run_scripted
from harness.core.asserts import (
    assert_routed,
    assert_routing_target,
    assert_entry_stage,
    assert_diagnosis_type,
    assert_feedback_trace_written,
    assert_card_sent,
)
from harness.core.protocol import TestInput
from harness.adapters.band_routing import BandRoutingHarness

# ── 测试数据 ──────────────────────────────────────────

BITABLE_HISTORY = [
    {
        "requirement_id": "REQ-001",
        "title": "搜索功能优化",
        "searchable_text": "搜索功能 搜索结果 相关度 客户反馈搜索不准",
        "stage_data": {
            "S1": {
                "customer_who": "XX公司",
                "usage_scenario": "移动端搜索",
                "problem": "搜索结果不准",
                "expected_outcome": "Top3相关度>80%",
            },
            "S2": {
                "acceptance_criteria": "Top3相关度>80%",
                "priority": "P0",
            },
            "S3": {
                "tech_plan": "ranking模型调整",
                "workload_days": "5",
            },
            "S4": {
                "version": "v2.3.1",
                "release_date": "2026-03-15",
            },
            "S5": {
                "satisfaction": "88%",
            },
            "S6": {
                "retrospective": "正常交付",
            },
        },
    },
]

FEEDBACK_TEXT = "搜索功能最近结果不准，跟之前一样的问题"
CUSTOMER_ID = "XX公司"


async def run() -> bool:
    harness = BandRoutingHarness(bitable_history=BITABLE_HISTORY)

    steps = [
        ScriptedStep(
            description="注入客户反馈：搜索功能结果不准",
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
            description="验证诊断类型为 tech_bug",
            action=lambda h: None,
            assertion=lambda h: assert_diagnosis_type(h, "tech_bug"),
        ),
        ScriptedStep(
            description="验证路由切入阶段为 S3",
            action=lambda h: None,
            assertion=lambda h: assert_entry_stage(h, 3),
        ),
        ScriptedStep(
            description="验证路由目标为 @s3-agent",
            action=lambda h: None,
            assertion=lambda h: assert_routing_target(h, "@s3-agent"),
        ),
        ScriptedStep(
            description="验证 feedback_trace 已写入",
            action=lambda h: None,
            assertion=assert_feedback_trace_written,
        ),
        ScriptedStep(
            description="验证飞书卡片已发送给负责人",
            action=lambda h: None,
            assertion=assert_card_sent,
        ),
    ]

    report = await run_scripted(harness, steps, "happy_path")
    return report.passed
