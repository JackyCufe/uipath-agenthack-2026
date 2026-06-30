"""
reporter.py — 测试报告生成

收集测试步骤、断言结果，生成最终 PASS/FAIL 报告。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .asserts import AssertResult


class TestReport:
    def __init__(self, scenario_name: str):
        self.scenario_name = scenario_name
        self.steps: list[dict[str, Any]] = []
        self.start_time = datetime.now()
        self.end_time: datetime | None = None

    def add_step(self, description: str, result: AssertResult | None = None, detail: str = ""):
        if result is not None:
            passed = result.passed
            message = result.message
        else:
            passed = None
            message = detail
        self.steps.append({
            "description": description,
            "passed": passed,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        })

    def finish(self):
        self.end_time = datetime.now()

    @property
    def passed(self) -> bool:
        """全部断言通过 = PASS。"""
        for step in self.steps:
            if step["passed"] is False:
                return False
        # 至少有一个断言
        return any(step["passed"] is True for step in self.steps)

    def render(self) -> str:
        self.finish()
        duration = (self.end_time - self.start_time).total_seconds()
        status = "✅ PASS" if self.passed else "❌ FAIL"

        lines = [
            f"\n{'='*60}",
            f"  {status} — {self.scenario_name}",
            f"  Duration: {duration:.1f}s | Steps: {len(self.steps)}",
            f"{'='*60}",
        ]

        for i, step in enumerate(self.steps, 1):
            if step["passed"] is True:
                icon = "  ✅"
            elif step["passed"] is False:
                icon = "  ❌"
            else:
                icon = "  ⏭️"
            lines.append(f"{icon} Step {i}: {step['description']}")
            if step["message"]:
                lines.append(f"       {step['message']}")

        lines.append(f"{'='*60}\n")
        return "\n".join(lines)
