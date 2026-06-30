"""
card_templates.py — 飞书卡片模板（Card JSON 2.0）

设计原则：
- 每张审批卡片必须包含四问完整内容、进展时间线、上一级备注
- 让每个负责人打开卡片就能看懂需求是什么、要做什么、标准是什么
- 负责人选择：通过时在卡片上填写飞书姓名，Bot 搜索 open_id
"""
from __future__ import annotations
from datetime import datetime

import os as _os
BITABLE_URL = _os.environ.get("BITABLE_URL", "https://my.feishu.cn/base/VSj3bCFngatjbpsv3XZc5QCPnfh")


def _seq_num(id_str: str) -> str:
    """从 'AC-2' / 'TC-3' / 'ac_xxx_001' 等格式中提取序号数字。
    只用于卡片展示，不改变内部数据。
    """
    import re as _re
    m = _re.search(r'[-_](\d+)$', id_str)
    if m:
        return m.group(1).lstrip('0') or '1'
    return id_str


# ─── 基础构件 ────────────────────────────────────────────

def _pt(content: str) -> dict:
    return {"tag": "plain_text", "content": content}


def _md(content: str) -> dict:
    return {"tag": "lark_md", "content": content}


def _hr() -> dict:
    return {"tag": "hr"}


def _div(text: dict) -> dict:
    return {"tag": "div", "text": text}


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


def _base_card_v2(title: str, template: str, elements: list) -> dict:
    return {
        "schema": "2.0",
        "header": {"title": _pt(title), "template": template},
        "body": {"elements": elements},
    }


def _bitable_btn() -> dict:
    return {
        "tag": "button",
        "text": _pt("📊 查看多维表格"),
        "type": "default",
        "behaviors": [{"type": "open_url", "default_url": BITABLE_URL}],
    }


# ─── 四问区域（所有审批卡片共用）──────────────────────────

def _four_q_section(q: dict) -> list:
    """渲染四问内容块，兼容新字段名（who/scene/problem/expected）和旧字段名（what/why/who/done）。"""
    return [
        _div(_md("**📋 客户场景**")),
        _field_row("客户是谁",   q.get("who") or q.get("what") or q.get("customer_who") or "—"),
        _field_row("使用场景",   q.get("scene") or q.get("usage_scenario") or "—"),
        _field_row("遇到的问题", q.get("problem") or q.get("why") or "—"),
        _field_row("期望结果",   q.get("expected") or q.get("done") or q.get("expected_outcome") or "—"),
    ]


# ─── 进展时间线（所有审批卡片共用）────────────────────────

def _timeline_section(history: list[dict]) -> list:
    """
    history: [{"stage": "Stage1", "label": "售前录入", "status": "done"|"current"|"pending", "note": ""}]
    """
    lines = []
    for h in history:
        s = h.get("status", "pending")
        icon = "✅" if s == "done" else ("👈 当前" if s == "current" else "⬜")
        note = f"（{h['note']}）" if h.get("note") else ""
        lines.append(f"{icon} {h['label']}{note}")
    text = "\n".join(lines)
    return [
        _hr(),
        _div(_md("**📍 当前进展**")),
        _div(_pt(text)),
    ]


# ─── 审批操作区（通用）────────────────────────────────────

def _outcome_form_elements(card_id: str, is_last_stage: bool = False) -> list:
    """
    审批表单核心元素（不含 form 标签，供嵌入已有表单）。
    card_id: 用于构造唯一按钮名，回调路由用
    返回: [outcome_select, note_textarea, (可选)next_assignee_input, submit_button]
    """
    outcome_options = [
        {"value": "approved",                     "text": "✅ 通过"},
        {"value": "approved_with_conditions",     "text": "⚠️ 有条件通过"},
        {"value": "rejected",                     "text": "↩️ 驳回"},
        {"value": "deferred",                     "text": "⏸️ 延期"},
        {"value": "info_needed",                  "text": "❓ 需补充信息"},
        {"value": "delegated",                    "text": "↗️ 转交"},
    ]

    elements = [
        {
            "tag": "select_static",
            "name": "outcome",
            "placeholder": _pt("选择审批结果"),
            "options": outcome_options,
            "width": "fill",
        },
        {
            "tag": "textarea",
            "name": "note",
            "placeholder": _pt("驳回原因 / 条件说明 / 延期原因 / 转交对象 / 补充信息说明"),
            "width": "fill",
            "max_length": 300,
        },
    ]

    if not is_last_stage:
        elements.append({
            "tag": "input",
            "name": "next_assignee",
            "placeholder": _pt("下一位审批人飞书姓名（通过/有条件通过时必填）"),
            "width": "fill",
            "max_length": 50,
        })

    elements.append({
        "tag": "button",
        "action_type": "form_submit",
        "name": f"submit_approval_{card_id}",
        "text": _pt("确认提交"),
        "type": "primary",
        "confirm": {
            "title": _pt("确认审批？"),
            "text": _pt("提交后不可撤销。"),
        },
    })

    return elements


def _approval_form(card_id: str, is_last_stage: bool = False) -> list:
    """完整审批表单（含 form 外壳），供通用审批卡片使用。"""
    return [
        _hr(),
        _div(_md("**📝 审批**")),
        {
            "tag": "form",
            "name": f"approval_form_{card_id}",
            "elements": _outcome_form_elements(card_id=card_id, is_last_stage=is_last_stage),
        },
    ]


