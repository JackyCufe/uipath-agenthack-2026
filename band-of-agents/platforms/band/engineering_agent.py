"""
engineering_agent.py — Engineering Agent

监听Band Room @mention，收到路由决策后：
1. 发飞书通知卡片给工程师
2. 工程师点按钮后处理回调（resolved/escalate/transfer）
3. 写feedback_trace到Bitable
"""
from __future__ import annotations

import os
import sys
import json
from typing import Any

_routing_dir = os.path.dirname(os.path.abspath(__file__))
if _routing_dir not in sys.path:
    sys.path.insert(0, _routing_dir)
_tools_dir = os.path.join(_routing_dir, "tools")
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from i18n import t, get_lang
from lark_notifier import notify_via_lark, send_card_to_open_id


async def handle_message(content: str, sender: str, tools, room_id: str) -> str | None:
    """
    收到routing-agent的路由消息，发飞书卡片给工程师。

    消息格式：
    [ROUTING] {"diagnosis_type":"tech_bug","matched_requirement_id":"DEMO-001",...}
    路由决策说明...
    """
    print(f"\n[Engineering Agent] Received message from {sender}")

    # 解析路由决策
    decision = _parse_routing_message(content)
    if not decision:
        print(f"  ⚠️ Cannot parse routing decision from message")
        return None

    diag_type = decision.get("diagnosis_type", "unknown")
    matched_req = decision.get("matched_requirement_id", "")
    entry_stage = decision.get("entry_stage", 3)
    severity = decision.get("severity", "normal")
    feedback_text = decision.get("feedback_text", "")
    customer_id = decision.get("customer_id", "")
    context_summary = decision.get("context_summary", "")

    print(f"  → Diagnosis: {diag_type}")
    print(f"  → Matched: {matched_req}")
    print(f"  → Entry Stage: S{entry_stage}")

    # 从Bitable历史记录提取负责人open_id
    owner_open_id, owner_name = _get_owner(entry_stage, matched_req)
    print(f"  → Owner: {owner_name}")

    # 发飞书通知卡片
    result = notify_via_lark(
        decision,
        feedback_text=feedback_text,
        customer_id=customer_id,
        owner_open_id=owner_open_id,
        owner_name=owner_name,
    )

    if result.get("ok"):
        print(f"  ✅ Feishu card sent to {owner_name}")
        return f"Engineering agent: card sent to {owner_name}. Waiting for engineer to resolve."
    else:
        print(f"  ❌ Card send failed: {result.get('error')}")
        return f"Engineering agent: card send failed - {result.get('error')}"


def _parse_routing_message(content: str) -> dict[str, Any] | None:
    """从routing-agent的消息中解析路由决策JSON。"""
    # 找 [ROUTING] 标记
    if "[ROUTING]" not in content:
        # 尝试直接解析JSON
        import re
        matches = re.findall(r'\{[\s\S]*\}', content)
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                pass
        return None

    # 提取JSON部分
    json_start = content.find("{")
    json_end = content.rfind("}") + 1
    if json_start < 0 or json_end <= 0:
        return None

    json_str = content[json_start:json_end]
    try:
        decision = json.loads(json_str)
        # 提取feedback_text（在JSON外面的文本部分）
        after_json = content[json_end:].strip()
        if after_json:
            # 尝试从routing消息中提取feedback
            lines = after_json.split("\n")
            for line in lines:
                if "feedback" in line.lower() or "反馈" in line:
                    decision["feedback_text"] = line.split(":", 1)[-1].strip()
                    break
        return decision
    except json.JSONDecodeError:
        return None


def _get_owner(entry_stage: int, matched_req_id: str) -> tuple[str, str]:
    """获取阶段负责人。"""
    from bitable_reader import get_requirement_chain

    if matched_req_id:
        chain = get_requirement_chain(matched_req_id)
        if chain:
            stage_data = chain.get("stage_data", {})
            stage_key = f"S{entry_stage}"
            stage_fields = stage_data.get(stage_key, {})
            # 找负责人字段
            for k, v in stage_fields.items():
                if "owner" in k.lower() or "负责人" in k:
                    if isinstance(v, list) and v:
                        person = v[0]
                        open_id = person.get("id", "")
                        name = person.get("en_name", person.get("name", ""))
                        if open_id:
                            return open_id, name

    # 降级
    role_names = {
        1: t("role.presales"), 2: t("role.pm"), 3: t("role.rd"),
        4: t("role.product_owner"), 5: t("role.after_sales"), 6: t("role.all"),
    }
    role = role_names.get(entry_stage, t("role.default"))
    open_id = os.environ.get("JACKY_OPEN_ID", "")
    return open_id, role


def handle_message_sync(content: str, sender: str = "") -> str:
    """同步版本：routing-agent本地调用，发飞书卡片给工程师。"""
    print(f"\n[Engineering Agent] Processing routing message (sync)")

    decision = _parse_routing_message(content)
    if not decision:
        print(f"  ⚠️ Cannot parse routing decision")
        return "Failed to parse"

    entry_stage = decision.get("entry_stage", 3)
    matched_req = decision.get("matched_requirement_id", "")
    feedback_text = decision.get("feedback_text", content)

    # 提取feedback_text从消息尾部
    if "feedback_text:" in content:
        idx = content.index("feedback_text:")
        feedback_text = content[idx + len("feedback_text:"):].strip().split("\n")[0]

    customer_id = ""
    if "customer_id:" in content:
        idx = content.index("customer_id:")
        customer_id = content[idx + len("customer_id:"):].strip().split("\n")[0]

    decision["feedback_text"] = feedback_text
    decision["customer_id"] = customer_id

    # 获取负责人
    owner_open_id, owner_name = _get_owner(entry_stage, matched_req)
    print(f"  → Owner: {owner_name}")

    # 发飞书卡片
    result = notify_via_lark(
        decision,
        feedback_text=feedback_text,
        customer_id=customer_id,
        owner_open_id=owner_open_id,
        owner_name=owner_name,
    )

    if result.get("ok"):
        print(f"  ✅ Feishu card sent to {owner_name}")
        return f"Card sent to {owner_name}"
    else:
        print(f"  ❌ Card send failed: {result.get('error')}")
        return f"Failed: {result.get('error')}"


def main():
    """启动Engineering Agent。"""
    from band_connection import create_band_agent, start_agent_blocking

    agent_id = os.environ.get("BAND_ENGINEERING_AGENT_ID", "")
    api_key = os.environ.get("BAND_ENGINEERING_API_KEY", "")

    if not agent_id or not api_key:
        print("⚠️ BAND_ENGINEERING_AGENT_ID / BAND_ENGINEERING_API_KEY not configured")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Engineering Agent — Starting")
    print(f"  Agent ID: {agent_id}")
    print(f"  Lang: {get_lang()}")
    print(f"{'='*60}")

    agent = create_band_agent(agent_id, api_key, handle_message)
    start_agent_blocking(agent)


if __name__ == "__main__":
    main()
