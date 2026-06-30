"""
asserts.py — 通用断言库

所有断言接受 harness（HarnessProtocol 实例），自动捕获状态后断言。
通用断言适用于任何流水线项目；项目特定断言放在 adapters/ 中。
"""
from __future__ import annotations

from .protocol import HarnessProtocol, SystemState


class AssertResult:
    def __init__(self, passed: bool, message: str = ""):
        self.passed = passed
        self.message = message

    def __bool__(self):
        return self.passed

    def __repr__(self):
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"{status}: {self.message}"


async def assert_stage(harness: HarnessProtocol, expected: int) -> AssertResult:
    state = await harness.inspect_state()
    if state.stage == expected:
        return AssertResult(True, f"Stage = {expected}")
    return AssertResult(False, f"Stage: expected {expected}, got {state.stage}")


async def assert_status(harness: HarnessProtocol, expected: str) -> AssertResult:
    state = await harness.inspect_state()
    if state.status == expected:
        return AssertResult(True, f"Status = '{expected}'")
    return AssertResult(False, f"Status: expected '{expected}', got '{state.status}'")


async def assert_routed(harness: HarnessProtocol) -> AssertResult:
    """验证系统已完成路由（status=routed）。"""
    state = await harness.inspect_state()
    if state.status == "routed":
        return AssertResult(True, "System routed successfully")
    return AssertResult(False, f"Expected status='routed', got '{state.status}'")


async def assert_routing_target(harness: HarnessProtocol, expected_agent: str) -> AssertResult:
    """验证路由目标 Agent 正确。"""
    state = await harness.inspect_state()
    if state.routing_target == expected_agent:
        return AssertResult(True, f"Routing target = {expected_agent}")
    return AssertResult(False, f"Routing target: expected {expected_agent}, got '{state.routing_target}'")


async def assert_entry_stage(harness: HarnessProtocol, expected: int) -> AssertResult:
    """验证路由切入阶段正确。"""
    state = await harness.inspect_state()
    if state.entry_stage == expected:
        return AssertResult(True, f"Entry stage = {expected}")
    return AssertResult(False, f"Entry stage: expected {expected}, got '{state.entry_stage}")


async def assert_diagnosis_type(harness: HarnessProtocol, expected: str) -> AssertResult:
    """验证诊断类型正确。"""
    state = await harness.inspect_state()
    if state.diagnosis_type == expected:
        return AssertResult(True, f"Diagnosis type = '{expected}'")
    return AssertResult(False, f"Diagnosis type: expected '{expected}', got '{state.diagnosis_type}'")


async def assert_severity(harness: HarnessProtocol, expected: str) -> AssertResult:
    """验证严重程度正确。"""
    state = await harness.inspect_state()
    if state.severity == expected:
        return AssertResult(True, f"Severity = '{expected}'")
    return AssertResult(False, f"Severity: expected '{expected}', got '{state.severity}'")


async def assert_matched_requirement(harness: HarnessProtocol, expected_id: str) -> AssertResult:
    """验证匹配到的历史需求 ID 正确。"""
    state = await harness.inspect_state()
    if state.matched_requirement_id == expected_id:
        return AssertResult(True, f"Matched requirement = {expected_id}")
    return AssertResult(False, f"Matched requirement: expected {expected_id}, got '{state.matched_requirement_id}'")


async def assert_feedback_trace_written(harness: HarnessProtocol) -> AssertResult:
    """验证 feedback_trace 知识库条目已写入。"""
    state = await harness.inspect_state()
    if state.feedback_trace_written:
        return AssertResult(True, "Feedback trace written")
    return AssertResult(False, "Feedback trace NOT written")


async def assert_card_sent(harness: HarnessProtocol) -> AssertResult:
    """验证飞书卡片已发送。"""
    output = await harness.capture()
    if output.card_sent:
        return AssertResult(True, "Card sent to Lark")
    return AssertResult(False, "No card sent")


async def assert_no_card_sent(harness: HarnessProtocol) -> AssertResult:
    """验证没有发飞书卡片（routing-agent 不应该直接发卡片）。"""
    output = await harness.capture()
    if not output.card_sent:
        return AssertResult(True, "No card sent (correct)")
    return AssertResult(False, "Unexpected card sent")


async def assert_rework_count(harness: HarnessProtocol, expected: int) -> AssertResult:
    state = await harness.inspect_state()
    if state.rework_count >= expected:
        return AssertResult(True, f"Rework count >= {expected} (got {state.rework_count})")
    return AssertResult(False, f"Rework count: expected >= {expected}, got {state.rework_count}")


async def assert_blocked(harness: HarnessProtocol) -> AssertResult:
    """验证硬门禁拦截。"""
    state = await harness.inspect_state()
    if state.status == "rejected":
        return AssertResult(True, "Hard gate blocked (status=rejected)")
    return AssertResult(False, f"Expected status='rejected' (blocked), got '{state.status}'")