def _disabled_approval_form() -> list:
    """审批后禁用的占位区域。"""
    return [
        _hr(),
        {
            "tag": "button",
            "text": _pt("📝 已完成审批"),
            "type": "default",
            "disabled": True,
            "disabled_tips": _pt("已完成操作"),
        },
    ]


# ─── 通用审批卡片构建器 ────────────────────────────────────

def build_approval_card(
    card_id: str,
    stage_label: str,         # 如 "Stage2 产品经理审批"
    req_id: str,
    req_title: str,
    customer: str,
    four_q: dict,             # {what, why, who, done}
    history: list[dict],      # 进展时间线
    prev_note: str = "",      # 上一级备注（修改建议）
    prev_role: str = "",      # 上一级角色名
    is_last_stage: bool = False,  # 最后一关不需要选下一级
    llm_summary: str = "",   # LLM 生成的历史阶段汇总
) -> dict:
    """
    通用审批卡片，适用于 Stage 2 / 3 / 4。
    """
    elements = [
        _div(_md(f"**需求 {req_id}**　　{req_title or ''}　　客户：{customer or '—'}")),
    ]

    # 四问
    elements += _four_q_section(four_q)

    # 进展时间线
    elements += _timeline_section(history)

    # 上一级备注
    if prev_note:
        elements += [
            _hr(),
            _div(_md(f"**💬 上一级备注（{prev_role}）**")),
            _div(_pt(prev_note)),
        ]

    # LLM 历史汇总
    if llm_summary:
        elements += [
            _hr(),
            _div(_md("**🤖 历史阶段汇总**")),
            _div(_pt(llm_summary)),
        ]

    # 审批区域（六元统一表单）
    elements += _approval_form(card_id, is_last_stage=is_last_stage)

    elements += [_hr(), _bitable_btn()]

    return _base_card_v2(
        title=f"🔔 {stage_label} | {req_id}",
        template="blue",
        elements=elements,
    )


def _filled_fields_section(stage_label: str, filled: dict) -> list:
    """根据阶段名渲染用户本轮填写的表单字段（只读展示区），供通过/拒绝确认卡复用。"""
    if not filled:
        return []
    if "Stage2" in stage_label:
        rows = [
            ("核心价值",   filled.get("core_value", "")),
            ("验收标准",   filled.get("acceptance_criteria", "")),
            ("功能定义",   filled.get("feature_def", "")),
            ("优先级",     filled.get("priority", "")),
            ("预计影响用户数", filled.get("impact_users", "")),
            ("补充说明",   filled.get("extra_note", "")),
        ]
        title = "**📝 产品审批填写内容（只读）**"
    elif "Stage3" in stage_label:
        rows = [
            ("技术方案",   filled.get("tech_plan", "")),
            ("工作量",     filled.get("workload_days", "")),
            ("风险点",     filled.get("risks", "")),
            ("自测结论",   filled.get("scenario_test", "")),
            ("自测备注",   filled.get("test_note", "")),
        ]
        title = "**📝 研发审批填写内容（只读）**"
    elif "Stage4" in stage_label:
        rows = [
            ("本版核心价值", filled.get("release_value", "")),
            ("版本号",       filled.get("version", "")),
            ("计划发版日期", filled.get("release_date", "")),
            ("客户场景是否跑通", filled.get("scenario_verified", "")),
            ("发版风险",     filled.get("release_risk", "")),
            ("回滚方案",     filled.get("rollback_plan", "")),
        ]
        title = "**📝 发版审批填写内容（只读）**"
    else:
        return []
    # 过滤掉空值，避免展示无意义的 "—"
    non_empty = [(label, val) for label, val in rows if val]
    if not non_empty:
        return []
    return [_hr(), _div(_md(title))] + [_field_row(label, val) for label, val in non_empty]


def build_approved_confirmed_card(original_schema: dict, card_id: str) -> dict:
    """点通过后原地更新的卡片（变绿，保留原有内容 + 本轮填写字段，按钮变灰）。"""
    req_id = original_schema.get("req_id") or original_schema.get("requirement_id") or "—"
    stage = original_schema.get("stage_label") or "审批"
    four_q = original_schema.get("four_q") or {}
    history = original_schema.get("history") or []
    prev_note = original_schema.get("prev_note") or ""
    prev_role = original_schema.get("prev_role") or ""
    llm_summary = original_schema.get("llm_summary") or ""
    req_title = original_schema.get("req_title") or ""
    customer = original_schema.get("customer") or ""
    filled = original_schema.get("filled_fields") or {}

    elements = [
        _div(_md(f"**需求 {req_id}**　　{req_title}　　客户：{customer or '—'}")),
    ]
    if four_q:
        elements += _four_q_section(four_q)
    if history:
        elements += _timeline_section(history)
    if prev_note:
        elements += [_hr(), _div(_md(f"**💬 上一级备注（{prev_role}）**")), _div(_pt(prev_note))]
    if llm_summary:
        elements += [_hr(), _div(_md("**🤖 历史阶段汇总**")), _div(_pt(llm_summary))]
    # 本轮用户填写的表单字段（Stage2/3/4 各自展示自己的字段）
    elements += _filled_fields_section(stage, filled)
    elements += [
        _hr(),
        _div(_md("**✅ 已确认通过，正在推送给下一位负责人...**")),
    ] + _disabled_approval_form()
    return _base_card_v2(title=f"✅ {stage} | 已通过", template="green", elements=elements)


