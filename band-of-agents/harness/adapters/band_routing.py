"""
band_routing.py — Band 路由层测试适配器

实现 HarnessProtocol 的 4 个接口，用 Mock 替代真实 Band Room 和飞书 API。
routing-agent 代码不需要知道自己在被测试——适配器拦截所有 IO。

设计要点：
- MockBandRoom：模拟 Band Room 消息收发，捕获 @mention
- MockLarkCard：模拟飞书卡片发送，捕获卡片 JSON
- MockBitableReader：模拟 Bitable 历史查询，返回预置数据
- 调用真实的 routing_agent.process_feedback() 函数（测真实逻辑）
"""
from __future__ import annotations

import json
import sys
import os
from typing import Any

# 确保能 import band-routing 模块
_HACKATHON_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _HACKATHON_ROOT not in sys.path:
    sys.path.insert(0, _HACKATHON_ROOT)

from harness.core.protocol import HarnessProtocol, TestInput, TestOutput, SystemState


class MockBandRoom:
    """模拟 Band Room 消息收发。"""

    def __init__(self):
        self.messages: list[dict[str, Any]] = []  # 所有消息历史
        self.mentions: list[dict[str, Any]] = []  # @mention 记录

    def send_message(self, content: str, mentions: list[str] | None = None) -> dict[str, Any]:
        """模拟 Band Room 发消息。"""
        msg = {
            "content": content,
            "mentions": mentions or [],
            "sender": "@routing-agent",
            "timestamp": len(self.messages),
        }
        self.messages.append(msg)
        if mentions:
            for m in mentions:
                self.mentions.append({
                    "target": m,
                    "content": content,
                    "message_idx": len(self.messages) - 1,
                })
        return msg

    def get_last_mention(self) -> dict[str, Any] | None:
        """获取最后一次 @mention。"""
        return self.mentions[-1] if self.mentions else None

    def clear(self):
        self.messages.clear()
        self.mentions.clear()


class MockLarkCard:
    """模拟飞书卡片发送。"""

    def __init__(self):
        self.cards_sent: list[dict[str, Any]] = []

    def send_card(self, open_id: str, card_json: dict[str, Any]) -> dict[str, Any]:
        """模拟飞书发卡片。"""
        record = {
            "open_id": open_id,
            "card": card_json,
            "timestamp": len(self.cards_sent),
        }
        self.cards_sent.append(record)
        return record

    @property
    def last_card(self) -> dict[str, Any] | None:
        return self.cards_sent[-1] if self.cards_sent else None

    def clear(self):
        self.cards_sent.clear()


class MockBitableReader:
    """模拟 Bitable 历史查询，返回预置数据。"""

    def __init__(self, history_data: list[dict[str, Any]] | None = None):
        # history_data: [{"requirement_id": "REQ-001", "title": "...", "stage_data": {...}, "searchable_text": "..."}]
        self.history = history_data or []

    def search(self, keyword: str, top_k: int = 5, product_model: str = "") -> list[dict[str, Any]]:
        """模拟语义搜索：中文 2-4 字滑动窗口匹配，支持产品型号筛选。"""
        import re
        results = []

        records = self.history
        # 如果有产品型号，先筛选
        if product_model:
            records = [r for r in records if r.get("product_model", "") == product_model]

        # 提取关键词：中文取 2~4 字滑窗，英文取 3+ 字母词
        cn_chars = re.findall(r'[\u4e00-\u9fa5]+', keyword)
        keywords = set()
        for seg in cn_chars:
            for length in (2, 3, 4):
                for i in range(len(seg) - length + 1):
                    keywords.add(seg[i:i+length])
        en_words = re.findall(r'[a-zA-Z]{3,}', keyword.lower())
        keywords.update(en_words)

        if not keywords:
            keywords = {keyword.lower()}

        for record in records:
            text = (record.get("searchable_text", "") + " " + record.get("title", "")).lower()
            hit_count = sum(1 for kw in keywords if kw.lower() in text)
            if hit_count > 0:
                record_copy = dict(record)
                record_copy["similarity"] = hit_count / len(keywords)
                results.append(record_copy)

        results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        return results[:top_k]

    def get_chain(self, requirement_id: str) -> dict[str, Any] | None:
        """模拟按 ID 拉取完整链路。"""
        for record in self.history:
            if record.get("requirement_id") == requirement_id:
                return record
        return None


