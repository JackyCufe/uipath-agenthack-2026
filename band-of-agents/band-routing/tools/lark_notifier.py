"""
lark_notifier.py — 飞书卡片通知工具

routing-agent 路由决策完成后，通过这个工具发飞书卡片给对应负责人。
不 import pipeline 代码，独立调用飞书 API。
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

# i18n
import os as _os
import sys as _sys
_i18n_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
if _i18n_dir not in _sys.path:
    _sys.path.insert(0, _i18n_dir)
from i18n import t


def _get_config():
    """从环境变量读取飞书配置。"""
    app_id = os.environ.get("FEISHU_APP_ID")
    if not app_id:
        _pipeline_dir = os.path.join(os.path.dirname(__file__), "..", "..", "ai-requirement-pipeline", "pipeline")
        _pipeline_dir = os.path.abspath(_pipeline_dir)
        _env_name = os.environ.get("FEISHU_ENV", "team-testing")
        _env_file = os.path.join(_pipeline_dir, f".env.{_env_name}")
        if os.path.exists(_env_file):
            with open(_env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        os.environ.setdefault(k.strip(), v.strip())

    return {
        "app_id": os.environ.get("FEISHU_APP_ID", ""),
        "app_secret": os.environ.get("FEISHU_APP_SECRET", ""),
        "base_url": os.environ.get("FEISHU_BASE_URL", "https://open.feishu.cn/open-apis"),
    }


_token_cache = {"token": None, "expires_at": 0}


def _get_token() -> str:
    import time as _time
    now = _time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    cfg = _get_config()
    resp = requests.post(
        f"{cfg['base_url']}/auth/v3/tenant_access_token/internal",
        json={"app_id": cfg["app_id"], "app_secret": cfg["app_secret"]},
    )
    data = resp.json()
    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expires_at"] = now + data["expire"] - 60
    return _token_cache["token"]


# ── 阶段 → 负责人角色映射 ──
STAGE_ROLE_MAP = {
    1: t("role.presales"),
    2: t("role.pm"),
    3: t("role.rd"),
    4: t("role.product_owner"),
    5: t("role.after_sales"),
    6: t("role.all"),
}


# ── 阶段 → 测试负责人 open_id 映射（从环境变量读）──
def _get_stage_owner_open_id(stage: int) -> str:
    """获取阶段负责人的 open_id。优先从环境变量，否则用 Jacky 默认。"""
    env_key = f"STAGE{stage}_OWNER_OPEN_ID"
    open_id = os.environ.get(env_key, "")
    if not open_id:
        # 默认用 Jacky
        open_id = os.environ.get("JACKY_OPEN_ID", "")
    return open_id


def notify_via_lark(
    routing_decision: dict[str, Any],
    feedback_text: str = "",
    customer_id: str = "",
    owner_open_id: str = "",
    owner_name: str = "",
) -> dict[str, Any]:
    """
    根据 routing-agent 的路由决策，发飞书卡片给对应负责人。

    Args:
        routing_decision: 路由决策 JSON
        feedback_text: 客户反馈原文
        customer_id: 客户标识
        owner_open_id: 负责人 open_id（从 Bitable 历史记录提取）
        owner_name: 负责人姓名

    Returns:
        {"ok": True/False, "message_id": "...", "error": "..."}
    """
    cfg = _get_config()
    entry_stage = routing_decision.get("entry_stage", 1)

    # 优先用从 Bitable 历史记录提取的负责人
    open_id = owner_open_id or _get_stage_owner_open_id(entry_stage)
    role = owner_name or STAGE_ROLE_MAP.get(entry_stage, t("role.default"))

    if not open_id:
        print(f"[lark_notifier] {t('log.no_open_id', stage=entry_stage)}")
        return {"ok": False, "error": "no open_id for stage owner"}

    # 构建卡片内容
    severity_icon = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}.get(
        routing_decision.get("severity", "normal"), "🟡"
    )

    card_content = _build_notification_card(routing_decision, role, severity_icon, feedback_text, customer_id)

    # 发送卡片消息
    token = _get_token()
    resp = requests.post(
        f"{cfg['base_url']}/im/v1/messages",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        params={"receive_id_type": "open_id"},
        json={
            "receive_id": open_id,
            "msg_type": "interactive",
            "content": json.dumps(card_content),
        },
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[lark_notifier] ❌ 发送失败: {data.get('msg')}")
        return {"ok": False, "error": data.get("msg", "unknown")}

    message_id = data.get("data", {}).get("message_id", "")
    print(f"[lark_notifier] ✅ 卡片已发送给 {role} (open_id={open_id[:12]}...)")
    return {"ok": True, "message_id": message_id, "card": card_content}


def _build_notification_card(
    decision: dict[str, Any],
    role: str,
    severity_icon: str,
    feedback_text: str = "",
    customer_id: str = "",
) -> dict[str, Any]:
    """构建飞书交互卡片 JSON（Card 2.0 schema，和 pipeline 的 card_templates.py 一致）。"""
    diag_type = decision.get("diagnosis_type", "")
    diagnosis_label = t(f"diagnosis.{diag_type}") if diag_type and diag_type != "unknown" else t("diagnosis.unknown")
    matched_req = decision.get("matched_requirement_id") or t("placeholder.no_match")
    template = "red" if decision.get("severity") == "urgent" else "yellow"

    def _pt(content: str) -> dict:
        return {"tag": "plain_text", "content": content}

    def _md(content: str) -> dict:
        return {"tag": "lark_md", "content": content}

    def _div(text: dict) -> dict:
        return {"tag": "div", "text": text}

    def _hr() -> dict:
        return {"tag": "hr"}

    def _field_row(label: str, value: str) -> dict:
        return {
            "tag": "column_set",
            "flex_mode": "none",
            "columns": [
                {"tag": "column", "width": "weighted", "weight": 1,
                 "elements": [_div(_md(f"**{label}**"))]},
                {"tag": "column", "width": "weighted", "weight": 3,
                 "elements": [_div(_pt(str(value) if value else "—"))]},
            ],
        }

    # 构建卡片元素
    elements = []

    # 客户反馈原文（引用块）
    elements.append(_div(_md(f"📋 **{t('card.feedback_original')}**")))
    elements.append(_div(_pt(feedback_text if feedback_text else t("placeholder.empty"))))
    elements.append(_hr())

    # 路由信息（字段行）
    if customer_id:
        elements.append(_field_row(t("label.customer"), customer_id))
    elements.append(_field_row(t("label.diagnosis_type"), diagnosis_label))
    elements.append(_field_row(t("label.matched_requirement"), matched_req))
    elements.append(_field_row(t("label.entry_stage"), f"S{decision.get('entry_stage', 1)}"))
    elements.append(_field_row(t("label.severity"), decision.get("severity", "normal")))
    elements.append(_hr())

    # 路由原因
    elements.append(_div(_md(f"🔍 **{t('card.routing_reason')}**")))
    # 长文本按句号/分号拆成 bullet points
    reason_text = decision.get("entry_reason", "—")
    reason_points = [s.strip() for s in reason_text.replace("；", "。").split("。") if s.strip()]
    if len(reason_points) > 1:
        for pt in reason_points:
            elements.append(_div(_md(f"• {pt}")))
    else:
        elements.append(_div(_pt(reason_text)))
    elements.append(_hr())

    # 上下文摘要（AI 生成的自然语言，整段输出）
    elements.append(_div(_md(f"📎 **{t('card.context_summary')}**")))
    elements.append(_div(_pt(decision.get("context_summary", "—"))))
    elements.append(_hr())

    # 处理人
    elements.append(_div(_md(f"👉 **{t('prompt.handle', role=role)}**")))

    # 交互按钮（竖排，每个按钮占一整行）
    req_id = matched_req if matched_req != t("placeholder.no_match") else ""
    btn_value = {
        "requirement_id": req_id,
        "entry_stage": decision.get("entry_stage", 1),
        "diagnosis_type": diagnosis_label,
        "customer_id": customer_id,
    }
    elements.append({
        "tag": "column_set",
        "flex_mode": "none",
        "columns": [
            {"tag": "column", "width": "weighted", "weight": 1,
             "elements": [
                 {"tag": "button", "text": _pt(t("btn.resolved")), "type": "primary",
                  "behaviors": [{"type": "callback", "value": {"action": "resolved", **btn_value}}]},
                 {"tag": "button", "text": _pt(t("btn.escalate")), "type": "default",
                  "behaviors": [{"type": "callback", "value": {"action": "escalate", **btn_value}}]},
                 {"tag": "button", "text": _pt(t("btn.transfer")), "type": "default",
                  "behaviors": [{"type": "callback", "value": {"action": "transfer", **btn_value}}]},
             ]},
        ],
    })

    return {
        "schema": "2.0",
        "header": {"title": _pt(f"{severity_icon} {t('card.routing_title')}"), "template": template},
        "body": {"elements": elements},
    }


# ─── 客户确认卡片 ──────────────────────────────────────

def build_customer_confirm_card(
    feedback_text: str,
    product_model: str = "",
    customer_id: str = "",
    ai_summary: str = "",
) -> dict[str, Any]:
    """
    客户确认卡片：AI 预填反馈摘要 + 产品型号，客户确认后才触发路由。

    客户看到这张卡片后：
    - 点"确认" → 触发 routing-agent 路由
    - 点"补充信息" → 可以修改反馈内容
    """
    def _pt(content: str) -> dict:
        return {"tag": "plain_text", "content": content}

    def _md(content: str) -> dict:
        return {"tag": "lark_md", "content": content}

    def _div(text: dict) -> dict:
        return {"tag": "div", "text": text}

    def _hr() -> dict:
        return {"tag": "hr"}

    def _field_row(label: str, value: str) -> dict:
        return {
            "tag": "column_set",
            "flex_mode": "none",
            "columns": [
                {"tag": "column", "width": "weighted", "weight": 1,
                 "elements": [_div(_md(f"**{label}**"))]},
                {"tag": "column", "width": "weighted", "weight": 3,
                 "elements": [_div(_pt(str(value) if value else "—"))]},
            ],
        }

    elements = [
        _div(_md(f"📋 **{t('card.confirm_prompt')}**")),
        _hr(),
        _field_row(t("label.customer"), customer_id or t("placeholder.dash")),
        _field_row(t("label.product_model"), product_model or t("placeholder.dash")),
        _div(_md(f"**{t('label.feedback_text')}**")),
        _div(_pt(feedback_text)),
    ]

    if ai_summary:
        elements.append(_hr())
        elements.append(_div(_md(f"🤖 **{t('card.ai_summary')}**")))
        elements.append(_div(_pt(ai_summary)))

    elements.append(_hr())

    # 确认/补充按钮
    elements.append({
        "tag": "column_set",
        "flex_mode": "none",
        "columns": [
            {"tag": "column", "width": "weighted", "weight": 1,
             "elements": [
                 {"tag": "button", "text": _pt(t("btn.confirm")), "type": "primary",
                  "behaviors": [{"type": "callback", "value": {
                      "action": "customer_confirm",
                      "feedback_text": feedback_text,
                      "product_model": product_model,
                      "customer_id": customer_id,
                  }}]},
                 {"tag": "button", "text": _pt(t("btn.edit")), "type": "default",
                  "behaviors": [{"type": "callback", "value": {
                      "action": "customer_edit",
                      "feedback_text": feedback_text,
                      "product_model": product_model,
                      "customer_id": customer_id,
                  }}]},
             ]},
        ],
    })

    return {
        "schema": "2.0",
        "header": {"title": _pt(f"📝 {t('card.confirm_title')}"), "template": "blue"},
        "body": {"elements": elements},
    }


# ─── 转交他人卡片 ──────────────────────────────────────

def build_transfer_card(
    original_decision: dict[str, Any],
    feedback_text: str = "",
) -> dict[str, Any]:
    """
    转交他人卡片：输入飞书姓名，搜索联系人，转交处理。

    研发点"转交他人"后收到这张卡片：
    - 输入飞书姓名
    - 点"搜索并转交" → 搜索飞书联系人 → 发路由卡片给对方
    """
    def _pt(content: str) -> dict:
        return {"tag": "plain_text", "content": content}

    def _md(content: str) -> dict:
        return {"tag": "lark_md", "content": content}

    def _div(text: dict) -> dict:
        return {"tag": "div", "text": text}

    def _hr() -> dict:
        return {"tag": "hr"}

    req_id = original_decision.get("matched_requirement_id", "")
    elements = [
        _div(_md(f"↗️ **{t('card.transfer_title')}**")),
        _div(_pt(t("card.transfer_original_req", req_id=req_id or t("placeholder.dash")))),
        _div(_pt(t("card.transfer_original_feedback", text=feedback_text[:80] + "..." if len(feedback_text) > 80 else feedback_text))),
        _hr(),
        # 直接列出几个常见联系人作为转交选项
        _div(_md(f"**Select a colleague to transfer to:**")),
    ]

    # 获取几个常见联系人
    jacky_name = "Jacky Lv"
    jacky_id = os.environ.get("JACKY_OPEN_ID", "")

    # 用按钮列表，每个按钮是一个callback
    transfer_buttons = []
    if jacky_id:
        transfer_buttons.append(
            {"tag": "button", "text": _pt(f"👤 {jacky_name}"), "type": "default",
             "behaviors": [{"type": "callback", "value": {
                 "action": "transfer_submit",
                 "requirement_id": req_id,
                 "feedback_text": feedback_text,
                 "target_name": jacky_name,
                 "target_open_id": jacky_id,
             }}]}
        )

    # 加一个"输入姓名"按钮（通过消息回复）
    transfer_buttons.append(
        {"tag": "button", "text": _pt(f"✏️ Enter name manually"), "type": "default",
         "behaviors": [{"type": "callback", "value": {
             "action": "transfer_manual",
             "requirement_id": req_id,
             "feedback_text": feedback_text,
         }}]}
    )

    elements.append({
        "tag": "column_set",
        "flex_mode": "none",
        "columns": [
            {"tag": "column", "width": "weighted", "weight": 1,
             "elements": transfer_buttons},
        ],
    })

    return {
        "schema": "2.0",
        "header": {"title": _pt(f"↗️ {t('card.transfer_title')}"), "template": "orange"},
        "body": {"elements": elements},
    }


# ─── 已处理确认卡片（发给客户）──────────────────────────

def build_resolved_notification_card(
    customer_id: str,
    requirement_id: str,
    resolved_by: str,
    resolution_note: str = "",
) -> dict[str, Any]:
    """
    已处理通知卡片：研发点"已处理"后，发这张卡片通知客户。

    客户收到后知道：问题已处理，附处理说明。
    """
    def _pt(content: str) -> dict:
        return {"tag": "plain_text", "content": content}

    def _md(content: str) -> dict:
        return {"tag": "lark_md", "content": content}

    def _div(text: dict) -> dict:
        return {"tag": "div", "text": text}

    def _hr() -> dict:
        return {"tag": "hr"}

    elements = [
        _div(_md(f"✅ **{t('card.resolved_prompt')}**")),
        _hr(),
        {"tag": "column_set", "flex_mode": "none",
         "columns": [
             {"tag": "column", "width": "weighted", "weight": 1,
              "elements": [_div(_md(f"**{t('label.related_requirement')}**"))]},
             {"tag": "column", "width": "weighted", "weight": 3,
              "elements": [_div(_pt(requirement_id or t("placeholder.dash")))]},
         ]},
        {"tag": "column_set", "flex_mode": "none",
         "columns": [
             {"tag": "column", "width": "weighted", "weight": 1,
              "elements": [_div(_md(f"**{t('label.resolved_by')}**"))]},
             {"tag": "column", "width": "weighted", "weight": 3,
              "elements": [_div(_pt(resolved_by))]},
         ]},
    ]

    if resolution_note:
        elements.append(_hr())
        elements.append(_div(_md(f"**{t('label.resolution_note')}**")))
        elements.append(_div(_pt(resolution_note)))

    elements.append(_hr())
    elements.append(_div(_md(t("card.thank_you"))))

    return {
        "schema": "2.0",
        "header": {"title": _pt(f"✅ {t('card.resolved_title')}"), "template": "green"},
        "body": {"elements": elements},
    }


# ─── 卡片发送辅助函数 ──────────────────────────────────

def send_card_to_open_id(open_id: str, card_json: dict[str, Any]) -> dict[str, Any]:
    """直接发卡片给指定 open_id，返回结果。"""
    cfg = _get_config()
    if not open_id:
        return {"ok": False, "error": "no open_id"}

    token = _get_token()
    resp = requests.post(
        f"{cfg['base_url']}/im/v1/messages",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        params={"receive_id_type": "open_id"},
        json={
            "receive_id": open_id,
            "msg_type": "interactive",
            "content": json.dumps(card_json),
        },
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[lark_notifier] ❌ 发送失败: {data.get('msg')}")
        return {"ok": False, "error": data.get("msg", "unknown")}

    message_id = data.get("data", {}).get("message_id", "")
    print(f"[lark_notifier] ✅ 卡片已发送 (open_id={open_id[:12]}...)")
    return {"ok": True, "message_id": message_id}


def search_feishu_user(name: str) -> dict[str, Any]:
    """
    搜索飞书联系人，返回 open_id + 姓名。
    先查 people_map，再查飞书通讯录 API。
    """
    cfg = _get_config()

    # 1. 先查 people_map（硬编码映射）
    try:
        _pipeline_dir = os.path.join(os.path.dirname(__file__), "..", "..", "ai-requirement-pipeline", "pipeline")
        _pipeline_dir = os.path.abspath(_pipeline_dir)
        if _pipeline_dir not in sys.path:
            sys.path.insert(0, _pipeline_dir)
        from people_map import PEOPLE_MAP, JACKY_OPEN_ID
        if name in PEOPLE_MAP:
            print(f"  [people_map] {name!r} → {PEOPLE_MAP[name][:12]}...")
            return {"open_id": PEOPLE_MAP[name], "name": name}
    except ImportError:
        pass

    # 2. 查飞书通讯录
    token = _get_token()
    resp = requests.get(
        f"{cfg['base_url']}/contact/v3/users/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"query": name, "user_id_type": "open_id", "page_size": 1},
    )
    data = resp.json()
    if data.get("code") == 0:
        users = data.get("data", {}).get("items", [])
        if users:
            user = users[0]
            open_id = user.get("open_id", "")
            display = user.get("name", name)
            print(f"  [feishu_search] {name!r} → {open_id[:12]}... ({display})")
            return {"open_id": open_id, "name": display}

    print(f"  [feishu_search] {name!r} → 未找到")
    return {"open_id": "", "name": name}