def build_rejected_confirmed_card(original_schema: dict, card_id: str, reason: str = "") -> dict:
    """点拒绝后原地更新的卡片（变红，保留原有内容 + 本轮填写字段，按钮变灰）。"""
    req_id = original_schema.get("req_id") or original_schema.get("requirement_id") or "—"
    stage = original_schema.get("stage_label") or "审批"
    four_q = original_schema.get("four_q") or {}
    history = original_schema.get("history") or []
    prev_note = original_schema.get("prev_note") or ""
    prev_role = original_schema.get("prev_role") or ""
    llm_summary = original_schema.get("llm_summary") or ""
    req_title = original_schema.get("req_title") or ""
    customer = original_schema.get("customer") or ""
    filled = original_schema.get("filled_fields") or {}
    reason_text = f"原因：{reason}" if reason else "（未填写原因）"

    elements = [
        _div(_md(f"**需求 {req_id}**　　{req_title}　　客户：{customer or '—'}")),
    ]
    if four_q:
        elements += _four_q_section(four_q)
    if history:
        elements += _timeline_section(history)
    if prev_note:
        elements += [_hr(), _div(_md(f"**💬 上一级备注（{prev_role}）**")), _div(_pt(prev_note))]
    if llm_summary:
        elements += [_hr(), _div(_md("**🤖 历史阶段汇总**")), _div(_pt(llm_summary))]
    # 本轮用户填写的表单字段
    elements += _filled_fields_section(stage, filled)
    elements += [
        _hr(),
        _div(_md(f"**❌ 已拒绝　{reason_text}**")),
        _div(_pt("已通知上一级负责人，等待其决定修改或放弃。")),
    ] + _disabled_approval_form()
    return _base_card_v2(title=f"❌ {stage} | 已拒绝", template="red", elements=elements)



def build_stage2_confirm_approved_card(original_schema: dict) -> dict:
    """Stage2 二次确认通过后的只读卡片：保留验收标准 + 测试用例展示，按钮变灰。"""
    req_id = original_schema.get("req_id") or "—"
    structured_criteria = original_schema.get("structured_criteria") or []
    test_cases = original_schema.get("test_cases") or []

    elements = [
        _div(_md(f"**需求 {req_id}**　验收标准已确认，已写入多维表格，研发即将收到通知。")),
        _hr(),
        _div(_md("**📋 已确认的结构化验收标准**")),
    ]
    if structured_criteria:
        for idx, c in enumerate(structured_criteria, 1):
            desc = c.get("description", "")
            metric = c.get("metric", "")
            threshold = c.get("threshold", "")
            method = c.get("measurement_method", "")
            pm_orig = c.get("pm_original", "")
            line = f"**标准 {idx}：{desc}**\n指标：{metric}　门槛：{threshold}\n测量方法：{method}"
            if pm_orig:
                line += f"\n（PM原文：{pm_orig}）"
            elements.append(_div(_md(line)))
    else:
        elements.append(_div(_pt("（无结构化验收标准）")))

    elements += [_hr(), _div(_md("**🧪 已确认的客户场景测试用例**"))]
    if test_cases:
        for idx, tc in enumerate(test_cases, 1):
            actor = tc.get("actor", "")
            precondition = tc.get("precondition", "")
            steps = tc.get("steps", [])
            expected = tc.get("expected_result", "")
            linked_id = tc.get("linked_criterion", "") or tc.get("criterion_id", "")
            linked_num = _seq_num(linked_id) if linked_id else ""
            linked_label = f"→ 标准 {linked_num}" if linked_num else ""
            steps_text = "\n".join(f"  {s}" for s in steps) if steps else "—"
            line = (
                f"**用例 {idx}** {linked_label}\n"
                f"角色：{actor}\n"
                f"前置：{precondition}\n"
                f"步骤：\n{steps_text}\n"
                f"期望结果：{expected}"
            )
            elements.append(_div(_md(line)))
    else:
        elements.append(_div(_pt("（无测试用例）")))

    elements += [
        _hr(),
        _div(_md("**✅ 验收标准已确认，正在通知研发...**")),
        {
            "tag": "button",
            "text": _pt("✅ 已确认"),
            "type": "default",
            "disabled": True,
            "disabled_tips": _pt("已完成操作"),
        },
        {
            "tag": "button",
            "text": _pt("✏️ 修改"),
            "type": "default",
            "disabled": True,
            "disabled_tips": _pt("已完成操作"),
        },
        _hr(),
        _bitable_btn(),
    ]
    return _base_card_v2(
        title=f"✅ Stage2 验收标准已确认 | {req_id}",
        template="green",
        elements=elements,
    )


# ─── Stage 1：售前录入卡片 ─────────────────────────────────

def build_stage1_confirmed_card(card_id: str, req_id: str, next_assignee: str, four_q: dict = None) -> dict:
    """Stage1 提交后原地替换的确认卡片（绿色）。显示四问内容 + 下一位审批人。"""
    elements = [
        _div(_md(f"**需求 {req_id}**　需求已提交，等待审批人确认。")),
        _hr(),
        _div(_md("**✅ 已确认通过，正在推送给下一位负责人...**")),
    ]
    # 始终展示四字段内容（即使 four_q 为 None 也显示占位）
    _q = four_q or {}
    elements += [
        _hr(),
        _div(_md("**📋 您填写的客户场景（只读）**")),
        _field_row("客户是谁",   _q.get("who") or "—"),
        _field_row("使用场景",   _q.get("scene") or "—"),
        _field_row("遇到的问题", _q.get("problem") or "—"),
        _field_row("期望结果",   _q.get("expected") or "—"),
    ]
    elements += [
        _hr(),
        _div(_md(f"**下一位审批人：{next_assignee or '待确认'}**，请等待对方确认。")),
    ]
    return _base_card_v2(
        title="✅ 需求已提交",
        template="green",
        elements=elements,
    )

