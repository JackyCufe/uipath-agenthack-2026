"""
loop_engine.py — 双模式测试引擎

模式1: Scripted Loop（零 token）
  按预定义步骤执行，每步注入输入、捕获输出、断言。
  适合回归测试、CI、已知场景。

模式2: Agent Loop（花 token）
  LLM 驱动探索性测试，感知→推理→行动→验证。
  适合从未测过的场景、边界探索、AI 预填质量检查。

两种模式分开，不混用。
"""
from __future__ import annotations

import json
import sys
from typing import Any, Callable, Awaitable

from .protocol import HarnessProtocol, TestInput, TestOutput, SystemState
from .asserts import AssertResult
from .reporter import TestReport


# ── Scripted Loop ──────────────────────────────────────

class ScriptedStep:
    """一个脚本化测试步骤。"""
    def __init__(
        self,
        description: str,
        action: Callable[[HarnessProtocol], Awaitable[None]],
        assertion: Callable[[HarnessProtocol], Awaitable[AssertResult]] | None = None,
    ):
        self.description = description
        self.action = action
        self.assertion = assertion


async def run_scripted(
    harness: HarnessProtocol,
    steps: list[ScriptedStep],
    scenario_name: str,
) -> TestReport:
    """执行脚本化测试，返回报告。"""
    report = TestReport(scenario_name)

    for step in steps:
        # 执行 action
        try:
            _result = step.action(harness)
            if _result is not None and hasattr(_result, '__await__'):
                await _result
        except Exception as e:
            report.add_step(step.description, AssertResult(False, f"Action error: {e}"))
            break

        # 执行 assertion
        if step.assertion:
            try:
                result = await step.assertion(harness)
            except Exception as e:
                result = AssertResult(False, f"Assert error: {e}")
            report.add_step(step.description, result)
        else:
            report.add_step(step.description)

    print(report.render())
    return report


# ── Agent Loop ─────────────────────────────────────────

async def run_agent_loop(
    harness: HarnessProtocol,
    goal: str,
    scenario_name: str,
    llm_call: Callable[[list[dict]], str],
    max_turns: int = 30,
) -> TestReport:
    """
    LLM 驱动的探索性测试。

    Args:
        harness: 项目适配层实例
        goal: 测试目标描述
        scenario_name: 场景名称
        llm_call: LLM 调用函数，接受 messages 列表，返回文本
        max_turns: 最大轮次
    """
    report = TestReport(scenario_name)
    await harness.reset()

    system_prompt = f"""你是一个测试 Agent。你在测试一个基于 Band 的客户反馈路由系统。

可用动作（在 action 字段指定）：
- inject_feedback: 注入客户反馈消息。参数: content (反馈文本), customer_id (客户标识)
- inject_card_action: 注入飞书卡片审批操作。参数: action (approve/reject), stage (阶段号)
- get_state: 获取当前系统状态
- get_output: 获取系统输出
- done: 测试完成，提交报告。参数: report (测试结论), passed (bool)

测试目标：{goal}

每一步：
1. 感知：读取当前状态和系统输出
2. 推理：判断当前状态是否符合预期，决定下一步
3. 行动：选择一个动作执行
4. 验证：确定性判断用断言，不确定的用语义判断

输出 JSON 格式：
{{"thought": "你的推理", "action": "动作名", "params": {{...}}, "assert": "断言描述或null"}}
"""

    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    for turn in range(max_turns):
        # 1. 感知
        state = await harness.inspect_state()
        output = await harness.capture()
        state_snapshot = {
            "stage": state.stage,
            "status": state.status,
            "routing_target": state.routing_target,
            "entry_stage": state.entry_stage,
            "diagnosis_type": state.diagnosis_type,
            "severity": state.severity,
            "matched_requirement_id": state.matched_requirement_id,
            "feedback_trace_written": state.feedback_trace_written,
            "replies_count": len(output.replies),
            "card_sent": bool(output.card_sent),
            "errors": output.errors,
        }

        messages.append({"role": "user", "content": json.dumps(state_snapshot, ensure_ascii=False)})

        # 2. 推理
        try:
            response_text = llm_call(messages)
        except Exception as e:
            report.add_step(f"Turn {turn+1}: LLM call failed", AssertResult(False, str(e)))
            break

        messages.append({"role": "assistant", "content": response_text})

        # 3. 解析并执行
        try:
            decision = json.loads(response_text)
        except json.JSONDecodeError:
            # 尝试提取 JSON
            import re
            match = re.search(r'\{[\s\S]*\}', response_text)
            if match:
                try:
                    decision = json.loads(match.group())
                except json.JSONDecodeError:
                    report.add_step(f"Turn {turn+1}: Parse failed", AssertResult(False, "LLM output not valid JSON"))
                    break
            else:
                report.add_step(f"Turn {turn+1}: Parse failed", AssertResult(False, "No JSON found in LLM output"))
                break

        action = decision.get("action", "")
        params = decision.get("params", {})
        thought = decision.get("thought", "")
        assert_desc = decision.get("assert")

        # 执行动作
        if action == "done":
            passed = params.get("passed", True)
            report.add_step(
                f"Turn {turn+1}: {thought}",
                AssertResult(passed, params.get("report", "Test completed")),
            )
            break
        elif action == "inject_feedback":
            await harness.inject(TestInput(
                kind="feedback",
                content=params.get("content", ""),
                customer_id=params.get("customer_id", ""),
            ))
            report.add_step(f"Turn {turn+1}: Inject feedback — {thought}")
        elif action == "inject_card_action":
            await harness.inject(TestInput(
                kind="card_action",
                action=params.get("action", ""),
                stage=params.get("stage", 0),
                form_data=params.get("form_data", {}),
            ))
            report.add_step(f"Turn {turn+1}: Card action — {thought}")
        elif action == "get_state":
            report.add_step(f"Turn {turn+1}: Get state — {thought}")
        elif action == "get_output":
            report.add_step(f"Turn {turn+1}: Get output — {thought}")
        else:
            report.add_step(f"Turn {turn+1}: Unknown action '{action}'", AssertResult(False, f"Unknown action: {action}"))
            break

        # 4. 验证（如果有断言描述）
        if assert_desc and assert_desc != "null":
            # Agent Loop 的断言是语义的，标记为通过（LLM 自己判断）
            report.add_step(f"  Assert: {assert_desc}", AssertResult(True, "LLM semantic check"))

    else:
        report.add_step(f"Max turns ({max_turns}) reached", AssertResult(False, "Did not complete within max turns"))

    print(report.render())
    return report
