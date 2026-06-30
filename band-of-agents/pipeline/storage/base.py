"""
StorageBackend —流水线存储层抽象协议。

流水线引擎只依赖这个接口，不知道底层是 Bitable、Wiki还是双层组合。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# -- 数据结构 ------------------------------------------------------------------

@dataclass
class StageResult:
    """单阶段输出，从流水线引擎传入存储层。"""
    stage_num: int           # 1-6
    stage_label: str          # "守门录入" / "产品审批" / ...
    verdict: str               # "approved" | "rejected" | "recalled" | "deferred"
    fields: dict[str, Any] = field(default_factory=dict)
    assignee_name: str = ""
    assignee_open_id: str = ""
    duration_seconds: float = 0.0
    note: str = ""


@dataclass
class RecordMeta:
    """需求记录元信息（S1前创建）。"""
    req_id: str
    original_text: str
    submitter_name: str
    submitter_open_id: str
    source_type: str = ""  # wecom / feishu / api / demo


# -- 协议 ----------------------------------------------------------------------

@runtime_checkable
class StorageBackend(Protocol):
    """存储后端协议。所有具体实现必须满足此接口。"""

    def create_record(self, meta: RecordMeta) -> str:
        """创建需求记录，返回 record_id。S1守门开始前调用。"""
        ...

    def save_stage_result(self, record_id: str, result: StageResult) -> None:
        """保存一个阶段的审批结果。自动触发旁路动作（Wiki渲染等）。"""
        ...

    def update_stage_status(
        self, record_id: str, stage_num: int,
        status: str, extra: dict[str, Any] | None = None,
    ) -> None:
        """更新阶段状态（不追加stage_history）。回退/挂起/转交用。"""
        ...

    def terminate_record(self, record_id: str, reason: str) -> None:
        """标记需求终止（守门拒绝/顶层放弃）。"""
        ...

    def get_stage_history(self, record_id: str) -> list[dict[str, Any]]:
        """读取完整阶段历史。回退链、Wiki渲染用。"""
        ...

    def get_record_meta(self, record_id: str) -> RecordMeta | None:
        """读取需求元信息。"""
        ...