def _s1_form_elements(card_id: str, p: dict, include_submit: bool = True) -> list:
    """Stage1 四问输入框（含下一位审批人）。required=True 让按钮在全填完后才亮起。"""
    elems = [
        {
            "tag": "input", "name": "s1_who",
            "placeholder": _pt("客户是谁？（角色、公司、具体使用人群）"),
            "width": "fill", "max_length": 300, "required": True,
            "default_value": p.get("s1_who") or p.get("who") or "",
        },
        {
            "tag": "input", "name": "s1_scene",
            "placeholder": _pt("使用场景？（在什么情况下、用什么设备、做什么事）"),
            "width": "fill", "max_length": 400, "required": True,
            "default_value": p.get("s1_scene") or p.get("scene") or "",
        },
        {
            "tag": "input", "name": "s1_problem",
            "placeholder": _pt("遇到的问题？（现在卡在哪里，具体描述）"),
            "width": "fill", "max_length": 500, "required": True,
            "default_value": p.get("s1_problem") or p.get("problem") or "",
        },
        {
            "tag": "input", "name": "s1_expected",
            "placeholder": _pt("期望结果？（做完之后客户期望看到什么变化，可量化最佳）"),
            "width": "fill", "max_length": 500, "required": True,
            "default_value": p.get("s1_expected") or p.get("expected") or "",
        },
        {
            "tag": "input", "name": "s1_customer",
            "placeholder": _pt("客户/公司名称（选填）"),
            "width": "fill", "max_length": 100,
            "default_value": p.get("s1_customer") or "",
        },
        {
            "tag": "input", "name": "next_assignee",
            "placeholder": _pt("下一位审批人飞书姓名（必填）"),
            "width": "fill", "max_length": 50, "required": True,
            "default_value": "",
        },
    ]
    if include_submit:
        elems.append({
            "tag": "button",
            "action_type": "form_submit",
            "name": f"stage1_submit_{card_id}",
            "text": _pt("📤 提交需求"),
            "type": "primary",
            "confirm": {
                "title": _pt("确认提交？"),
                "text": _pt("提交后将发给下一位审批人，不可撤销。"),
            },
        })
    return elems


def build_stage1_input_card(card_id: str, req_id: str, prefill: dict = None, round_num: int = 1) -> dict:
    """售前录入卡片，四问 + 下一位审批人，全部必填后按钮才亮起。"""
    p = prefill or {}
    hint = f"第 {round_num} 轮（最多3轮）" if round_num > 1 else ""
    elements = [
        _div(_md(f"**需求 {req_id}**　请还原客户场景（不做功能翻译）" + (f"　{hint}" if hint else ""))),
        _div(_pt("⚠️ 说明：Stage1 只还原客户实际场景，功能怎么做是PM的事。")),
        _hr(),
        {
            "tag": "form",
            "name": f"stage1_form_{card_id}",
            "elements": _s1_form_elements(card_id, p),
        },
        _hr(),
        _bitable_btn(),
    ]
    return _base_card_v2(title=f"📝 Stage1 需求录入 | {req_id}", template="blue", elements=elements)


def build_stage1_rejected_card(card_id: str, req_id: str, reason: str, prefill: dict = None, round_num: int = 2) -> dict:
    """售前收到拒绝后的修改卡片：展示拒绝原因 + 原内容 + 重新填写。"""
    p = prefill or {}
    elements = [
        _div(_md(f"**需求 {req_id}**　审批被拒绝，请修改后重新提交")),
        _hr(),
        _div(_md("**⚠️ 拒绝原因：**")),
        _div(_pt(reason or "未填写原因")),
        _hr(),
        _div(_md("**📋 上次提交内容（可在下方修改）：**")),
        _field_row("客户是谁",   p.get("s1_who") or p.get("who") or "—"),
        _field_row("使用场景",   p.get("s1_scene") or p.get("scene") or "—"),
        _field_row("遇到的问题", p.get("s1_problem") or p.get("problem") or "—"),
        _field_row("期望结果",   p.get("s1_expected") or p.get("expected") or "—"),
        _hr(),
        {
            "tag": "form",
            "name": f"stage1_retry_form_{card_id}",
            "elements": _s1_form_elements(card_id, p) + [
                {
                    "tag": "button",
                    "action_type": "form_submit",
                    "name": f"abandon_submit_{card_id}",
                    "text": _pt("🚫 放弃此需求"),
                    "type": "danger",
                    "confirm": {"title": _pt("确认放弃？"), "text": _pt("放弃后需求终止。")},
                },
            ],
        },
    ]
    return _base_card_v2(title=f"⚠️ 修改后重新提交 | {req_id}", template="orange", elements=elements)


# ─── 拒绝回执卡片（发给上一级）──────────────────────────────

def _rejection_notice_base(card_id, req_id, rejected_by_role, reason, original_content) -> list:
    elements = [
        _div(_md(f"**需求 {req_id}** 被 {rejected_by_role} 拒绝")),
        _hr(),
        _div(_md("**❌ 拒绝原因：**")),
        _div(_pt(reason or "未填写原因")),
        _hr(),
        _div(_md("**📋 当前需求内容：**")),
    ]
    elements += _four_q_section(original_content)
    return elements


