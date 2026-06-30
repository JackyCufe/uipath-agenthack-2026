"""
protocol.py — 通用测试接口定义

harness 的通用引擎层只依赖这些抽象接口，不依赖任何项目特定代码。
新项目只需实现 HarnessProtocol，即可复用全部引擎和场景。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestInput:
    """注入到被测系统的输入。"""
    kind: str  # "text" | "card_action" | "feedback"
    content: str = ""
    action: str = ""
    stage: int = 0
    form_data: dict[str, Any] = field(default_factory=dict)
    customer_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestOutput:
    """从被测系统捕获的输出。"""
    replies: list[dict[str, Any]] = field(default_factory=list)  # [{"type": "text"|"card"|"routing", "content": ...}]
    routing_decision: dict[str, Any] | None = None  # routing-agent 的路由决策 JSON
    card_sent: dict[str, Any] | None = None  # 发出的飞书卡片 JSON
    bitable_writes: list[dict[str, Any]] = field(default_factory=list)  # 写入 Bitable 的记录
    errors: list[str] = field(default_factory=list)


@dataclass
class SystemState:
    """被测系统的内部状态快照。"""
    stage: int = 0
    status: str = ""  # active | info_needed | rejected | completed | routed
    rework_count: int = 0
    phase: str = ""
    routing_target: str = ""  # @s1-agent etc
    entry_stage: int = 0  # 路由切入阶段
    diagnosis_type: str = ""  # tech_bug | service_issue | new_requirement | complaint
    severity: str = ""  # urgent | normal | low
    matched_requirement_id: str = ""
    feedback_trace_written: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


class HarnessProtocol(ABC):
    """
    项目适配层必须实现的 4 个接口。

    引擎层通过这 4 个接口与被测系统交互，不知道项目细节。
    """

    @abstractmethod
    async def inject(self, input: TestInput) -> None:
        """注入：发文本 / 提交卡片action / 触发事件。"""
        ...

    @abstractmethod
    async def capture(self) -> TestOutput:
        """捕获：文本回复 / 卡片JSON / 路由决策 / 错误消息。"""
        ...

    @abstractmethod
    async def inspect_state(self) -> SystemState:
        """读状态：当前阶段 / session状态 / 路由目标 / 计数器。"""
        ...

    @abstractmethod
    async def reset(self) -> None:
        """重置：清session，回到初始状态。"""
        ...
