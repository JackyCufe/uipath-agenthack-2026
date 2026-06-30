"""
card_handler.py — 飞书卡片按钮回调接收（长连接 WebSocket 方式）

⚠️ 重要：demo.py 必须在 OpenClaw 主进程之外单独运行（terminal 直接跑），
否则 OpenClaw 主进程会竞争同一个 WS 连接，回调发不到我们的 handler。

对外暴露：
  - start_card_listener()               → 启动长连接（后台线程）
  - register_schema(card_id, schema)    → 发卡片时注册 schema，供回调时重建"已确认"卡片
  - wait_for_card_action(card_id, timeout=None) → 阻塞直到收到按钮回调

DEMO_MODE=true 时直接返回 approve，不启动长连接。
"""
from __future__ import annotations

import queue
import re
import threading
import time
from typing import Optional

from config import FEISHU_APP_ID, FEISHU_APP_SECRET, DEMO_MODE, AFTERSALES_GROUP_CHAT_ID

# Thread-safe store: card_id → {"action": "approve"|"reject", "reason": str}
_action_store: dict[str, dict] = {}
# card_id → 原始 schema dict（用于回调时重建"已确认"状态卡片）
_schema_store: dict[str, dict] = {}
# card_id → feishu message_id（备用）
_message_id_store: dict[str, str] = {}
_store_lock = threading.Lock()
_listener_started = False

# A2: 飞书消息触发 Pipeline — 消息队列
_incoming_message_queue: queue.Queue = queue.Queue()


def get_incoming_message_queue() -> queue.Queue:
    """返回飞书消息队列，供 demo.py 消费触发 Pipeline。"""
    return _incoming_message_queue


def _set_action(card_id: str, action: str, reason: str = "") -> None:
    with _store_lock:
        _action_store[card_id] = {"action": action, "reason": reason}
        print(f"[card_handler] ✅ 存储回调: card_id={card_id} action={action}")


def _get_action(card_id: str) -> Optional[dict]:
    with _store_lock:
        return _action_store.get(card_id)


def register_schema(card_id: str, schema: dict) -> None:
    """发卡片时把原始 schema 注册进来，供回调时重建"已确认"状态卡片用。"""
    with _store_lock:
        _schema_store[card_id] = schema


def _get_schema(card_id: str) -> Optional[dict]:
    with _store_lock:
        return _schema_store.get(card_id)