def _retry_form_elements(card_id, original_content, include_escalate=True, include_abandon=False) -> list:
    buttons = [
        {
            "tag": "button", "action_type": "form_submit",
            "name": f"retry_submit_{card_id}",
            "text": _pt("✏️ 修改后重新提交"), "type": "primary",
        },
    ]
    if include_escalate:
        buttons.append({
            "tag": "button", "action_type": "form_submit",
            "name": f"escalate_submit_{card_id}",
            "text": _pt("⬆️ 继续往上退"), "type": "default",
            "confirm": {"title": _pt("确认往上退？"), "text": _pt("将拒绝通知传给上一级，由其决定。")},
        })
    if include_abandon:
        buttons.append({
            "tag": "button", "action_type": "form_submit",
            "name": f"abandon_submit_{card_id}",
            "text": _pt("🚫 放弃此需求"), "type": "danger",
            "confirm": {"title": _pt("确认放弃？"), "text": _pt("放弃后需求终止。")},
        })
    return [{
        "tag": "form", "name": f"retry_form_{card_id}",
        "elements": [
            {"tag": "input", "name": "s1_who",
             "placeholder": _pt("客户是谁？（修改后填写）"),
             "width": "fill", "max_length": 300, "required": True,
             "default_value": original_content.get("who") or ""},
            {"tag": "input", "name": "s1_scene",
             "placeholder": _pt("使用场景？"),
             "width": "fill", "max_length": 400, "required": True,
             "default_value": original_content.get("scene") or ""},
            {"tag": "input", "name": "s1_problem",
             "placeholder": _pt("遇到的问题？"),
             "width": "fill", "max_length": 500, "required": True,
             "default_value": original_content.get("problem") or ""},
            {"tag": "input", "name": "s1_expected",
             "placeholder": _pt("期望结果？"),
             "width": "fill", "max_length": 500, "required": True,
             "default_value": original_content.get("expected") or ""},
            {"tag": "input", "name": "next_assignee",
             "placeholder": _pt("下一位审批人飞书姓名（必填）"),
             "width": "fill", "max_length": 50, "required": True},
        ] + buttons,
    }]


def build_rejection_notice_card(
    card_id: str, req_id: str, rejected_by_role: str,
    reason: str, original_content: dict, is_top_level: bool = False,
) -> dict:
    """
    拒绝回执卡片。
    - 中间级（Stage2/3）：修改重提 + 继续往上退（无放弃）
    - 顶级（售前）：修改重提 + 放弃（无往上退）
    """
    elements = _rejection_notice_base(card_id, req_id, rejected_by_role, reason, original_content)
    elements += [_hr(), _div(_pt("请选择如何处理："))]
    elements += _retry_form_elements(
        card_id, original_content,
        include_escalate=not is_top_level,
        include_abandon=is_top_level,
    )
    elements += [_hr(), _bitable_btn()]
    return _base_card_v2(title=f"⚠️ 需求 {req_id} 被拒绝", template="red", elements=elements)


# ─── Stage 2b：PM二次确认卡片（AI结构化后）─────────────────



def build_stage2_confirm_card(
    card_id: str,
    req_id: str,
    structured_criteria: list,
    test_cases: list,
    next_assignee: str = "",
) -> dict:
    """
    Stage2 第二张卡：测试用例确认卡。
    每条测试用例一个独立多行文本框（AI预填，PM可直接编辑）。
    按钮：「传给下一位负责人」+「回退第一张卡」
    """
    elements = [
        _div(_md(f"**需求 {req_id}**　AI 已生成测试用例，请核对后传给研发")),
        _hr(),
        _div(_md("**📋 验收标准（仅展示）**")),
    ]
    if structured_criteria:
        for idx, c in enumerate(structured_criteria, 1):
            desc = c.get("description", "")
            threshold = c.get("threshold", "")
            method = c.get("measurement_method", "")
            line = f"标准 {idx}：{desc}"
            if threshold:
                line += f"　门槛：{threshold}"
            if method:
                line += f"　测量：{method}"
            elements.append(_div(_md(line)))
    else:
        elements.append(_div(_pt("（暂无结构化验收标准）")))

    elements += [
        _hr(),
        _div(_md("**🧪 客户场景测试用例（可直接编辑）**")),
        _div(_pt("每条用例预填了角色、步骤和期望结果，可直接修改文本后提交。")),
    ]

    form_elements = []
    if test_cases:
        for idx, tc in enumerate(test_cases, 1):
            actor = tc.get("actor", "")
            precondition = tc.get("precondition", "")
            steps = tc.get("steps", [])
            expected = tc.get("expected_result", "")
            steps_text = " → ".join(str(s) for s in steps) if steps else ""
            prefill_text = "角色：" + actor + "\n前置：" + precondition + "\n步骤：" + steps_text + "\n期望：" + expected
            form_elements.append({
                "tag": "input",
                "name": f"test_case_{idx}",
                "label": _pt(f"用例 {idx}"),
                "placeholder": _pt("描述测试角色、步骤和期望结果"),
                "width": "fill",
                "max_length": 800,
                "rows": 4,
                "default_value": prefill_text,
            })
    else:
        form_elements.append({
            "tag": "input",
            "name": "test_case_1",
            "label": _pt("用例 1（AI未能生成，请手动填写）"),
            "placeholder": _pt("描述测试角色、步骤和期望结果"),
            "width": "fill",
            "max_length": 800,
            "rows": 4,
            "default_value": "",
        })

    form_elements += [
        {
            "tag": "input",
            "name": "next_assignee",
            "placeholder": _pt("下一位审批人飞书姓名（传给研发前必填）"),
            "width": "fill",
            "max_length": 50,
            "required": True,
            "default_value": next_assignee,
        },
        {
            "tag": "button",
            "action_type": "form_submit",
            "name": f"s2_confirm_approve_{card_id}",
            "text": _pt("✅ 确认，传给研发"),
            "type": "primary",
            "confirm": {
                "title": _pt("确认传给研发？"),
                "text": _pt("测试用例和验收标准将写入多维表格，并通知研发负责人。"),
            },
        },
        {
            "tag": "button",
            "action_type": "form_submit",
            "name": f"s2_confirm_back_{card_id}",
            "text": _pt("↩️ 回退，重新填写第一步"),
            "type": "default",
        },
    ]

    elements.append({
        "tag": "form",
        "name": f"s2_confirm_form_{card_id}",
        "elements": form_elements,
    })
    elements += [_hr(), _bitable_btn()]

    return _base_card_v2(
        title=f"🔔 Stage2 测试用例确认 | {req_id}",
        template="blue",
        elements=elements,
    )