class MockFeedbackTraceWriter:
    """模拟 feedback_trace 知识库写入。"""

    def __init__(self):
        self.traces: list[dict[str, Any]] = []

    def write(self, trace: dict[str, Any]) -> None:
        self.traces.append(trace)

    @property
    def last_trace(self) -> dict[str, Any] | None:
        return self.traces[-1] if self.traces else None

    def clear(self):
        self.traces.clear()


class BandRoutingHarness(HarnessProtocol):
    """
    Band 路由层测试适配器。

    inject feedback → 调用真实 routing_agent.process_feedback()
    → 捕获 routing-agent 的路由决策、@mention、飞书卡片、Bitable 写入
    """

    def __init__(
        self,
        bitable_history: list[dict[str, Any]] | None = None,
        routing_agent=None,
    ):
        self.mock_band = MockBandRoom()
        self.mock_lark = MockLarkCard()
        self.mock_bitable = MockBitableReader(bitable_history)
        self.mock_trace = MockFeedbackTraceWriter()

        # 延迟导入 routing_agent，避免循环依赖
        self._routing_agent_cls = routing_agent
        self._routing_agent = None
        self._last_output: TestOutput = TestOutput()
        self._state: SystemState = SystemState()

    def _ensure_agent(self):
        """懒初始化 routing-agent，注入所有 mock。"""
        if self._routing_agent is None:
            # 确保 band-routing 目录在 path 中（用连字符不能直接 import）
            _band_routing_dir = os.path.join(_HACKATHON_ROOT, "band-routing")
            if _band_routing_dir not in sys.path:
                sys.path.insert(0, _band_routing_dir)

            if self._routing_agent_cls is None:
                # band-routing 目录用连字符，不能直接 import，用 importlib
                import importlib.util
                _module_path = os.path.join(_band_routing_dir, "routing_agent.py")
                _spec = importlib.util.spec_from_file_location("routing_agent", _module_path)
                _module = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_module)
                self._routing_agent_cls = _module.RoutingAgent

            self._routing_agent = self._routing_agent_cls(
                band_room=self.mock_band,
                lark_card=self.mock_lark,
                bitable_reader=self.mock_bitable,
                trace_writer=self.mock_trace,
            )

    async def inject(self, input: TestInput) -> None:
        """注入客户反馈或卡片审批操作。"""
        self._ensure_agent()
        self._last_output = TestOutput()

        if input.kind == "feedback":
            # 调用真实 routing-agent 处理反馈
            try:
                decision = self._routing_agent.process_feedback(
                    feedback_text=input.content,
                    customer_id=input.customer_id,
                )
                self._last_output.routing_decision = decision

                # 从决策更新状态
                if decision:
                    self._state.status = "routed"
                    self._state.diagnosis_type = decision.get("diagnosis_type", "")
                    self._state.entry_stage = decision.get("entry_stage", 0)
                    self._state.routing_target = decision.get("target_agent", "")
                    self._state.severity = decision.get("severity", "")
                    self._state.matched_requirement_id = decision.get("matched_requirement_id", "")
                else:
                    self._state.status = "error"
                    self._last_output.errors.append("routing_agent returned None")
            except Exception as e:
                self._state.status = "error"
                self._last_output.errors.append(str(e))

            # 捕获 Band Room 消息
            for msg in self.mock_band.messages:
                self._last_output.replies.append({
                    "type": "routing",
                    "content": msg["content"],
                    "mentions": msg["mentions"],
                })

            # 捕获飞书卡片
            if self.mock_lark.last_card:
                self._last_output.card_sent = self.mock_lark.last_card["card"]

            # 捕获 feedback_trace
            self._state.feedback_trace_written = len(self.mock_trace.traces) > 0

        elif input.kind == "card_action":
            # 模拟人在飞书卡片上的操作
            self._state.status = "card_action_processed"
            self._state.stage = input.stage

    async def capture(self) -> TestOutput:
        return self._last_output

    async def inspect_state(self) -> SystemState:
        return self._state

    async def reset(self) -> None:
        self.mock_band.clear()
        self.mock_lark.clear()
        self.mock_trace.clear()
        self._last_output = TestOutput()
        self._state = SystemState()
        self._routing_agent = None  # 重置 agent