def register_message_id(card_id: str, message_id: str) -> None:
    """发卡片后将 message_id 注册进来（备用）。"""
    with _store_lock:
        _message_id_store[card_id] = message_id


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def start_card_listener() -> None:
    """启动飞书 WebSocket 长连接，接收卡片按钮回调。

    ⚠️ 必须在 OpenClaw 主进程之外单独运行，否则 WS 连接被 OpenClaw 竞争。
    """
    global _listener_started
    if DEMO_MODE:
        print("[card_handler] DEMO_MODE=true — 跳过长连接")
        return
    if _listener_started:
        return

    try:
        import lark_oapi as lark
    except ImportError as exc:
        print(f"[card_handler] lark_oapi 未安装: {exc}")
        return

    def card_callback_handler(data):
        """
        lark_oapi 触发 card.action.trigger 时调用。
        必须在 3 秒内返回 P2CardActionTriggerResponse。
        返回的 card 字段会原地替换飞书里的卡片。
        """
        from lark_oapi.event.callback.model.p2_card_action_trigger import (
            P2CardActionTriggerResponse, CallBackToast, CallBackCard
        )
        from card_templates import (
            build_approved_confirmed_card,
            build_rejected_confirmed_card,
            build_stage2_confirm_approved_card,
        )

        try:
            event = getattr(data, "event", None) or data
            action_obj = getattr(event, "action", None)
            value = getattr(action_obj, "value", {}) or {} if action_obj else {}
            form_value = getattr(action_obj, "form_value", {}) or {}
            btn_name = getattr(action_obj, "name", "") or ""

            action_type = value.get("action_type", "") if isinstance(value, dict) else ""
            card_id = value.get("card_id", "") if isinstance(value, dict) else ""

            # form_submit 按钮路由
            if not action_type:
                if btn_name.startswith("approve_submit_"):
                    action_type = "approve"
                    card_id = btn_name[len("approve_submit_"):]
                elif btn_name.startswith("reject_submit_"):
                    action_type = "reject"
                    card_id = btn_name[len("reject_submit_"):]
                elif btn_name.startswith("submit_approval_"):
                    # 六元审批表单：outcome 决定 action_type
                    outcome = ""
                    if isinstance(form_value, dict):
                        outcome = form_value.get("outcome", "")
                    card_id = btn_name[len("submit_approval_"):]
                    # outcome → action_type 映射
                    _outcome_map = {
                        "approved": "approve",
                        "approved_with_conditions": "approve_with_conditions",
                        "rejected": "reject",
                        "deferred": "defer",
                        "info_needed": "info_needed",
                        "delegated": "delegate",
                    }
                    action_type = _outcome_map.get(outcome, "info_needed")
                    print(f"[card_handler] 六元审批: outcome={outcome!r} → action_type={action_type!r}")
                elif btn_name.startswith("followup_submit_"):
                    action_type = "followup"
                    card_id = btn_name[len("followup_submit_"):]
                elif btn_name.startswith("feedback_submit_"):
                    action_type = "feedback_submit"
                    card_id = btn_name[len("feedback_submit_"):]
                elif btn_name.startswith("feedback_skip_"):
                    action_type = "feedback_skip"
                    card_id = btn_name[len("feedback_skip_"):]
                elif btn_name.startswith("stage1_submit_"):
                    action_type = "stage1_submit"
                    card_id = btn_name[len("stage1_submit_"):]
                elif btn_name.startswith("stage1_abandon_"):
                    action_type = "abandon"
                    card_id = btn_name[len("stage1_abandon_"):]
                elif btn_name.startswith("retry_submit_"):
                    action_type = "retry_submit"
                    card_id = btn_name[len("retry_submit_"):]
                elif btn_name.startswith("abandon_submit_"):
                    action_type = "abandon"
                    card_id = btn_name[len("abandon_submit_"):]
                elif btn_name.startswith("feedback_design_submit_"):
                    action_type = "feedback_design_submit"
                    card_id = btn_name[len("feedback_design_submit_"):]
                elif btn_name.startswith("s2_generate_"):
                    action_type = "s2_generate"
                    card_id = btn_name[len("s2_generate_"):]
                elif btn_name.startswith("s2_recall_"):
                    action_type = "s2_recall"
                    card_id = btn_name[len("s2_recall_"):]
                elif btn_name.startswith("s2_confirm_back_"):
                    action_type = "s2_confirm_back"
                    card_id = btn_name[len("s2_confirm_back_"):]
                elif btn_name.startswith("s2_confirm_approve_"):
                    action_type = "s2_confirm_approve"
                    card_id = btn_name[len("s2_confirm_approve_"):]
                elif btn_name.startswith("escalate_submit_"):
                    action_type = "escalate"
                    card_id = btn_name[len("escalate_submit_"):]
                else:
                    # 兜底：从 btn_name 里提取 action_type 和 card_id
                    # 格式：{action_type}_{card_id}，card_id 以 s1c_/s2c_/s3c_/s4c_/s5c_ 等开头
                    _snc_match = re.search(r'_(s\dc_)', btn_name)
                    if _snc_match:
                        _snc_pos = _snc_match.start()
                        action_type = btn_name[:_snc_pos]
                        card_id = btn_name[_snc_pos + 1:]  # 去掉分隔符 _，保留 s1c_/s2c_/...

            # 修改建议（A3：通过时可填）
            suggestion = ""
            if isinstance(form_value, dict):
                suggestion = form_value.get("approve_suggestion", "") or "" or form_value.get("note", "")

            # 下一位负责人（通过时填写）
            next_assignee = ""
            if isinstance(form_value, dict):
                next_assignee = form_value.get("next_assignee", "") or ""

            # Stage1 表单内容
            s1_fields = {}
            if isinstance(form_value, dict):
                for key in ("s1_who", "s1_scene", "s1_problem", "s1_expected", "s1_customer", "questionnaire"):
                    if form_value.get(key):
                        s1_fields[key] = form_value[key]

            # 拒绝原因（统一从 note 或 reject_reason 读取）
            reason = ""
            if isinstance(form_value, dict):
                reason = form_value.get("reject_reason", "") or "" or form_value.get("note", "")
            if not reason and isinstance(value, dict):
                reason = value.get("reason", "") or ""

            # 追问卡片回答
            followup_response = ""
            if isinstance(form_value, dict):
                followup_response = form_value.get("followup_response", "") or ""

            # 反馈录入
            satisfaction_rate = ""
            feedback_summary = ""
            if isinstance(form_value, dict):
                satisfaction_rate = form_value.get("satisfaction_rate", "") or ""
                feedback_summary = form_value.get("feedback_summary", "") or ""

            print(f"[card_handler] 回调: action_type={action_type!r} card_id={card_id!r} "
                  f"reason={reason!r} btn_name={btn_name!r}")

            resp = P2CardActionTriggerResponse()

            if action_type in ("stage1_submit", "retry_submit", "s1_confirm_submit") and card_id:
                # 四问必填校验：从 form_value 直接取（不过滤空值）
                _required_keys = ("s1_who", "s1_scene", "s1_problem", "s1_expected")
                _missing = [
                    k for k in _required_keys
                    if not (isinstance(form_value, dict) and form_value.get(k, "").strip())
                ]
                if _missing:
                    print(f"[card_handler] ⚠️ 四问未填完整，缺失字段: {_missing}")
                    toast = CallBackToast()
                    toast.type = "error"
                    toast.content = "请填写完整四要素再提交（客户是谁、使用场景、遇到的问题、期望结果）"
                    resp.toast = toast
                    return resp

                # 统一 action 名称：s1_confirm_submit 等同于 stage1_submit
                if action_type == "s1_confirm_submit":
                    action_type = "stage1_submit"

                # 重新收集 s1_fields（含空字段，校验通过后再存）
                s1_fields = {}
                if isinstance(form_value, dict):
                    for key in ("s1_who", "s1_scene", "s1_problem", "s1_expected", "s1_customer", "questionnaire"):
                        s1_fields[key] = form_value.get(key, "")

                with _store_lock:
                    _action_store[card_id] = {
                        "action": action_type,
                        "s1_fields": s1_fields,
                        "next_assignee": next_assignee,
                    }
                print(f"[card_handler] ✅ Stage1提交: card_id={card_id} action={action_type}")
                toast = CallBackToast()
                toast.type = "success"
                toast.content = "✅ 需求已提交，正在推送给下一位审批人..."
                resp.toast = toast
                cb_card = CallBackCard()
                cb_card.type = "raw"
                # 从 schema 中取 req_id；同时把四问传给确认卡片
                _schema = _schema_store.get(card_id, {})
                _req_id = _schema.get("req_id") or card_id
                _four_q = {
                    "who":      s1_fields.get("s1_who", ""),
                    "scene":    s1_fields.get("s1_scene", ""),
                    "problem":  s1_fields.get("s1_problem", ""),
                    "expected": s1_fields.get("s1_expected", ""),
                } if s1_fields else None
                from card_templates import build_stage1_confirmed_card
                cb_card.data = build_stage1_confirmed_card(card_id, _req_id, next_assignee, _four_q)
                resp.card = cb_card

            elif action_type == "escalate" and card_id:
                with _store_lock:
                    _action_store[card_id] = {"action": "escalate"}
                print(f"[card_handler] ✅ 继续往上退: card_id={card_id}")
                toast = CallBackToast()
                toast.type = "info"
                toast.content = "⬆️ 已通知上一级负责人处理。"
                resp.toast = toast
                cb_card = CallBackCard()
                cb_card.type = "raw"
                cb_card.data = {
                    "schema": "2.0",
                    "header": {"title": {"tag": "plain_text", "content": "⬆️ 已向上退回"}, "template": "orange"},
                    "body": {"elements": [{"tag": "div", "text": {"tag": "plain_text", "content": "已将问题传递给上一级负责人，请等待对方决定。"}}]},
                }
                resp.card = cb_card

            elif action_type == "abandon" and card_id:
                with _store_lock:
                    _action_store[card_id] = {"action": "abandon", "reason": reason}
                print(f"[card_handler] ✅ 放弃需求: card_id={card_id}")
                toast = CallBackToast()
                toast.type = "info"
                toast.content = "需求已放弃，流程终止。"
                resp.toast = toast
                cb_card = CallBackCard()
                cb_card.type = "raw"
                cb_card.data = {
                    "schema": "2.0",
                    "header": {"title": {"tag": "plain_text", "content": "🚫 需求已放弃"}, "template": "grey"},
                    "body": {"elements": [{"tag": "div", "text": {"tag": "plain_text", "content": "需求已终止，记录已保存到多维表格。"}}]},
                }
                resp.card = cb_card

            elif action_type == "feedback_design_submit" and card_id:
                # 从 form_value 取用户最终填写的问卷内容
                questionnaire_confirmed = (
                    (form_value.get("questionnaire", "") if isinstance(form_value, dict) else "")
                    or s1_fields.get("questionnaire", "")
                )
                with _store_lock:
                    _action_store[card_id] = {
                        "action": "feedback_design_submit",
                        "questionnaire": questionnaire_confirmed,
                    }
                print(f"[card_handler] ✅ 问卷设计确认: card_id={card_id}")
                toast = CallBackToast()
                toast.type = "success"
                toast.content = "✅ 问卷已确认，请开始分发。"
                resp.toast = toast
                cb_card = CallBackCard()
                cb_card.type = "raw"
                # 展示用户确认的问卷内容而非空来
                _q_preview = questionnaire_confirmed[:500] + ("…" if len(questionnaire_confirmed) > 500 else "")
                cb_card.data = {
                    "schema": "2.0",
                    "header": {"title": {"tag": "plain_text", "content": "✅ 问卷已确认"}, "template": "green"},
                    "body": {"elements": [
                        {"tag": "div", "text": {"tag": "lark_md", "content": "**已确认的问卷内容**"}},
                        {"tag": "div", "text": {"tag": "plain_text", "content": _q_preview or "（未填写）"}},
                        {"tag": "hr"},
                        {"tag": "div", "text": {"tag": "plain_text", "content": "请将问卷分发给客户，收集到反馈后返回录入。"}},
                    ]},
                }
                resp.card = cb_card

            elif action_type == "approve" and card_id:
                # 提取所有表单字段（含各阶段专属字段）
                all_form = dict(form_value) if isinstance(form_value, dict) else {}
                with _store_lock:
                    _action_store[card_id] = {
                        "action": "approve",
                        "reason": reason,
                        "suggestion": suggestion,
                        "next_assignee": next_assignee,
                        # Stage2 专属
                        "core_value":           all_form.get("core_value", ""),
                        "feature_def":          all_form.get("feature_def", ""),
                        "acceptance_criteria":  all_form.get("acceptance_criteria", ""),
                        "priority":             all_form.get("priority", ""),
                        "impact_users":         all_form.get("impact_users", ""),
                        "extra_note":           all_form.get("extra_note", ""),
                        # Stage3 专属
                        "tech_plan":      all_form.get("tech_plan", ""),
                        "workload_days":  all_form.get("workload_days", ""),
                        "risks":          all_form.get("risks", ""),
                        "scenario_test":  all_form.get("scenario_test", ""),
                        "test_note":      all_form.get("test_note", ""),
                        # Stage4 专属
                        "release_value":    all_form.get("release_value", ""),
                        "version":          all_form.get("version", ""),
                        "release_date":     all_form.get("release_date", ""),
                        "scenario_verified": all_form.get("scenario_verified", ""),
                        "release_risk":     all_form.get("release_risk", ""),
                        "rollback_plan":    all_form.get("rollback_plan", ""),
                    }
                print(f"[card_handler] ✅ 存储回调: card_id={card_id} action=approve next={next_assignee}")

                original_schema = _get_schema(card_id)
                if original_schema:
                    # 把本轮用户填写的非空表单字段追加进 schema，供确认卡片展示
                    filled = {k: v for k, v in all_form.items() if v}
                    merged_schema = {**original_schema, "filled_fields": filled}

                    toast = CallBackToast()
                    toast.type = "success"
                    toast.content = "✅ 已确认通过，正在进入下一环节..."
                    resp.toast = toast

                    cb_card = CallBackCard()
                    cb_card.type = "raw"
                    cb_card.data = build_approved_confirmed_card(merged_schema, card_id)
                    resp.card = cb_card

            elif action_type == "reject" and card_id:
                _set_action(card_id, action_type, reason)

                original_schema = _get_schema(card_id)
                if original_schema:
                    # 拒绝时同样展示已填表单内容，帮助上一级了解拒绝前填了什么
                    all_form_for_reject = dict(form_value) if isinstance(form_value, dict) else {}
                    filled_for_reject = {k: v for k, v in all_form_for_reject.items() if v}
                    merged_schema_reject = {**original_schema, "filled_fields": filled_for_reject}

                    toast = CallBackToast()
                    toast.type = "error"
                    toast.content = f"❌ 已拒绝{'，原因：' + reason if reason else ''}"
                    resp.toast = toast

                    cb_card = CallBackCard()
                    cb_card.type = "raw"
                    cb_card.data = build_rejected_confirmed_card(merged_schema_reject, card_id, reason)
                    resp.card = cb_card

            elif action_type == "followup" and card_id:
                with _store_lock:
                    _action_store[card_id] = {"action": "followup", "reason": "", "followup_response": followup_response}
                print(f"[card_handler] ✅ 存储回调: card_id={card_id} action=followup")
                toast = CallBackToast()
                toast.type = "success"
                toast.content = "✅ 补充信息已提交，正在重新审核..."
                resp.toast = toast
                cb_card = CallBackCard()
                cb_card.type = "raw"
                cb_card.data = {
                    "schema": "2.0",
                    "header": {"title": {"tag": "plain_text", "content": "✅ 补充信息已提交"}, "template": "green"},
                    "body": {"elements": [{"tag": "div", "text": {"tag": "plain_text", "content": f"内容：{followup_response[:100]}"}}]},
                }
                resp.card = cb_card

            elif action_type in ("feedback_submit", "feedback_skip") and card_id:
                _fb_payload = {
                    "action": action_type,
                    "reason": "",
                    "satisfaction_rate": satisfaction_rate,
                    "feedback_summary": feedback_summary,
                }
                # 透传每道题的答案（answer_1, answer_2, ...）
                if isinstance(form_value, dict):
                    for _k, _v in form_value.items():
                        if _k.startswith("answer_"):
                            _fb_payload[_k] = _v
                with _store_lock:
                    _action_store[card_id] = _fb_payload
                print(f"[card_handler] ✅ 存储回调: card_id={card_id} action={action_type}")
                toast = CallBackToast()
                toast.type = "success"
                toast.content = "✅ 反馈已录入，正在运行复盘分析..."
                resp.toast = toast
                cb_card = CallBackCard()
                cb_card.type = "raw"
                _sat_text = f"满意度均分：{satisfaction_rate}" if satisfaction_rate else "（未填写满意度）"
                _fb_text = feedback_summary[:300] + ("…" if len(feedback_summary) > 300 else "") if feedback_summary else "（未填写反馈摘要）"
                _is_skip = action_type == "feedback_skip"
                cb_card.data = {
                    "schema": "2.0",
                    "header": {"title": {"tag": "plain_text", "content": "⏭️ 跳过反馈" if _is_skip else "✅ 反馈录入完成"}, "template": "green"},
                    "body": {"elements": [
                        {"tag": "div", "text": {"tag": "lark_md", "content": "**已录入反馈数据**"}},
                        {"tag": "div", "text": {"tag": "plain_text", "content": _sat_text}},
                        {"tag": "div", "text": {"tag": "plain_text", "content": f"反馈摘要：{_fb_text}"}},
                        {"tag": "hr"},
                        {"tag": "div", "text": {"tag": "plain_text", "content": "复盘分析将在后台运行，完成后通知。"}},
                    ]},
                }
                resp.card = cb_card

            elif action_type == "pipeline_done" and card_id:
                _set_action(card_id, "pipeline_done", "")
                toast = CallBackToast()
                toast.type = "success"
                toast.content = "🏁 Pipeline 已归档，感谢使用！"
                resp.toast = toast
                cb_card = CallBackCard()
                cb_card.type = "raw"
                cb_card.data = {
                    "schema": "2.0",
                    "header": {"title": {"tag": "plain_text", "content": "🏁 Pipeline 已完成归档"}, "template": "green"},
                    "body": {"elements": [{"tag": "div", "text": {"tag": "plain_text", "content": "所有数据已保存至多维表格，Pipeline 正式结束。"}}]},
                }
                resp.card = cb_card

            elif action_type == "s2_confirm_approve" and card_id:
                # Stage2 第二张卡：PM确认测试用例，传给研发
                _s2c_payload = {"action": "s2_confirm_approve", "next_assignee": next_assignee}
                # 透传所有测试用例文本（test_case_1, test_case_2, ...）
                if isinstance(form_value, dict):
                    for _k, _v in form_value.items():
                        if _k.startswith("test_case_"):
                            _s2c_payload[_k] = _v
                with _store_lock:
                    _action_store[card_id] = _s2c_payload
                print(f"[card_handler] ✅ Stage2测试用例确认通过: card_id={card_id} next={next_assignee}")
                toast = CallBackToast()
                toast.type = "success"
                toast.content = "✅ 测试用例已确认，正在传给研发..."
                resp.toast = toast
                cb_card = CallBackCard()
                cb_card.type = "raw"
                # 保留验收标准 + 测试用例（含 PM 编辑内容），展示为只读卡
                _s2c_schema = dict(_get_schema(card_id) or {})
                # 把 PM 编辑后的测试用例文本合回 test_cases 供只读卡展示
                if isinstance(form_value, dict):
                    _edited_cases = []
                    for _i, _tc in enumerate(_s2c_schema.get("test_cases", []), 1):
                        _edited_text = form_value.get(f"test_case_{_i}", "")
                        if _edited_text:
                            _tc_copy = dict(_tc)
                            _tc_copy["steps"] = [_edited_text]
                            _edited_cases.append(_tc_copy)
                        else:
                            _edited_cases.append(_tc)
                    if _edited_cases:
                        _s2c_schema["test_cases"] = _edited_cases
                from card_templates import build_stage2_confirm_approved_card
                cb_card.data = build_stage2_confirm_approved_card(_s2c_schema)
                resp.card = cb_card

            elif action_type == "s2_confirm_back" and card_id:
                # Stage2 第二张卡：PM回退，重新填写第一张卡
                with _store_lock:
                    _action_store[card_id] = {"action": "s2_confirm_back"}
                print(f"[card_handler] ✅ Stage2测试用例确认回退: card_id={card_id}")
                toast = CallBackToast()
                toast.type = "info"
                toast.content = "↩️ 已回退，正在重新发送第一步填写卡..."
                resp.toast = toast
                cb_card = CallBackCard()
                cb_card.type = "raw"
                cb_card.data = {
                    "schema": "2.0",
                    "header": {"title": {"tag": "plain_text", "content": "↩️ 回退到第一步"}, "template": "orange"},
                    "body": {"elements": [{"tag": "div", "text": {"tag": "plain_text", "content": "正在重新发送产品审批填写卡，请稍候。"}}]},
                }
                resp.card = cb_card

            elif action_type == "s2_generate" and card_id:
                # Stage2 第一张卡：PM点「生成测试用例」提交
                _s2g_payload = {"action": "s2_generate"}
                if isinstance(form_value, dict):
                    for _k in ("core_value", "acceptance_criteria", "feature_def", "priority",
                               "impact_users", "extra_note", "next_assignee"):
                        _s2g_payload[_k] = form_value.get(_k, "")
                with _store_lock:
                    _action_store[card_id] = _s2g_payload
                print(f"[card_handler] ✅ Stage2生成测试用例: card_id={card_id}")
                toast = CallBackToast()
                toast.type = "info"
                toast.content = "⏳ 正在生成测试用例，请稍候..."
                resp.toast = toast
                cb_card = CallBackCard()
                cb_card.type = "raw"
                # 保留原有卡片内容，叠加 PM 本轮填写的字段，仅改变状态
                _s2g_schema = dict(_get_schema(card_id) or {})
                _s2g_schema["filled_fields"] = {k: v for k, v in (form_value or {}).items() if v}
                from card_templates import build_approved_confirmed_card
                cb_card.data = build_approved_confirmed_card(_s2g_schema, card_id)
                resp.card = cb_card

            elif action_type == "s2_recall" and card_id:
                # Stage2 第一张卡：PM撤回上一级
                all_form = dict(form_value) if isinstance(form_value, dict) else {}
                recall_reason = all_form.get("reject_reason", "") or reason
                with _store_lock:
                    _action_store[card_id] = {
                        "action": "s2_recall",
                        "reason": recall_reason,
                    }
                print(f"[card_handler] ✅ Stage2撤回上一级: card_id={card_id}")
                toast = CallBackToast()
                toast.type = "info"
                toast.content = "↩️ 已退回至售前，通知重新提交。"
                resp.toast = toast
                cb_card = CallBackCard()
                cb_card.type = "raw"
                cb_card.data = {
                    "schema": "2.0",
                    "header": {"title": {"tag": "plain_text", "content": "↩️ 已退回至售前"}, "template": "orange"},
                    "body": {"elements": [
                        {"tag": "div", "text": {"tag": "plain_text", "content": "需求已退回售前，请等待重新提交。"}},
                        {"tag": "div", "text": {"tag": "plain_text", "content": f"退回原因：{recall_reason or '未填写'}"}},
                    ]},
                }
                resp.card = cb_card

            else:
                print(f"[card_handler] ⚠️ 无法解析动作 value={value} form_value={form_value} btn_name={btn_name!r}")

            return resp

        except Exception as exc:
            print(f"[card_handler] 处理异常: {exc}")
            import traceback; traceback.print_exc()
            return P2CardActionTriggerResponse()

    def message_receive_handler(data):
        """接收飞书用户发给 Bot 的消息，放入队列供 demo.py 消费触发 Pipeline。
        售后群（AFTERSALES_GROUP_CHAT_ID）的所有消息静默忽略，不触发 Pipeline 也不回复。
        """
        try:
            import json as _json
            msg = getattr(data, "event", None)
            if msg is None:
                return
            message = getattr(msg, "message", None)
            if message is None:
                return

            # 售后群静默：来自该群的任何消息直接忽略
            chat_id = getattr(message, "chat_id", "") or ""
            if chat_id == AFTERSALES_GROUP_CHAT_ID:
                print(f"[message_handler] 售后群消息，静默忽略 chat_id={chat_id}")
                return

            msg_type = getattr(message, "message_type", "") or ""
            if msg_type != "text":
                return
            content_raw = getattr(message, "content", "{}") or "{}"
            text = _json.loads(content_raw).get("text", "").strip()
            sender = getattr(msg, "sender", None)
            sender_id = getattr(sender, "sender_id", None)
            open_id = getattr(sender_id, "open_id", "") if sender_id else ""
            chat_id = getattr(message, "chat_id", "") or ""
            if text:
                print(f"[message_handler] 收到新需求消息: {text[:80]} sender={open_id} chat_id={chat_id}")
                _incoming_message_queue.put({"text": text, "sender_open_id": open_id, "sender_chat_id": chat_id})
        except Exception as exc:
            print(f"[message_handler] 解析消息异常: {exc}")

    def message_read_handler(data):
        """静默忽略消息已读回执事件（im.message.message_read_v1）。"""
        pass

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_card_action_trigger(card_callback_handler)
        .register_p2_im_message_receive_v1(message_receive_handler)
        .register_p2_im_message_message_read_v1(message_read_handler)
        .build()
    )

    ws_client = lark.ws.Client(
        FEISHU_APP_ID,
        FEISHU_APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.WARNING,
    )

    def _run():
        print("[card_handler] WebSocket 长连接启动中...")
        try:
            ws_client.start()
        except Exception as exc:
            print(f"[card_handler] WebSocket 异常: {exc}")

    thread = threading.Thread(target=_run, daemon=True, name="feishu-card-ws")
    thread.start()
    _listener_started = True
    time.sleep(2)
    print("[card_handler] ✅ WebSocket 长连接已启动，等待卡片回调...")


def clear_action(card_id: str) -> None:
    """清除已处理的 card_id，避免下次发同名卡片时立刻命中旧结果。"""
    with _store_lock:
        _action_store.pop(card_id, None)


def wait_for_card_action(card_id: str, timeout: Optional[float] = None) -> dict:
    """阻塞直到收到指定 card_id 的按钮回调。"""
    if DEMO_MODE:
        print(f"[card_handler] DEMO_MODE — 自动通过 card_id={card_id}")
        return {"action": "approve", "reason": ""}

    deadline = (time.monotonic() + timeout) if timeout is not None else None
    print(f"[card_handler] ⏳ 等待按钮点击 card_id={card_id}...")

    while True:
        result = _get_action(card_id)
        if result is not None:
            print(f"[card_handler] ✅ 收到动作: {result}")
            return result

        if deadline is not None and time.monotonic() >= deadline:
            print(f"[card_handler] ⏰ 等待超时 card_id={card_id}")
            return {"action": "timeout", "reason": f"超时({timeout}s)"}

        time.sleep(0.5)