def build_feedback_design_card(
    card_id: str,
    req_id: str,
    llm_summary: str = "",
    suggested_questions: str = "",
) -> dict:
    """
    Stage5 第一张卡：问卷设计卡（发给售后）。
    LLM历史汇总 + 一个多行文本框（AI预填针对性问题，售后可编辑）。
    """
    elements = [
        _div(_md(f"**需求 {req_id}**　请根据验收标准设计客户反馈问卷")),
        _div(_pt("以下问题由 AI 根据本次版本验收标准自动生成，您可以直接修改文本后提交分发。")),
    ]
    if llm_summary:
        elements += [_hr(), _div(_md("**🤖 历史阶段汇总**")), _div(_pt(llm_summary))]
    elements += [
        _hr(),
        {
            "tag": "form",
            "name": f"feedback_design_form_{card_id}",
            "elements": [
                {
                    "tag": "input",
                    "name": "questionnaire",
                    "label": _pt("📋 问卷内容（可直接编辑，每行一道问题）"),
                    "placeholder": _pt("每行一道问题，支持换行添加更多问题"),
                    "width": "fill",
                    "max_length": 1000,
                    "rows": 4,
                    "default_value": suggested_questions[:1000],
                },
                {
                    "tag": "button",
                    "action_type": "form_submit",
                    "name": f"feedback_design_submit_{card_id}",
                    "text": _pt("✅ 确认问卷，开始分发"),
                    "type": "primary",
                    "confirm": {
                        "title": _pt("确认提交问卷？"),
                        "text": _pt("提交后将进入反馈录入环节，请先完成线下客户访谈。"),
                    },
                },
            ],
        },
        _hr(),
        _bitable_btn(),
    ]
    return _base_card_v2(
        title=f"📋 Stage5 问卷设计 | {req_id}",
        template="blue",
        elements=elements,
    )


def build_feedback_input_card(
    card_id: str,
    req_id: str,
    questions: list,
    llm_summary: str = "",
) -> dict:
    """
    Stage5 第二张卡：反馈录入卡（发给售后）。
    根据第一张卡的问题列表动态生成对应 input 行。
    questions: list of str，每条是一道问题文本。
    """
    elements = [
        _div(_md(f"**需求 {req_id}**　请录入客户反馈结果")),
        _div(_pt("线下客户访谈完成后，逐题录入客户的回答。")),
    ]
    if llm_summary:
        elements += [_hr(), _div(_md("**🤖 历史阶段汇总**")), _div(_pt(llm_summary))]
    elements.append(_hr())

    form_elements = []
    for idx, q in enumerate(questions, 1):
        form_elements.append({
            "tag": "input",
            "name": f"answer_{idx}",
            "label": _pt(q[:100] if q else f"问题 {idx}"),
            "placeholder": _pt("录入客户的实际回答"),
            "width": "fill",
            "max_length": 500,
            "rows": 4,
        })

    # 固定尾部：整体满意度均分
    form_elements += [
        {
            "tag": "input",
            "name": "satisfaction_rate",
            "label": _pt("整体满意度均分"),
            "placeholder": _pt("客户打分（如：8.5 / 10）"),
            "width": "fill",
            "max_length": 20,
        },
        {
            "tag": "button",
            "action_type": "form_submit",
            "name": f"feedback_submit_{card_id}",
            "text": _pt("✅ 提交反馈，触发复盘"),
            "type": "primary",
            "confirm": {
                "title": _pt("确认提交？"),
                "text": _pt("提交后将自动触发复盘分析，不可修改。"),
            },
        },
    ]

    elements.append({
        "tag": "form",
        "name": f"feedback_input_form_{card_id}",
        "elements": form_elements,
    })
    elements += [_hr(), _bitable_btn()]

    return _base_card_v2(
        title=f"📊 Stage5 录入客户反馈 | {req_id}",
        template="blue",
        elements=elements,
    )


def build_retrospective_card(
    card_id: str,
    req_id: str,
    timeline_text: str,
    rejection_summary: str,
    satisfaction: str,
    ai_analysis: str,
) -> dict:
    elements = [
        _div(_md(f"**需求 {req_id} 复盘报告**")),
        _hr(),
        _div(_md("**📅 全程时间线**")),
        _div(_pt(timeline_text or "—")),
        _hr(),
        _div(_md("**🚫 拒绝记录**")),
        _div(_pt(rejection_summary or "无拒绝，全程一次通过")),
        _hr(),
        _div(_md("**⭐ 客户满意度**")),
        _div(_pt(satisfaction or "无数据")),
        _hr(),
        _div(_md("**🤖 AI 分析**")),
        _div(_pt(ai_analysis or "—")),
        _hr(),
        _bitable_btn(),
    ]
    return _base_card_v2(
        title=f"📊 复盘报告 | {req_id}",
        template="purple",
        elements=elements,
    )


