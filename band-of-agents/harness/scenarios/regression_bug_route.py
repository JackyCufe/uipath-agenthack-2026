"""
regression_bug_route.py — 回归 bug 路由到 S3 场景

客户反馈描述了一个已交付需求的回归问题。
routing-agent 应匹配到历史需求，诊断为 tech_bug，路由到 S3 场景测试。
验证完整链路：匹配 → 诊断 → 路由 → 卡片发送 → trace 写入。
"""
from __future__ import annotations

from harness.core.loop_engine import ScriptedStep, run_scripted
from harness.core.asserts import (
    assert_routed,
    assert_routing_target,
    assert_entry_stage,
    assert_diagnosis_type,
    assert_matched_requirement,
    assert_severity,
    assert_feedback_trace_written,
    assert_card_sent,
)
from harness.core.protocol import TestInput
from harness.adapters.band_routing import BandRoutingHarness

# ── 测试数据 ──

BITABLE_HISTORY = [
    {
        "requirement_id": "REQ-089",
        "title": "搜索功能优化",
        "searchable_text": "搜索功能 搜索结果 相关度 ranking模型 移动端搜索 Top3相关度",
        "stage_data": {
            "S1": {
                "customer_who": "XX公司",
                "usage_scenario": "移动端搜索",
                "problem": "搜索结果不准，Top3经常不相关",
                "expected_outcome": "Top3相关度>80%",
            },
            "S2": {
                "acceptance_criteria": "Top3相关度>80%",
                "feature_def": "ranking模型优化",
                "priority": "P0",
            },
            "S3": {
                "tech_plan": "ranking模型调整，增加用户行为权重",
                "workload_days": "5",
                "test_cases": [
                    "TC-001: 搜索'笔记本电脑'，验证Top3相关度",
                    "TC-002: 搜索'手机壳'，验证Top3相关度",
                ],
            },
            "S4": {
                "version": "v2.3.1",
                "release_date": "2026-03-15",
                "scenario_verified": "是",
            },
            "S5": {
                "satisfaction": "88%",
                "feedback_summary": "搜索结果明显改善",
            },
            "S6": {
                "retrospective": "正常交付，ranking模型调整效果良好",
                "process_health_score": 85,
            },
        },
    },
    {
        "requirement_id": "REQ-045",
        "title": "搜索性能调优",
        "searchable_text": "搜索性能 响应时间 搜索慢 查询优化",
        "stage_data": {
            "S1": {"customer_who": "YY公司", "problem": "搜索响应慢"},
            "S2": {"acceptance_criteria": "响应<2秒"},
            "S4": {"version": "v2.1.0"},
        },
    },
]

FEEDBACK_TEXT = "之前修复的搜索功能最近又出问题了，搜索结果又不准了，跟上次一样"
CUSTOMER_ID = "XX公司"


async def run() -> bool:
    harness = BandRoutingHarness(bitable_history=BITABLE_HISTORY)

    steps = [
        ScriptedStep(
            description="注入客户反馈：搜索回归bug",
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
            description="验证匹配到历史需求 REQ-089",
            action=lambda h: None,
            assertion=lambda h: assert_matched_requirement(h, "REQ-089"),
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
            description="验证严重程度为 normal",
            action=lambda h: None,
            assertion=lambda h: assert_severity(h, "normal"),
        ),
        ScriptedStep(
            description="验证 feedback_trace 已写入",
            action=lambda h: None,
            assertion=assert_feedback_trace_written,
        ),
        ScriptedStep(
            description="验证飞书卡片已发送给测试负责人",
            action=lambda h: None,
            assertion=assert_card_sent,
        ),
    ]

    report = await run_scripted(harness, steps, "regression_bug_route")
    return report.passed
