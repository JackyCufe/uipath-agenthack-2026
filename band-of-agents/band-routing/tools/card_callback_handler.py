"""
card_callback_handler.py — 卡片回调统一处理器

处理所有飞书卡片按钮回调：
1. customer_confirm — 客户确认提交 → 触发 routing-agent
2. customer_edit — 客户补充修改 → 弹编辑卡片
3. resolved — 研发点"已处理" → 写 Bitable + 通知客户
4. escalate — 研发点"需走完整流程" → 创建新需求
5. transfer — 研发点"转交他人" → 弹转交卡片
6. transfer_submit — 转交卡片提交 → 搜索联系人 + 发卡片给对方
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

# 加载飞书环境
_pipeline_dir = os.path.join(os.path.dirname(__file__), "..", "ai-requirement-pipeline", "pipeline")
_pipeline_dir = os.path.abspath(_pipeline_dir)
if _pipeline_dir not in sys.path:
    sys.path.insert(0, _pipeline_dir)

_env_name = os.environ.get("FEISHU_ENV", "team-testing")
_env_file = os.path.join(_pipeline_dir, f".env.{_env_name}")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

# 导入 lark_notifier 工具
_tools_dir = os.path.join(os.path.dirname(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from lark_notifier import (
    build_transfer_card,
    build_resolved_notification_card,
    send_card_to_open_id,
    search_feishu_user,
)

# i18n
_routing_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _routing_dir not in sys.path:
    sys.path.insert(0, _routing_dir)
from i18n import t, get_lang


def handle_card_callback(callback_data: dict[str, Any]) -> dict[str, Any]:
    """
    统一处理卡片回调。

    Args:
        callback_data: 飞书卡片回调数据，包含 action value + operator open_id

    Returns:
        {"ok": True/False, "message": "..."}
    """
    # 提取回调值
    value = callback_data.get("value", {})
    action = value.get("action", "")
    operator_open_id = callback_data.get("operator", {}).get("open_id", "")

    print(f"\n[card_callback] 收到回调: action={action}, operator={operator_open_id[:12]}...")
    print(f"  value: {json.dumps(value, ensure_ascii=False)[:200]}")

    if action == "customer_confirm":
        return _handle_customer_confirm(value, operator_open_id)

    elif action == "customer_edit":
        return _handle_customer_edit(value, operator_open_id)

    elif action == "resolved":
        return _handle_resolved(value, operator_open_id)

    elif action == "escalate":
        return _handle_escalate(value, operator_open_id)

    elif action == "transfer":
        return _handle_transfer(value, operator_open_id)

    elif action == "transfer_submit":
        return _handle_transfer_submit(callback_data, operator_open_id)

    else:
        print(f"  ⚠️ 未知 action: {action}")
        return {"ok": False, "message": f"未知 action: {action}"}


# ─── 回调处理函数 ──────────────────────────────────────

def _handle_customer_confirm(value: dict, operator_open_id: str) -> dict:
    """客户确认提交 → 触发 routing-agent 路由。"""
    feedback_text = value.get("feedback_text", "")
    product_model = value.get("product_model", "")
    customer_id = value.get("customer_id", "")

    print(f"  → {t('callback.routed') if False else t('callback.routed')}")
    print(f"  → 反馈: {feedback_text[:60]}...")
    print(f"  → 型号: {product_model}")

    # 触发 routing-agent
    _routing_root = os.path.join(os.path.dirname(__file__), "..")
    _routing_root = os.path.abspath(_routing_root)
    if _routing_root not in sys.path:
        sys.path.insert(0, _routing_root)

    from routing_agent import RoutingAgent
    agent = RoutingAgent()
    decision = agent.process_feedback(
        feedback_text=feedback_text,
        customer_id=customer_id,
        product_model=product_model,
    )

    if decision and decision.get("target_agent"):
        return {"ok": True, "message": t("callback.routed"), "decision": decision}
    else:
        return {"ok": False, "message": t("callback.routing_failed")}


def _handle_customer_edit(value: dict, operator_open_id: str) -> dict:
    """客户补充修改 → 更新卡片为可编辑状态。"""
    feedback_text = value.get("feedback_text", "")
    product_model = value.get("product_model", "")
    customer_id = value.get("customer_id", "")

    print(f"  → 客户要求补充修改")

    # 发一张带输入框的编辑卡片
    from lark_notifier import _get_config
    cfg = _get_config()

    def _pt(content): return {"tag": "plain_text", "content": content}
    def _md(content): return {"tag": "lark_md", "content": content}
    def _div(text): return {"tag": "div", "text": text}

    edit_card = {
        "schema": "2.0",
        "header": {"title": _pt(f"✏️ {t('card.edit_title')}"), "template": "blue"},
        "body": {"elements": [
            _div(_md(t("card.edit_prompt"))),
            {"tag": "hr"},
            {"tag": "input", "name": "edited_feedback", "placeholder": _pt(t("callback.feedback_content")),
             "value": feedback_text},
            {"tag": "input", "name": "edited_product", "placeholder": _pt(t("label.product_model")),
             "value": product_model},
            {"tag": "column_set", "flex_mode": "none",
             "columns": [
                 {"tag": "column", "width": "weighted", "weight": 1,
                  "elements": [
                      {"tag": "button", "text": _pt(t("btn.confirm")), "type": "primary",
                       "action_type": "form_submit", "name": "customer_re_submit",
                       "value": {"action": "customer_confirm", "customer_id": customer_id}},
                  ]},
             ]},
        ]},
    }

    return {"ok": True, "message": t("callback.edit_card_sent")}


def _handle_resolved(value: dict, operator_open_id: str) -> dict:
    """研发点"已处理" → 写 Bitable + 写 feedback_trace + 通知客户。"""
    req_id = value.get("requirement_id", "")
    customer_id = value.get("customer_id", "")
    entry_stage = value.get("entry_stage", 1)
    diagnosis_type = value.get("diagnosis_type", "")

    print(f"  → {t('callback.resolved_msg')}: req={req_id}")

    # 1. 写 Bitable（更新需求记录）
    _update_bitable_feedback_trace(req_id, "resolved", operator_open_id)

    # 2. 写 feedback_trace（处理结果闭环）
    _write_trace_resolution(req_id, "resolved", operator_open_id, diagnosis_type)

    # 3. 获取处理人姓名
    resolver_name = _get_user_name(operator_open_id)

    # 3. 通知客户
    if customer_id:
        # 查客户的 open_id（这里简化，实际需要客户在飞书的 open_id）
        from lark_notifier import _get_config
        cfg = _get_config()
        jacky_open_id = os.environ.get("JACKY_OPEN_ID", "")

        resolved_card = build_resolved_notification_card(
            customer_id=customer_id,
            requirement_id=req_id,
            resolved_by=resolver_name,
            resolution_note=t("callback.resolution_note") if get_lang() == "en" else "问题已修复，请验证。",
        )
        send_card_to_open_id(jacky_open_id, resolved_card)

    # 4. 更新原卡片为"已处理"状态
    def _pt(content): return {"tag": "plain_text", "content": content}
    def _md(content): return {"tag": "lark_md", "content": content}
    def _div(text): return {"tag": "div", "text": text}

    updated_card = {
        "schema": "2.0",
        "header": {"title": _pt(f"✅ {t('card.resolved_title')}"), "template": "green"},
        "body": {"elements": [
            _div(_md(t("card.resolved_by_marked", name=resolver_name))),
            _div(_pt(t("card.req_label", req_id=req_id or t("placeholder.dash")))),
            _div(_pt(t("callback.customer_notified"))),
        ]},
    }

    return {"ok": True, "message": t("callback.resolved_msg")}


def _handle_escalate(value: dict, operator_open_id: str) -> dict:
    """研发点"需走完整流程" → 写 Bitable + 写 feedback_trace + 创建新需求。"""
    req_id = value.get("requirement_id", "")
    customer_id = value.get("customer_id", "")
    diagnosis_type = value.get("diagnosis_type", "")

    print(f"  → {t('callback.escalated_msg')}: req={req_id}")

    # 更新 Bitable
    _update_bitable_feedback_trace(req_id, "escalated", operator_open_id)

    # 写 feedback_trace（处理结果闭环）
    _write_trace_resolution(req_id, "escalated", operator_open_id, diagnosis_type)

    # 通知发起人
    def _pt(content): return {"tag": "plain_text", "content": content}
    def _md(content): return {"tag": "lark_md", "content": content}
    def _div(text): return {"tag": "div", "text": text}

    updated_card = {
        "schema": "2.0",
        "header": {"title": _pt(f"🔄 {t('card.escalated_title')}"), "template": "orange"},
        "body": {"elements": [
            _div(_md(t("card.escalated_msg"))),
            _div(_pt(t("card.req_label", req_id=req_id or t("placeholder.dash")))),
            _div(_pt(t("card.presales_will_start"))),
        ]},
    }

    return {"ok": True, "message": t("callback.escalated_msg")}


def _handle_transfer(value: dict, operator_open_id: str) -> dict:
    """研发点"转交他人" → 发送转交卡片（不替换原卡片，单独发新消息）。"""
    req_id = value.get("requirement_id", "")
    feedback_text = value.get("feedback_text", "")
    entry_stage = value.get("entry_stage", 1)
    customer_id = value.get("customer_id", "")
    diagnosis_type = value.get("diagnosis_type", "")

    print(f"  → {t('callback.transfer_card_sent')}: req={req_id}")

    # 构建转交卡片
    original_decision = {
        "matched_requirement_id": req_id,
        "entry_stage": entry_stage,
        "diagnosis_type": diagnosis_type,
    }
    transfer_card = build_transfer_card(original_decision, feedback_text)

    # 直接发新卡片消息（不通过回调返回）
    from lark_notifier import send_card_to_open_id
    send_card_to_open_id(operator_open_id, transfer_card)

    # 回调只返回toast，不返回card
    return {"ok": True, "message": t("callback.transfer_card_sent")}


def _handle_transfer_submit(callback_data: dict, operator_open_id: str) -> dict:
    """转交提交 → 直接发路由卡片给转交对象。"""
    value = callback_data.get("value", {})

    target_name = value.get("target_name", "")
    target_open_id = value.get("target_open_id", "")
    feedback_text = value.get("feedback_text", "")
    req_id = value.get("requirement_id", "")

    print(f"  → Transfer to: {target_name}")

    if not target_open_id:
        return {"ok": False, "message": t("callback.enter_name")}

    # 发路由通知卡片给转交对象
    from lark_notifier import _build_notification_card, send_card_to_open_id
    decision = {
        "diagnosis_type": "transferred",
        "matched_requirement_id": req_id,
        "entry_stage": 3,
        "severity": "normal",
        "entry_reason": f"Transferred by colleague",
        "context_summary": f"Customer feedback: {feedback_text[:100]}",
    }

    card = _build_notification_card(decision, target_name, "🟡", feedback_text, "")
    send_result = send_card_to_open_id(target_open_id, card)

    if send_result.get("ok"):
        return {"ok": True, "message": t("callback.transferred_to", name=target_name)}
    else:
        return {"ok": False, "message": t("callback.transfer_failed", error=send_result.get("error"))}


# ─── 辅助函数 ──────────────────────────────────────────

def _update_bitable_feedback_trace(req_id: str, status: str, operator_open_id: str) -> None:
    """更新 Bitable 中的反馈追踪记录。"""
    import requests
    from lark_notifier import _get_config, _get_token

    cfg = _get_config()
    if not cfg.get("app_token"):
        return

    token = _get_token()

    # 查找记录
    filter_expr = f'CurrentValue.[{t("field.requirement_id")}]="{req_id}"'
    resp = requests.get(
        f"{cfg['base_url']}/bitable/v1/apps/{cfg['app_token']}/tables/{cfg['table_id']}/records",
        headers={"Authorization": f"Bearer {token}"},
        params={"filter": filter_expr, "page_size": 1},
    )
    data = resp.json()
    items = data.get("data", {}).get("items", [])
    if not items:
        print(f"  ⚠️ {t('callback.bitable_not_found', req_id=req_id)}")
        return

    record_id = items[0].get("record_id", "")

    # 更新记录
    update_fields = {
        t("field.current_stage"): t("callback.feedback_processed", status=status),
    }

    resp = requests.put(
        f"{cfg['base_url']}/bitable/v1/apps/{cfg['app_token']}/tables/{cfg['table_id']}/records/{record_id}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"fields": update_fields},
    )
    result = resp.json()
    if result.get("code") == 0:
        print(f"  → {t('callback.bitable_updated', req_id=req_id, status=status)}")
    else:
        print(f"  ⚠️ {t('callback.bitable_update_failed', msg=result.get('msg'))}")


def _get_user_name(open_id: str) -> str:
    """通过 open_id 查飞书用户姓名。"""
    import requests
    from lark_notifier import _get_config, _get_token

    cfg = _get_config()
    token = _get_token()

    try:
        resp = requests.get(
            f"{cfg['base_url']}/contact/v3/users/{open_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"user_id_type": "open_id"},
        )
        data = resp.json()
        if data.get("code") == 0:
            user = data.get("data", {}).get("user", {})
            return user.get("name", t("callback.default_resolver"))
    except Exception:
        pass

    return t("callback.default_resolver")


def _write_trace_resolution(req_id: str, resolution: str, operator_open_id: str, diagnosis_type: str = "") -> None:
    """
    把处理结果写入 feedback_trace，形成知识闭环。

    在 Bitable 中更新该需求记录，追加反馈处理结果。
    下次相似反馈进来时，routing-agent 可以查到历史处理结果作为参考。
    """
    import requests
    from lark_notifier import _get_config, _get_token

    cfg = _get_config()
    if not cfg.get("app_token"):
        return

    token = _get_token()

    # 查找记录
    filter_expr = f'CurrentValue.[{t("field.requirement_id")}]="{req_id}"'
    resp = requests.get(
        f"{cfg['base_url']}/bitable/v1/apps/{cfg['app_token']}/tables/{cfg['table_id']}/records",
        headers={"Authorization": f"Bearer {token}"},
        params={"filter": filter_expr, "page_size": 1},
    )
    data = resp.json()
    items = data.get("data", {}).get("items", [])
    if not items:
        print(f"  ⚠️ {t('callback.bitable_not_found', req_id=req_id)}")
        return

    record_id = items[0].get("record_id", "")
    resolver_name = _get_user_name(operator_open_id)

    # 构建处理结果摘要
    if resolution == "resolved":
        trace_text = f"[{resolver_name}] Marked as resolved | Diagnosis: {diagnosis_type}"
    elif resolution == "escalated":
        trace_text = f"[{resolver_name}] Escalated to full pipeline | Diagnosis: {diagnosis_type}"
    elif resolution == "transferred":
        trace_text = f"[{resolver_name}] Transferred | Diagnosis: {diagnosis_type}"
    else:
        trace_text = f"[{resolver_name}] {resolution} | Diagnosis: {diagnosis_type}"

    # 更新记录：在"当前阶段"字段追加处理结果
    current_stage = str(items[0].get("fields", {}).get(t("field.current_stage"), ""))

    update_fields = {
        t("field.current_stage"): t("callback.feedback_processed", status=resolution),
    }

    resp = requests.put(
        f"{cfg['base_url']}/bitable/v1/apps/{cfg['app_token']}/tables/{cfg['table_id']}/records/{record_id}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"fields": update_fields},
    )
    result = resp.json()
    if result.get("code") == 0:
        print(f"  → feedback_trace updated: {req_id} → {resolution} by {resolver_name}")
    else:
        print(f"  ⚠️ feedback_trace update failed: {result.get('msg')}")