# ─── Pipeline 完成卡片 ────────────────────────────────────

def build_pipeline_complete_card(summary: dict, card_id: str) -> dict:
    req_id = summary.get("req_id") or summary.get("version") or "—"
    sat = summary.get("satisfaction_rate") or "—"
    health = summary.get("health_score") or "—"
    roi = summary.get("roi_summary") or "—"

    elements = [
        _div(_md(f"**🏁 需求 {req_id} 全流程完成！**")),
        _hr(),
        _field_row("客户满意度", str(sat)),
        _field_row("流程健康度", str(health)),
        _field_row("ROI结论",   str(roi)),
        _hr(),
        _div(_pt("所有数据已归档至多维表格，点击确认结束。")),
        {
            "tag": "button",
            "text": _pt("✅ 确认归档，结束 Pipeline"),
            "type": "primary",
            "behaviors": [{"type": "callback", "value": {"action_type": "pipeline_done", "card_id": card_id}}],
            "confirm": {
                "title": _pt("确认结束？"),
                "text": _pt("确认后 Pipeline 正式结束，数据已保存。"),
            },
        },
        _hr(),
        _bitable_btn(),
    ]
    return _base_card_v2(
        title=f"🏁 Pipeline 完成 | {req_id}",
        template="green",
        elements=elements,
    )


# ─── Stage 2-4 专属审批卡片 ──────────────────────────────────

def build_stage2_card(card_id: str, req_id: str, req_title: str, customer: str,
                      four_q: dict, history: list, prev_note: str = "",
                      prev_role: str = "", llm_summary: str = "",
                      prefill: dict = None) -> dict:
    """Stage2 产品经理审批卡片：展示区 + 产品专属填写区。
    prefill: AI 预填字段 {"core_value": ..., "acceptance_criteria": ..., "feature_def": ...}
    """
    pf = prefill or {}
    elements = [
        _div(_md(f"**需求 {req_id}**　　{req_title}　　客户：{customer or '—'}")),
    ]
    elements += _four_q_section(four_q)
    elements += _timeline_section(history)
    if prev_note:
        elements += [_hr(), _div(_md(f"**💬 上一级备注（{prev_role}）**")), _div(_pt(prev_note))]
    if llm_summary:
        elements += [_hr(), _div(_md("**🤖 历史阶段汇总**")), _div(_pt(llm_summary))]
    elements += [
        _hr(),
        _div(_md("**📝 产品审批填写区**　　_AI 已根据四问预填，请核对修改后生成测试用例_")),
        {
            "tag": "form",
            "name": f"approve_form_{card_id}",
            "elements": [
                {
                    "tag": "input", "name": "core_value",
                    "placeholder": _pt("核心价值判断：这个需求解决了客户的什么核心问题？（一句话，客户视角，必填）"),
                    "width": "fill", "max_length": 300, "required": True,
                    "default_value": pf.get("core_value", ""),
                },
                {
                    "tag": "input", "name": "acceptance_criteria",
                    "placeholder": _pt("验收标准：做到什么程度算完成？（客户视角，可量化最佳，必填）"),
                    "width": "fill", "max_length": 500, "required": True,
                    "default_value": pf.get("acceptance_criteria", ""),
                },
                {
                    "tag": "input", "name": "feature_def",
                    "placeholder": _pt("功能定义：准备做成什么？（PM完成从客户问题到产品方案的翻译，必填）"),
                    "width": "fill", "max_length": 500, "required": True,
                    "default_value": pf.get("feature_def", ""),
                },
                {
                    "tag": "select_static", "name": "priority",
                    "placeholder": _pt("优先级（必选）"),
                    "required": True,
                    "options": [
                        {"text": {"tag": "plain_text", "content": "SP（极其重要）"}, "value": "SP"},
                        {"text": {"tag": "plain_text", "content": "P0"}, "value": "P0"},
                        {"text": {"tag": "plain_text", "content": "P1"}, "value": "P1"},
                        {"text": {"tag": "plain_text", "content": "P2"}, "value": "P2"},
                    ],
                },
                {
                    "tag": "input", "name": "impact_users",
                    "placeholder": _pt("预计影响用户数（选填）"),
                    "width": "fill", "max_length": 100,
                },
                {
                    "tag": "input", "name": "extra_note",
                    "placeholder": _pt("补充说明（选填）"),
                    "width": "fill", "max_length": 300,
                },
                {
                    "tag": "input", "name": "reject_reason",
                    "placeholder": _pt("退回原因（撤回上一级时必填）"),
                    "width": "fill", "max_length": 300,
                },
                # 注意：这里不填下一位负责人，点「生成测试用例」后会弹出二次确认卡，
                # 在二次确认卡上才填下一位负责人。
                {
                    "tag": "button", "action_type": "form_submit",
                    "name": f"s2_generate_{card_id}",
                    "text": _pt("🔍 生成测试用例"),
                    "type": "primary",
                    "confirm": {"title": _pt("确认提交？"), "text": _pt("提交后 AI 将生成结构化验收标准和测试用例，请等待二次确认。")},
                },
                {
                    "tag": "button", "action_type": "form_submit",
                    "name": f"s2_recall_{card_id}",
                    "text": _pt("↩️ 退回售前补充"),
                    "type": "default",
                    "confirm": {"title": _pt("确认退回？"), "text": _pt("将退回 Stage1，并通知售前补充修改。请先填写退回原因。")},
                },
            ],
        },
    ]
    elements += [_hr(), _bitable_btn()]
    return _base_card_v2(title=f"🔔 Stage2 产品审批 | {req_id}", template="blue", elements=elements)


def build_stage3_card(card_id: str, req_id: str, req_title: str, customer: str,
                      four_q: dict, history: list, prev_note: str = "",
                      prev_role: str = "", llm_summary: str = "") -> dict:
    """Stage3 研发审批卡片：展示区 + 研发专属填写区。"""
    elements = [
        _div(_md(f"**需求 {req_id}**　　{req_title}　　客户：{customer or '—'}")),
    ]
    elements += _four_q_section(four_q)
    elements += _timeline_section(history)
    if prev_note:
        elements += [_hr(), _div(_md(f"**💬 上一级备注（{prev_role}）**")), _div(_pt(prev_note))]
    if llm_summary:
        elements += [_hr(), _div(_md("**🤖 历史阶段汇总**")), _div(_pt(llm_summary))]
    elements += [
        _hr(),
        _div(_md("**📝 研发审批填写区**")),
        {
            "tag": "form",
            "name": f"approve_form_{card_id}",
            "elements": [
                {
                    "tag": "input", "name": "tech_plan",
                    "placeholder": _pt("技术方案简述：准备怎么做？（一句话，必填）"),
                    "width": "fill", "max_length": 300, "required": True,
                },
                {
                    "tag": "input", "name": "workload_days",
                    "placeholder": _pt("工作量评估：X 人天（必填）"),
                    "width": "fill", "max_length": 50, "required": True,
                },
                {
                    "tag": "input", "name": "risks",
                    "placeholder": _pt("技术风险点：依赖项或潜在风险（必填）"),
                    "width": "fill", "max_length": 300, "required": True,
                },
                {
                    "tag": "select_static", "name": "scenario_test",
                    "placeholder": _pt("客户场景自测结论（必选，基于Stage1使用场景验证）"),
                    "required": True,
                    "options": [
                        {"text": _pt("通过"), "value": "通过"},
                        {"text": _pt("部分通过"), "value": "部分通过"},
                        {"text": _pt("未通过"), "value": "未通过"},
                    ],
                },
                {
                    "tag": "input", "name": "test_note",
                    "placeholder": _pt("自测备注（选填）"),
                    "width": "fill", "max_length": 300,
                },
            ] + _outcome_form_elements(card_id=card_id, is_last_stage=False),
        },
    ]
    elements += [_hr(), _bitable_btn()]
    return _base_card_v2(title=f"🔔 Stage3 研发审批 | {req_id}", template="blue", elements=elements)


def build_stage4_card(card_id: str, req_id: str, req_title: str, customer: str,
                      four_q: dict, history: list, prev_note: str = "",
                      prev_role: str = "", llm_summary: str = "") -> dict:
    """Stage4 发版审批卡片：展示区 + 发版专属填写区。最后一关，无需填下一位审批人。"""
    elements = [
        _div(_md(f"**需求 {req_id}**　　{req_title}　　客户：{customer or '—'}")),
    ]
    elements += _four_q_section(four_q)
    elements += _timeline_section(history)
    if prev_note:
        elements += [_hr(), _div(_md(f"**💬 上一级备注（{prev_role}）**")), _div(_pt(prev_note))]
    if llm_summary:
        elements += [_hr(), _div(_md("**🤖 历史阶段汇总**")), _div(_pt(llm_summary))]
    elements += [
        _hr(),
        _div(_md("**📝 发版审批填写区**")),
        _div(_pt("⚠️ 客户场景必须跑通才允许发版。")),
        {
            "tag": "form",
            "name": f"approve_form_{card_id}",
            "elements": [
                {
                    "tag": "input", "name": "release_value",
                    "placeholder": _pt("本版核心价值：客户本次能感知到什么变化？（一句话，必填）"),
                    "width": "fill", "max_length": 300, "required": True,
                },
                {
                    "tag": "input", "name": "version",
                    "placeholder": _pt("版本号，如 v2.5.1（必填）"),
                    "width": "fill", "max_length": 50, "required": True,
                },
                {
                    "tag": "date_picker", "name": "release_date",
                    "placeholder": _pt("计划发版日期（必选）"),
                    "required": True,
                },
                {
                    "tag": "select_static", "name": "scenario_verified",
                    "placeholder": _pt("客户场景是否跑通？（必选，否则不允许发版）"),
                    "required": True,
                    "options": [
                        {"text": _pt("是"), "value": "是"},
                        {"text": _pt("否"), "value": "否"},
                    ],
                },
                {
                    "tag": "select_static", "name": "release_risk",
                    "placeholder": _pt("发版风险（必选）"),
                    "required": True,
                    "options": [
                        {"text": _pt("低"), "value": "低"},
                        {"text": _pt("中"), "value": "中"},
                        {"text": _pt("高"), "value": "高"},
                    ],
                },
                {
                    "tag": "input", "name": "rollback_plan",
                    "placeholder": _pt("回滚方案（选填）"),
                    "width": "fill", "max_length": 300,
                },
            ] + _outcome_form_elements(card_id=card_id, is_last_stage=False),
        },
    ]
    elements += [_hr(), _bitable_btn()]
    return _base_card_v2(title=f"🔔 Stage4 发版审批 | {req_id}", template="blue", elements=elements)
