"""
Demo Script — AI需求管理Pipeline v3

流程：
1. 用户给飞书 Bot 发消息 → 触发 Stage1 录入卡片
2. 售前在卡片逐项填写四问 + 选下一位审批人 → 提交
3. 每级审批人收到含四问+时间线+LLM历史汇总的卡片 → 通过/拒绝
4. 拒绝可逐级回退（C→B→A），回退后重提必须从当前级重新往后走
5. 全程异步，多需求并发互不阻塞

运行：python demo.py
"""
import concurrent.futures
import json
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import DEMO_MODE, BITABLE_URL, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
import pipeline_config_loader as pcfg
from card_handler import (
    start_card_listener,
    get_incoming_message_queue,
    wait_for_card_action,
    register_schema,
    clear_action,
)
from card_templates import (
    build_stage1_input_card,
    build_stage1_rejected_card,
    build_stage2_card,
    build_stage2_confirm_card,
    build_stage3_card,
    build_stage4_card,
    build_rejection_notice_card,
    build_feedback_design_card,
    build_feedback_input_card,
    build_retrospective_card,
    build_pipeline_complete_card,
)
from tools import (
    send_feishu_card,
    send_feishu_message,
    send_feishu_group_message,
    resolve_feishu_user_id,
    write_bitable_record,
    get_bitable_record_fields,
)
from people_map import JACKY_OPEN_ID, PEOPLE_MAP
from openai import OpenAI
from agent_runner import (
    run_agent,
    extract_json_from_response,
    extract_json_from_tool_calls,
    extract_gatekeeping_result,
    extract_value_transform_result,
)
import schema_builder

# ─── 全局 OpenAI 客户端（DeepSeek API，Stage2 AI预填等直接调用 LLM 处使用）─
_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
)

# ─── 授权白名单 ───────────────────────────────────────────
# 允许触发 Pipeline 的飞书 open_id 集合。
# open_id 是 bot 级别隔离的：同一个人在不同 bot 下 open_id 不同！
# 新增授权用户：在 people_map.py 里添加其 open_id，然后加入此 set。
#
# ⚠️ Sleeper-J bot (cli_aa9f3b0f8db91cda) 下 Jacky 的 open_id 待确认：
#    首次运行后查看启动日志里打印的 sender_id，更新 .env.sleeper 的 JACKY_OPEN_ID
AUTHORIZED_SENDERS: set[str] = {
    JACKY_OPEN_ID,                              # 当前环境 .env 里配置的 Jacky open_id
    "ou_5faad2db3966e67e9ee746bc019d313b",      # Jacky (主 OpenClaw/Sleeper bot 下)
    "ou_53dc335c8bc5cd77a631684216a8ed48",      # Jacky (Team Testing bot 下)
    "ou_6b5a125571126eec0737c327c493254e",      # Jacky (原 Sleeper bot 下)
    "ou_c5f5a5e3fe5d37780fa7d5d32edbce4f",      # Jacky（飞书个人用户 / Sleeper-J bot 下）
    *PEOPLE_MAP.values(),
}

# ─── 售后群话 ───────────────────────────────────────────
# Stage4 发版审批通过后，自动向售后群发送反馈收集通知。
# 机器人必须已入该群。实例: config.AFTERSALES_GROUP_CHAT_ID
from config import AFTERSALES_GROUP_CHAT_ID

# ─── Stage 1 对话状态管理 ────────────────────────────────
# key: sender_open_id
# value: {
#   "round": int,           # 当前追问轮次（1-3）
#   "req_id": str,          # 需求ID
#   "history": list[str],   # 每轮用户消息历史
#   "four_q": dict,         # AI整理的四字段 {who, scene, problem, expected}
# }
conversation_state: dict[str, dict] = {}
_conv_state_lock = threading.Lock()

# ─── 工具函数 ─────────────────────────────────────────────

_req_counter = 0
_req_lock = threading.Lock()

def _new_req_id() -> str:
    global _req_counter
    with _req_lock:
        _req_counter += 1
        return f"REQ-{datetime.now().strftime('%Y%m%d')}-{_req_counter:03d}"

def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _now_ms() -> int:
    """飞书 Bitable DateTime 字段需要毫秒时间戳（int）"""
    return int(datetime.now().timestamp() * 1000)

def _search_open_id(name: str) -> str:
    result = resolve_feishu_user_id(name)
    return result.get("open_id") or JACKY_OPEN_ID

def _get_sender_name(open_id: str) -> str:
    """通过 open_id 反查飞书姓名，查不到返回 '售前'。"""
    if DEMO_MODE:
        return "售前（DEMO）"
    try:
        from tools import _get_feishu_token
        from config import FEISHU_BASE_URL
        import requests as _req
        token = _get_feishu_token()
        resp = _req.get(
            f"{FEISHU_BASE_URL}/contact/v3/users/{open_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"user_id_type": "open_id"},
            timeout=5,
        )
        data = resp.json()
        name = data.get("data", {}).get("user", {}).get("name", "")
        return name if name else "售前"
    except Exception as e:
        print(f"[get_sender_name] 失败: {e}")
        return "售前"

# ─── Bitable 字段格式转换 ──────────────────────────────────
# 人员字段：写入格式为 [{"id": "ou_xxx"}]
_PERSON_FIELDS = {
    "当前负责人", "S1_负责人",
    "S2_负责人",
    "S3_负责人",
    "S4_负责人", "S5_负责人",
}
# 日期字段：写入格式为毫秒时间戳(int)，与 init_bitable.py 的 DATE 类型一致
_DATE_FIELDS = {
    "创建时间", "最后更新时间",
    "S1_提交时间",
    "S2_收单时间", "S2_决策时间",
    "S3_收单时间", "S3_决策时间",
    "S4_收单时间", "S4_决策时间", "S4_计划发版日期",
    "S5_分发时间", "S5_反馈提交时间",
    "S6_复盘发送时间",
}
# 数字字段（type=2）：必须写入 int/float，否则飞书 API 报 NumberFieldConvFail 导致整条记录丢失
# 整数数字字段
_INT_FIELDS = {
    "S1_交互轮数", "S1_返工次数",
    "S2_耗时_分钟", "S2_二次确认退回次数", "S2_预计影响用户数", "S2_返工次数",
    "S3_耗时_分钟", "S3_返工次数",
    "S4_耗时_分钟",
    "总拒绝次数",
}
# 浮点数字字段（保留小数）
_FLOAT_FIELDS = {
    "S3_工作量_人天",       # 可能是 0.5人天
    "S5_满意度均分",        # 9.8
    "S5_满意度脚本计算值",   # 与均分相同
}

# 当前阶段单选选项映射（代码里用的旧字符串 → 飞书单选选项名）
_STAGE_MAP = {
    "Stage1录入中":   "Stage1 售前录入",
    "Stage2产品审批": "Stage2 产品审批",
    "Stage3研发审批": "Stage3 研发审批",
    "Stage4发版审批": "Stage4 发版审批",
    "Stage5反馈收集": "Stage5 客户反馈",
    "Stage6复盘":     "Stage6 复盘",
    "已终止":         "已终止",
    "已完成":         "Stage6 复盘",  # 流程结束映射到 Stage6
}

def _coerce_fields(fields: dict, open_id_map: dict | None = None) -> dict:
    """把字段值转成 Bitable 对应类型的写入格式。
    open_id_map: {字段名: open_id}，用于人员字段写入。
    """
    from datetime import datetime as _dt
    result = {}
    for k, v in fields.items():
        if v is None or v == "":
            # 人员字段：即使 fields 里值为空，只要 open_id_map 有就写入
            if k in _PERSON_FIELDS:
                oid = (open_id_map or {}).get(k) if open_id_map else None
                if oid:
                    result[k] = [{"id": oid}]
            continue  # 其他空值跳过，不覆盖

        if k in _PERSON_FIELDS:
            # 人员字段：需要 open_id；open_id_map 优先，没有则用 fields 里的值当 open_id
            oid = ((open_id_map or {}).get(k) if open_id_map else None) or (v if isinstance(v, str) else None)
            if oid:
                result[k] = [{"id": oid}]
            # 没有 open_id 就跳过，不写文本（避免类型错误）
        elif k in _DATE_FIELDS:
            # 日期字段：转毫秒时间戳
            if isinstance(v, (int, float)):
                result[k] = int(v)
            elif isinstance(v, str) and v:
                # date_picker 返回纯数字字符串毫秒时间戳（如 "1747267200000"）
                if v.isdigit():
                    result[k] = int(v)
                else:
                    parsed_ts = None
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %z", "%Y-%m-%d %H:%M %z"):
                        try:
                            parsed_ts = _dt.strptime(v, fmt).timestamp()
                            break
                        except ValueError:
                            continue
                    if parsed_ts is not None:
                        result[k] = int(parsed_ts * 1000)
                    else:
                        print(f"[bitable] 日期字段 {k} 格式无法识别，跳过：{v}")
        elif k in _INT_FIELDS:
            # 整数字段
            try:
                result[k] = int(float(v))
            except (ValueError, TypeError):
                print(f"[bitable] 整数字段 {k} 无法转换，跳过：{v!r}")
        elif k in _FLOAT_FIELDS:
            # 浮点字段（保留小数）
            try:
                result[k] = float(v)
            except (ValueError, TypeError):
                print(f"[bitable] 浮点字段 {k} 无法转换，跳过：{v!r}")
        elif k == "当前阶段":
            result[k] = _STAGE_MAP.get(v, v)  # 映射到正确单选值
        else:
            result[k] = v

    # open_id_map 里有但 fields 里没有的人员字段，直接补写（不依赖 fields 占位）
    if open_id_map:
        for k, oid in open_id_map.items():
            if k in _PERSON_FIELDS and k not in result and oid:
                result[k] = [{"id": oid}]

    return result


def _update_bitable(record_id, fields: dict, open_id_map: dict | None = None):
    """User 字段单独一次 PUT，失败不影响其他字段写入。"""
    if not record_id:
        return
    try:
        coerced = _coerce_fields(fields, open_id_map)
        if not coerced:
            print(f"[bitable] 警告：_coerce_fields 输出为空，跳过写入")
            return

        # 把 Person 字段单独分离，避免其失败导致整条记录丢失
        person_fields = {k: v for k, v in coerced.items() if k in _PERSON_FIELDS}
        other_fields  = {k: v for k, v in coerced.items() if k not in _PERSON_FIELDS}

        # 写入非-Person 字段（这一步必定成功）
        if other_fields:
            result = write_bitable_record(other_fields, record_id=record_id)
            if result and not result.get("ok"):
                print(f"[bitable] ❗️ 写入失败（{len(other_fields)}个字段）: {result.get('error')} | 字段：{list(other_fields.keys())}")
            else:
                print(f"[bitable] ✅ 写入成功：{len(other_fields)}个字段 → {list(other_fields.keys())}")

        # 单独写入 Person 字段，失败只警告不报错
        if person_fields:
            p_result = write_bitable_record(person_fields, record_id=record_id)
            if p_result and not p_result.get("ok"):
                print(f"[bitable] ⚠️ Person字段写入失败（可能 open_id 不在此租户）: {p_result.get('error')} | 字段：{list(person_fields.keys())}")
            else:
                print(f"[bitable] ✅ Person字段写入成功：{list(person_fields.keys())}")

    except Exception as e:
        print(f"[bitable] 写入异常: {e}")


def _get_int_field(record_id: str, field_name: str) -> int:
    if not record_id:
        return 0
    try:
        fields = get_bitable_record_fields(record_id)
        raw = fields.get(field_name, 0)
        if raw in (None, ""):
            return 0
        return int(float(raw))
    except Exception as e:
        print(f"[bitable] 读取字段 {field_name} 失败，按0处理: {e}")
        return 0


def _inc_bitable_counter(record_id: str, field_name: str, step: int = 1):
    current = _get_int_field(record_id, field_name)
    _update_bitable(record_id, {
        field_name: current + step,
        "最后更新时间": _now_ms(),
    })


# ─── LLM 历史汇总 ─────────────────────────────────────────

def _llm_summarize_history(history: list[dict], target_stage_num: int = 0) -> str:
    """把各阶段历史记录拼接成结构化文本（Demo阶段：纯字段拼接，不调 LLM）。

    target_stage_num: 即将进入的阶段编号（2=PM视角, 3=研发视角, 4=发版视角, 5=售后视角, 6=复盘）
    为 0 时输出通用汇总。
    """
    if not history:
        return ""
    lines = []
    for h in history:
        action_cn = {"approve": "通过", "reject": "拒绝"}.get(h.get("action", ""), h.get("action", ""))
        note = h.get("note", "")
        line = f"- Stage{h.get('stage_num','?')} {h.get('role','?')}（{h.get('assignee_name','?')}）{action_cn}"
        if note:
            line += f"，备注：{note}"
        # 附上该阶段的关键实质字段
        detail_parts = []
        sn = h.get("stage_num", 0)
        if sn == 1:
            if h.get("who"):      detail_parts.append(f"客户是谁：{h['who']}")
            if h.get("scene"):    detail_parts.append(f"使用场景：{h['scene']}")
            if h.get("problem"):  detail_parts.append(f"遇到的问题：{h['problem']}")
            if h.get("expected"): detail_parts.append(f"期望结果：{h['expected']}")
        elif sn == 2:
            if h.get("core_value"):       detail_parts.append(f"核心价值：{h['core_value']}")
            if h.get("acceptance_criteria"): detail_parts.append(f"验收标准：{h['acceptance_criteria']}")
            if h.get("feature_def"):      detail_parts.append(f"功能定义：{h['feature_def']}")
            if h.get("priority"):         detail_parts.append(f"优先级：{h['priority']}")
        elif sn == 3:
            if h.get("tech_plan"):        detail_parts.append(f"技术方案：{h['tech_plan']}")
            if h.get("workload_days"):    detail_parts.append(f"工作量：{h['workload_days']}人天")
            if h.get("risks"):            detail_parts.append(f"风险：{h['risks']}")
            if h.get("scenario_test"):    detail_parts.append(f"自测结论：{h['scenario_test']}")
        elif sn == 4:
            if h.get("release_value"):    detail_parts.append(f"发版价值：{h['release_value']}")
            if h.get("version"):          detail_parts.append(f"版本号：{h['version']}")
            if h.get("scenario_verified"): detail_parts.append(f"场景验证：{h['scenario_verified']}")
        elif sn == 5:
            if h.get("satisfaction_rate"): detail_parts.append(f"满意度：{h['satisfaction_rate']}")
            if h.get("feedback_summary"): detail_parts.append(f"反馈摘要：{h['feedback_summary'][:80]}")
        if detail_parts:
            line += "\n  " + "；".join(detail_parts)
        lines.append(line)
    return "\n".join(lines)


# ─── Stage 常量 ───────────────────────────────────────────

STAGES = [
    {
        "num": 2, "label": "Stage2 产品经理审批",
        "bitable_prefix": "S2", "bitable_stage": "Stage2 产品审批",
        "history_labels": {
            "done_before": ["Stage1 售前录入"],
            "current": "Stage2 产品审批",
            "pending_after": ["Stage3 研发审批", "Stage4 发版审批"],
        },
        "is_last": False,
    },
    {
        "num": 3, "label": "Stage3 研发审批",
        "bitable_prefix": "S3", "bitable_stage": "Stage3 研发审批",
        "history_labels": {
            "done_before": ["Stage1 售前录入", "Stage2 产品审批"],
            "current": "Stage3 研发审批",
            "pending_after": ["Stage4 发版审批"],
        },
        "is_last": False,
    },
    {
        "num": 4, "label": "Stage4 发版审批",
        "bitable_prefix": "S4", "bitable_stage": "Stage4 发版审批",
        "history_labels": {
            "done_before": ["Stage1 售前录入", "Stage2 产品审批", "Stage3 研发审批"],
            "current": "Stage4 发版审批",
            "pending_after": [],
        },
        "is_last": True,
    },
]


# ─── Stage 1 对话追问式守门 ─────────────────────────────────

def _stage1_gatekeeper_conversation(
    req_id: str,
    sender_open_id: str,
    trigger_text: str,
    max_rounds: int = 3,
    sender_chat_id: str = "",
) -> tuple[dict, str] | None:
    """
    Stage 1 对话式守门追问。

    逻辑：
    - 使用 conversation_state[sender_open_id] 管理状态
    - 每轮调用守门 Agent 分析当前信息（核心：信息来源是否可追溯到客户）
    - 如信息足够（approved）→ 返回 (AI整理的四字段 dict, requirement_type)
    - 如需追问（info_needed）→ 发追问消息给售前，等待回复，最多3轮
    - 3轮后无论如何整理四字段（用已有信息）
    - 返回 None 表示需求被拒绝或终止

    DEMO_MODE下用 input() 代替飞书消息收发。
    """
    _dest = sender_chat_id or sender_open_id
    _id_type = "chat_id" if sender_chat_id else "open_id"
    def _send_msg(text): return send_feishu_message(_dest, text, _id_type)
    import queue as _queue

    history: list[str] = [trigger_text]
    four_q: dict = {}
    schema1_final = None

    for round_num in range(1, max_rounds + 1):
        # 优化：只传当前轮最新信息 + 先前轮摘要，防止历史全量拼接导致 input 膨胀
        latest_input = history[-1]  # 当前轮用户输入
        if round_num == 1:
            # 第一轮：传入原始需求全文
            combined_text = latest_input
        else:
            # 后续轮：只传增量补充 + 需求一句话摘要
            combined_text = (
                f"原始需求（摘要）：{history[0][:200]}\n\n"
                f"第{round_num}轮补充信息：{latest_input}"
            )

        user_msg = (
            f"请对以下需求进行守门评审（第{round_num}轮，共最多{max_rounds}轮）。\n\n"
            f"核心只判断一件事：这些信息能否追溯到客户原话或客户行为？\n\n"
            f"需求内容：\n{combined_text}\n\n"
            f"rounds: {round_num}\n\n"
            f"请按照守门流程完成评审，输出 Schema 1 JSON。"
        )
        extra_context = {
            "requirement_id": req_id,
            "submitted_by": "售前",
            "submitted_at": _now_str(),
            "rounds": round_num,
        }

        try:
            result = run_agent("01-gatekeeper.md", user_msg, extra_context=extra_context)

            # ── 新路径：从专用工具 submit_gatekeeping_result 取原子字段，脚本组装 Schema 1 ──
            schema1 = None
            raw_gk = extract_gatekeeping_result(result["tool_calls"])
            if raw_gk is not None:
                schema1 = schema_builder.build_schema1(
                    verdict=raw_gk.get("verdict", "info_needed"),
                    customer_who=raw_gk.get("customer_who"),
                    usage_scenario=raw_gk.get("usage_scenario"),
                    problem=raw_gk.get("problem"),
                    expected_outcome=raw_gk.get("expected_outcome"),
                    reject_reason=raw_gk.get("reject_reason"),
                    followup_questions=raw_gk.get("followup_questions", []),
                    requirement_source=raw_gk.get("requirement_source"),
                    requirement_type=raw_gk.get("requirement_type"),
                    source_traceable=raw_gk.get("source_traceable", False),
                    req_id=req_id,
                    original_text=combined_text,
                    submitted_by="售前",
                    rounds=round_num,
                )
                print(f"[{req_id}] ✅ 从 submit_gatekeeping_result 组装 Schema 1")

            # ── 旧路径兜底：Agent 仍输出了 JSON 文本（兼容过渡期）──
            if schema1 is None:
                schema1 = extract_json_from_response(result["text"])
                if schema1 is not None:
                    schema1 = schema_builder.validate_and_repair(schema1)
                    print(f"[{req_id}] ℹ️ 从 text JSON 提取 schema1（旧路径兜底）")

            # ── 最后兜底：从 write_bitable_record tool_calls 提取 ──
            if schema1 is None and result.get("tool_calls"):
                schema1 = extract_json_from_tool_calls(result["tool_calls"])
                if schema1 is not None:
                    schema1 = schema_builder.validate_and_repair(schema1)
                    print(f"[{req_id}] ℹ️ 从 tool_calls write_bitable_record 提取 schema1（最终兜底）")

        except Exception as e:
            print(f"[{req_id}] 守门Agent调用失败（{e}），视为系统异常拒绝")
            schema1 = None

        if schema1 is None:
            # 解析失败不能默认放行——通知售前系统异常，终止本次流转
            print(f"[{req_id}] 守门Agent无法解析结果，系统异常，拒绝放行")
            if DEMO_MODE:
                print(f"  [DEMO] 系统异常：守门 Agent 返回结果无法解析，请重新提交需求。")
            else:
                _send_msg(
                    f"【系统异常】{req_id}\n守门 Agent 返回结果解析失败，请重新提交需求。如多次失败请联系技术支持。",
                )
            return None

        schema1_final = schema1
        gk = schema1.get("gatekeeping", {})
        verdict = gk.get("verdict", "unknown")
        print(f"[{req_id}] Stage1 守门 Round{round_num} verdict={verdict}")

        # 从 schema1 中提取四字段
        four_q = {
            "who":      gk.get("customer_who") or "",
            "scene":    gk.get("usage_scenario") or "",
            "problem":  gk.get("problem") or "",
            "expected": gk.get("expected_outcome") or "",
        }

        if verdict == "approved":
            req_type = schema1.get("requirement_type", "customer_reported")
            print(f"[{req_id}] 守门通过（类型={req_type}），信息来源可追溯")
            return four_q, req_type

        elif verdict == "rejected":
            reject_reason = gk.get("reject_reason") or "需求信息不符合立项要求"
            print(f"[{req_id}] 守门拒绝：{reject_reason}")
            if DEMO_MODE:
                print(f"  [DEMO] 需求 {req_id} 已被守门 Agent 拒绝。原因：{reject_reason}")
            else:
                _send_msg(
                    f"【需求被守门拒绝】{req_id}\n原因：{reject_reason}\n请修改后重新提交。",
                )
            return None

        elif verdict == "info_needed":
            followup_questions = gk.get("followup_questions", [])
            if not followup_questions:
                followup_questions = ["请补充具体的客户场景和需求描述。"]

            if round_num >= max_rounds:
                # 达到最大轮次仍有缺失 → 拒绝，不强行放行
                print(f"[{req_id}] 达到最大轮数{max_rounds}，仍有字段缺失，拒绝")
                if not DEMO_MODE:
                    _send_msg(
                        f"【需求未能通过守门】{req_id}\n"
                        f"多轮补充后仍有信息缺失，本次需求已终止。\n"
                        f"请先与客户确认完整信息后重新提交。",
                    )
                return None

            # Pipeline 统一加编号，去掉 Agent 可能带的序号前缀
            clean_questions = [
                re.sub(r'^\d+[.、。\s]+', '', q).strip()
                for q in followup_questions if q.strip()
            ]
            questions_text = "\n".join(
                f"{i+1}. {q}" for i, q in enumerate(clean_questions)
            )
            print(f"[{req_id}] 守门追问（第{round_num}轮）：\n{questions_text}")

            if DEMO_MODE:
                print(f"\n  [DEMO] 守门 Agent 追问：")
                print(f"{questions_text}")
                supplement = input("  请输入补充信息（直接回车=终止此需求）：").strip()
                if supplement:
                    history.append(supplement)
                else:
                    print(f"[{req_id}] 用户未补充，终止需求")
                    return None
            else:
                _send_msg(
                    f"【需求信息待补充】{req_id}（第{round_num}轮，共{max_rounds}轮）\n"
                    f"以下信息还需要补充：\n{questions_text}\n"
                    f"请直接回复此消息补充信息。",
                )
                msg_q = get_incoming_message_queue()
                followup_msg = msg_q.get()  # 无限等待，直到用户回复
                supplement = followup_msg.get("text", "").strip()
                print(f"[{req_id}] 收到补充信息: {supplement[:80]}")
                if supplement:
                    history.append(supplement)

        else:
            # unknown verdict，记录日志但不放行，要求重新提交
            print(f"[{req_id}] 守门返回未知 verdict={verdict}，终止")
            if not DEMO_MODE:
                _send_msg(
                    f"【系统异常】{req_id}\n守门判断结果异常，请重新提交需求。",
                )
            return None

    # 理论上不会到达这里（max_rounds 循环结束）
    return None


# ─── 单条需求全流程 ───────────────────────────────────────

def run_single_requirement(sender_open_id: str, trigger_text: str, sender_chat_id: str = ""):
    # 局部wrapper：优先用 chat_id 发消息（绕开 open_id cross app 问题）
    _dest = sender_chat_id or JACKY_OPEN_ID
    _id_type = "chat_id" if sender_chat_id else "open_id"
    def _send_card(card_json): return send_feishu_card(_dest, card_json, _id_type)
    def _send_msg(text): return send_feishu_message(_dest, text, _id_type)
    """处理单条需求，全程阻塞，在独立线程中运行。"""

    # ── 检查是否已有进行中的需求（并发控制）────────────────
    with _conv_state_lock:
        if sender_open_id in conversation_state:
            existing_req = conversation_state[sender_open_id].get("req_id", "")
            msg = f"你还有一条需求 {existing_req} 正在录入中，请先完成它再提交新需求。"
            print(f"[main] {sender_open_id} 已有进行中需求 {existing_req}，拒绝新触发")
            if DEMO_MODE:
                print(f"  [DEMO] {msg}")
            else:
                _send_msg(msg)
            return

    req_id = _new_req_id()
    print(f"\n{'='*60}")
    print(f"  [Pipeline] 新需求 {req_id}")
    print(f"  触发: {trigger_text[:60]}")
    print(f"{'='*60}")

    # ── 创建多维表格行 ────────────────────────────────────
    result = write_bitable_record(_coerce_fields({
        "需求ID": req_id,
        "需求标题": trigger_text[:100],
        "当前阶段": "Stage1 售前录入",
        "创建时间": _now_ms(),
        "最后更新时间": _now_ms(),
    }, open_id_map={"当前负责人": JACKY_OPEN_ID}))
    row_id = result.get("record_id")
    if not row_id:
        print(f"[{req_id}] ❌ 创建 bitable 行失败，中止流程: {result.get('error')} code={result.get('code')}")
        return

    # ── Stage 1：对话追问式守门（最多3轮）──────────────────
    # 标记此 sender 正在进行 Stage1
    with _conv_state_lock:
        conversation_state[sender_open_id] = {
            "round": 1,
            "req_id": req_id,
            "history": [trigger_text],
            "four_q": {},
        }

    try:
        print(f"[{req_id}] Stage1 对话式守门开始...")
        gatekeeper_result = _stage1_gatekeeper_conversation(
            req_id=req_id,
            sender_open_id=sender_open_id,
            trigger_text=trigger_text,
            max_rounds=3,
            sender_chat_id=sender_chat_id,
        )
    finally:
        # 读取交互轮数后再清理（conversation_state 在 finally 前赋值）
        _s1_rounds = len(conversation_state.get(sender_open_id, {}).get("history", [trigger_text]))
        with _conv_state_lock:
            conversation_state.pop(sender_open_id, None)

    if gatekeeper_result is None:
        # 守门拒绝
        _update_bitable(row_id, {
            "当前阶段": "已终止",
            "终止原因": "守门Agent拒绝：信息来源不可追溯",
            "最后更新时间": _now_ms(),
        })
        print(f"[{req_id}] 需求已被守门 Agent 终止。")
        return

    four_q, requirement_type = gatekeeper_result

    # 需求类型中文映射（提前定义，卡片和Bitable共用）
    _req_type_names = {
        "customer_reported": "客户需求",
        "internal_improvement": "内部改进",
        "compliance": "合规需求",
        "competitive": "竞品对标",
    }
    _req_type_label = _req_type_names.get(requirement_type, "客户需求")

    # ── Stage 1 确认卡片：发给售前确认AI整理的四字段 ────────
    s1_confirm_id = f"s1c_{req_id}"
    clear_action(s1_confirm_id)

    # 构建确认卡片（展示AI整理结果，提供[确认进入审批]/[修改]）
    from card_templates import _base_card_v2, _md, _pt, _div, _hr, _field_row, _bitable_btn

    s1_confirm_elements = [
        _div(_md(f"**需求 {req_id}**　AI已整理需求信息，请确认后进入审批")),
        _hr(),
        _div(_md("**📋 AI整理的客户场景（请确认无误）**")),
        _field_row("需求类型",   _req_type_label),
        _field_row("客户是谁",   four_q.get("who") or "—"),
        _field_row("使用场景",   four_q.get("scene") or "—"),
        _field_row("遇到的问题", four_q.get("problem") or "—"),
        _field_row("期望结果",   four_q.get("expected") or "—"),
        _hr(),
        _div(_md("**如果信息有误，请在下方修改后再确认。**")),
        {
            "tag": "form",
            "name": f"s1_confirm_form_{s1_confirm_id}",
            "elements": [
                {
                    "tag": "input", "name": "s1_who",
                    "placeholder": _pt("客户是谁（可修改）"),
                    "width": "fill", "max_length": 300,
                    "default_value": four_q.get("who") or "",
                },
                {
                    "tag": "input", "name": "s1_scene",
                    "placeholder": _pt("使用场景（可修改）"),
                    "width": "fill", "max_length": 400,
                    "default_value": four_q.get("scene") or "",
                },
                {
                    "tag": "input", "name": "s1_problem",
                    "placeholder": _pt("遇到的问题（可修改）"),
                    "width": "fill", "max_length": 500,
                    "default_value": four_q.get("problem") or "",
                },
                {
                    "tag": "input", "name": "s1_expected",
                    "placeholder": _pt("期望结果（可修改）"),
                    "width": "fill", "max_length": 500,
                    "default_value": four_q.get("expected") or "",
                },
                {
                    "tag": "input", "name": "s1_customer",
                    "placeholder": _pt("客户/公司名称（选填）"),
                    "width": "fill", "max_length": 100,
                },
                {
                    "tag": "input", "name": "next_assignee",
                    "placeholder": _pt("下一位审批人飞书姓名（必填）"),
                    "width": "fill", "max_length": 50, "required": True,
                },
                {
                    "tag": "button", "action_type": "form_submit",
                    "name": f"s1_confirm_submit_{s1_confirm_id}",
                    "text": _pt("✅ 确认，进入审批"),
                    "type": "primary",
                    "confirm": {
                        "title": _pt("确认提交？"),
                        "text": _pt("提交后将发给产品经理审批，不可撤销。"),
                    },
                },
            ],
        },
        _hr(),
        _bitable_btn(),
    ]
    s1_confirm_card = _base_card_v2(
        title=f"📝 Stage1 确认 | {req_id}",
        template="blue",
        elements=s1_confirm_elements,
    )

    register_schema(s1_confirm_id, {"req_id": req_id, "stage_label": "Stage1 确认"})

    if DEMO_MODE:
        print(f"\n  [DEMO] Stage1 确认卡片（AI整理四字段）：")
        print(f"  客户：{four_q.get('who','—')}")
        print(f"  场景：{four_q.get('scene','—')}")
        print(f"  问题：{four_q.get('problem','—')}")
        print(f"  期望：{four_q.get('expected','—')}")
        next_assignee_input = input("  下一位审批人姓名（直接回车=产品经理）：").strip() or "产品经理"
        s1_override = {}
        override_who = input(f"  修改「客户是谁」（直接回车保留 [{four_q.get('who','')}]）：").strip()
        if override_who:
            s1_override["who"] = override_who
        override_scene = input(f"  修改「使用场景」（直接回车保留）：").strip()
        if override_scene:
            s1_override["scene"] = override_scene
        override_problem = input(f"  修改「遇到的问题」（直接回车保留）：").strip()
        if override_problem:
            s1_override["problem"] = override_problem
        override_expected = input(f"  修改「期望结果」（直接回车保留）：").strip()
        if override_expected:
            s1_override["expected"] = override_expected
        four_q.update(s1_override)
        next_assignee_name = next_assignee_input
        customer = input("  客户/公司名称（选填，直接回车跳过）：").strip()
        s1_confirm_action = {
            "action": "s1_confirm_submit",
            "s1_fields": {
                "s1_who": four_q.get("who", ""),
                "s1_scene": four_q.get("scene", ""),
                "s1_problem": four_q.get("problem", ""),
                "s1_expected": four_q.get("expected", ""),
                "s1_customer": customer,
            },
            "next_assignee": next_assignee_name,
        }
    else:
        _send_card(s1_confirm_card)
        print(f"[{req_id}] Stage1 确认卡片已发，等待售前确认...")
        s1_confirm_action = wait_for_card_action(s1_confirm_id)
        clear_action(s1_confirm_id)

    if s1_confirm_action.get("action") == "abandon":
        _update_bitable(row_id, {"当前阶段": "已终止", "终止原因": "售前放弃", "最后更新时间": _now_ms()})
        return

    # 从确认卡片中读取（可能已修改的）四字段
    confirmed_fields = s1_confirm_action.get("s1_fields", {})
    if confirmed_fields:
        four_q = {
            "who":      confirmed_fields.get("s1_who") or four_q.get("who", ""),
            "scene":    confirmed_fields.get("s1_scene") or four_q.get("scene", ""),
            "problem":  confirmed_fields.get("s1_problem") or four_q.get("problem", ""),
            "expected": confirmed_fields.get("s1_expected") or four_q.get("expected", ""),
        }
    next_assignee_name = (
        s1_confirm_action.get("next_assignee") or
        confirmed_fields.get("next_assignee") or
        "产品经理"
    ).strip()
    customer = confirmed_fields.get("s1_customer", "") if confirmed_fields else ""

    if not next_assignee_name:
        next_assignee_name = "产品经理"

    # 写入 S1 字段 + 状态更新（Stage1通过）
    _next_assignee_open_id = _search_open_id(next_assignee_name)
    _update_bitable(row_id, {
        "需求标题": trigger_text[:200],
        "当前阶段": "Stage2 产品审批",
        "客户名称": customer,
        "S1_客户是谁": four_q.get("who", ""),
        "S1_遇到的问题": four_q.get("problem", ""),
        "S1_使用场景": four_q.get("scene", ""),
        "S1_期望结果": four_q.get("expected", ""),
        "S1_需求类型": _req_type_label,
        "S1_交互轮数": _s1_rounds,
        "S1_提交时间": _now_str(),
        "S1_负责人": sender_open_id,    # open_id, 由 _coerce_fields 转成 Person格式
        "S1_结果": "通过",
        "最后更新时间": _now_ms(),
    }, open_id_map={
        # sender_open_id 来自消息事件，可能不在 Bitable App 租户里
        # 用 JACKY_OPEN_ID 兜底（同一个人，不同 App 的 open_id）
        "S1_负责人": JACKY_OPEN_ID,
    })

    # stage_history：记录每级操作，用于回退 + LLM 汇总
    # 格式：{"stage_num": int, "role": str, "assignee_name": str, "assignee_open_id": str,
    #        "action": "approve"|"reject", "note": str, "time": str}
    sender_name = _get_sender_name(sender_open_id)
    stage_history: list[dict] = [
        {
            "stage_num": 1, "role": "Stage1 售前",
            "assignee_name": sender_name, "assignee_open_id": sender_open_id,
            "action": "approve", "note": "", "time": _now_str(),
            # 把四问内容带进来，让 LLM 汇总有实质内容可读
            "who": four_q.get("who", ""),
            "scene": four_q.get("scene", ""),
            "problem": four_q.get("problem", ""),
            "expected": four_q.get("expected", ""),
            "requirement_type": requirement_type,
        }
    ]

    # ── Stage 2-4：while 循环状态机，支持前进/后退 ─────────
    # current_stage_idx：当前在 STAGES 列表里的索引（0=Stage2, 1=Stage3, 2=Stage4）
    current_stage_idx = 0
    current_assignee_name = next_assignee_name
    # Demo阶段所有角色都是同一个人，直接用 sender_open_id，不靠姓名反查

    while current_stage_idx < len(STAGES):
        stage = STAGES[current_stage_idx]
        sn = stage["num"]
        prefix = stage["bitable_prefix"]

        # 按当前负责人姓名查 open_id；查不到或未填时兜底 JACKY_OPEN_ID
        assignee_open_id = _search_open_id(current_assignee_name) if current_assignee_name else JACKY_OPEN_ID
        recv_time = _now_str()
        stage_start = time.monotonic()

        # 构建进展时间线
        hl = stage["history_labels"]
        history_timeline = (
            [{"label": l, "status": "done"} for l in hl["done_before"]] +
            [{"label": hl["current"], "status": "current"}] +
            [{"label": l, "status": "pending"} for l in hl["pending_after"]]
        )

        # LLM 历史汇总（Task 4）— 在后台线程执行，避免阻塞卡片下发
        llm_summary = ""
        if len(stage_history) >= 1:
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(_llm_summarize_history, stage_history, sn)
                    llm_summary = future.result(timeout=40)
            except Exception:
                llm_summary = "；".join(
                    f"{h.get('role','?')} {'通过' if h.get('action')=='approve' else '拒绝'}"
                    + (f"（{h['note']}）" if h.get("note") else "")
                    for h in stage_history
                )

        # 上一级备注
        prev_entry = stage_history[-1] if stage_history else {}
        prev_note = prev_entry.get("note", "")
        prev_role = prev_entry.get("role", "")

        # ── Stage 2：等PM填写后 AI结构化 + 二次确认 ────────────
        # Stage 2 AI调用已移到卡片提交后（下方 approve 分支中）
        # 此处仅构建卡片摘要文本（Stage 2不再预生成，等PM填完再做）
        if sn == 2:
            pass  # Stage 2 AI结构化在approve分支中处理

        # ── Stage 3：测试用例已在Stage 2由PM确认，此处只展示摘要 ──
        elif sn == 3:
            # 从 stage_history 中取 Stage 2 通过时写入的测试用例摘要
            _s3_s2_entry = next(
                (h for h in reversed(stage_history) if h.get("stage_num") == 2),
                {}
            )
            _s3_test_cases_summary = _s3_s2_entry.get("test_cases_summary", "")
            if _s3_test_cases_summary:
                _s3_ai_note = f"【已确认的客户场景测试用例（来自Stage2 PM确认）】\n{_s3_test_cases_summary}"
                llm_summary = (_s3_ai_note + "\n\n" + llm_summary).strip() if llm_summary else _s3_ai_note

        # ── Stage 4 AI 发版评审预判断 ─────────────────────────
        elif sn == 4:
            _s4_s2_entry = next(
                (h for h in reversed(stage_history) if h.get("stage_num") == 2),
                {}
            )
            _s4_s3_entry = next(
                (h for h in reversed(stage_history) if h.get("stage_num") == 3),
                {}
            )
            try:
                _s4_payload = (
                    f"请对本需求进行发版评审预判断，汇总全链路数据。\n\n"
                    f"需求ID：{req_id}\n"
                    f"客户是谁：{four_q.get('who', '')}\n"
                    f"使用场景：{four_q.get('scene', '')}\n"
                    f"遇到的问题：{four_q.get('problem', '')}\n"
                    f"期望结果：{four_q.get('expected', '')}\n"
                    f"PM审批备注：{_s4_s2_entry.get('note', '')}\n"
                    f"研发审批备注：{_s4_s3_entry.get('note', '')}\n\n"
                    f"请按照发版评审Agent规范输出 Schema 4 JSON（包含 release_verdict、core_value_statement 字段）。"
                )
                _s4_result = run_agent("04-release-review.md", _s4_payload, extra_context={"requirement_id": req_id})
                _s4_ai_output = extract_json_from_response(_s4_result["text"]) or {}
            except Exception as _e:
                print(f"[{req_id}] Stage4 AI分析失败，降级处理: {_e}")
                _s4_ai_output = {}

            # Stage4 LLM汇总已在上面生成，直接使用，不再拼接内部调试信息
            pass

        card_id = f"s{sn}_{req_id}_{int(time.time())}"  # 加时间戳避免回退后 card_id 重复
        clear_action(card_id)
        # 根据阶段选择专属卡片
        _card_builders = {
            3: build_stage3_card,
            4: build_stage4_card,
        }
        # Stage2：AI 预填核心价值/功能定义/验收标准，其余阶段正常构建
        if sn == 2:
            _s2_prefill = {}
            try:
                # 直接调 LLM（不过 Agent tool_use loop），更快更准
                _prefill_prompt = (
                    f"你是产品经理助手。根据以下售前收集的四问信息，帮我预填以下3个字段。\n\n"
                    f"客户是谁：{four_q.get('who', '')}\n"
                    f"使用场景：{four_q.get('scene', '')}\n"
                    f"遇到的问题：{four_q.get('problem', '')}\n"
                    f"期望结果：{four_q.get('expected', '')}\n\n"
                    f'请仅输出一个JSON，不要其他文字：\n'
                    f'{{"core_value": "(一句话总结该需求解决了客户什么核心问题，客户视角)", '
                    f'"acceptance_criteria": "(可量化的验收标准，如\"首次响应时长降至10秒内\")", '
                    f'"feature_def": "(产品方案一句话描述)"}}'
                )
                _prefill_resp = _client.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    max_tokens=512,
                    messages=[{"role": "user", "content": _prefill_prompt}],
                )
                _prefill_text = _prefill_resp.choices[0].message.content or ""
                print(f"[{req_id}] Stage2 prefill LLM raw: {_prefill_text[:200]}")
                _prefill_json = extract_json_from_response(_prefill_text) or {}
                _s2_prefill = {
                    "core_value": _prefill_json.get("core_value", ""),
                    "acceptance_criteria": _prefill_json.get("acceptance_criteria", ""),
                    "feature_def": _prefill_json.get("feature_def", ""),
                }
                print(f"[{req_id}] Stage2 AI预填完成: core_value={_s2_prefill['core_value'][:40]!r}")
            except Exception as _pe:
                import traceback
                print(f"[{req_id}] Stage2 AI预填失败，使用空白卡: {_pe}")
                traceback.print_exc()
            card = build_stage2_card(
                card_id=card_id,
                req_id=req_id,
                req_title=four_q.get("who", "")[:80],
                customer=customer,
                four_q=four_q,
                history=history_timeline,
                prev_note=prev_note,
                prev_role=prev_role,
                llm_summary=llm_summary,
                prefill=_s2_prefill,
            )
        else:
            card_builder = _card_builders.get(sn, build_stage2_card)
            card = card_builder(
                card_id=card_id,
                req_id=req_id,
                req_title=four_q.get("who", "")[:80],
                customer=customer,
                four_q=four_q,
                history=history_timeline,
                prev_note=prev_note,
                prev_role=prev_role,
                llm_summary=llm_summary,
            )
        register_schema(card_id, {
            "req_id": req_id,
            "stage_label": stage["label"],
            "req_title": four_q.get("who", "")[:80],
            "customer": customer,
            "four_q": four_q,
            "history": history_timeline,
            "prev_note": prev_note,
            "prev_role": prev_role,
            "llm_summary": llm_summary,
        })
        send_result = _send_card(card)
        print(f"[{req_id}] send_feishu_card → {send_result}")
        _update_bitable(row_id, {
            f"{prefix}_收单时间": recv_time,
            "当前阶段": stage["bitable_stage"],
            "最后更新时间": _now_ms(),
        }, open_id_map={
            f"{prefix}_负责人": assignee_open_id,
            "当前负责人": assignee_open_id,
        })
        print(f"[{req_id}] {stage['label']} → {current_assignee_name}，等待审批...")

        action = wait_for_card_action(card_id)
        clear_action(card_id)
        elapsed_min = int((time.monotonic() - stage_start) / 60)
        decide_time = _now_str()

        # ── 通过 / 有条件通过 / Stage2生成测试用例 ────────
        _action_name = action.get("action", "")
        if _action_name in ("approve", "approve_with_conditions", "s2_generate", "s2_recall"):
            next_name = (action.get("next_assignee") or "").strip()
            suggestion = action.get("suggestion", "")
            note = action.get("note") or action.get("reason") or suggestion
            is_conditional = (_action_name == "approve_with_conditions")

            # Stage 2：PM点「生成测试用例」→ AI结构化 → 发第二张卡（测试用例确认）
            # PM点「撤回上一级」→ 退回Stage1
            if sn == 2:
                action_name = _action_name

                # ── 撤回上一级 ──
                if action_name == "s2_recall":
                    recall_reason = action.get("reason", "").strip() or "PM认为需求信息不充分，退回售前补充"
                    print(f"[{req_id}] PM撤回，退回Stage1，原因：{recall_reason}")
                    send_feishu_message(sender_chat_id or JACKY_OPEN_ID,
                        f"⚠️ 需求 {req_id} 已由产品退回售前补充。原因：{recall_reason}",
                        "chat_id" if sender_chat_id else "open_id")
                    _update_bitable(row_id, {
                        "当前阶段": "Stage1 售前录入",
                        "S2_结果": "撤回",
                        "S2_拒绝原因": recall_reason,
                        "最后更新时间": _now_ms(),
                    })
                    _inc_bitable_counter(row_id, "S1_返工次数")
                    stage_history.append({
                        "stage_num": 2, "role": "Stage2 产品审批",
                        "assignee_name": current_assignee_name, "assignee_open_id": assignee_open_id,
                        "action": "recall", "note": recall_reason, "time": _now_str(),
                    })

                    # 重发 Stage1 修改卡，保留原 req_id / four_q，让售前补充后继续流程
                    s1_retry_id = f"s1r_{req_id}_{int(time.time())}"
                    clear_action(s1_retry_id)
                    _s1_retry_prefill = {
                        "who": four_q.get("who", ""),
                        "scene": four_q.get("scene", ""),
                        "problem": four_q.get("problem", ""),
                        "expected": four_q.get("expected", ""),
                        "s1_customer": customer,
                    }
                    register_schema(s1_retry_id, {"req_id": req_id, "stage_label": "Stage1 退回修改"})
                    _send_card(build_stage1_rejected_card(
                        card_id=s1_retry_id,
                        req_id=req_id,
                        reason=recall_reason,
                        prefill=_s1_retry_prefill,
                        round_num=2,
                    ))
                    print(f"[{req_id}] Stage1 退回修改卡已发，等待售前补充...")
                    s1_retry_action = wait_for_card_action(s1_retry_id)
                    clear_action(s1_retry_id)

                    if s1_retry_action.get("action") == "abandon":
                        _update_bitable(row_id, {
                            "当前阶段": "已终止",
                            "终止原因": f"Stage2退回后售前放弃: {recall_reason}",
                            "最后更新时间": _now_ms(),
                        })
                        return

                    retry_fields = s1_retry_action.get("s1_fields", {})
                    if retry_fields:
                        four_q = {
                            "who": retry_fields.get("s1_who") or four_q.get("who", ""),
                            "scene": retry_fields.get("s1_scene") or four_q.get("scene", ""),
                            "problem": retry_fields.get("s1_problem") or four_q.get("problem", ""),
                            "expected": retry_fields.get("s1_expected") or four_q.get("expected", ""),
                        }
                        customer = retry_fields.get("s1_customer", customer)

                    next_assignee_name = (s1_retry_action.get("next_assignee") or "产品经理").strip() or "产品经理"
                    _retry_next_oid = _search_open_id(next_assignee_name)
                    _update_bitable(row_id, {
                        "需求标题": trigger_text[:200],
                        "当前阶段": "Stage2 产品审批",
                        "客户名称": customer,
                        "S1_客户是谁": four_q.get("who", ""),
                        "S1_遇到的问题": four_q.get("problem", ""),
                        "S1_使用场景": four_q.get("scene", ""),
                        "S1_期望结果": four_q.get("expected", ""),
                        "S1_提交时间": _now_str(),
                        "S1_结果": "通过",
                        "最后更新时间": _now_ms(),
                    }, open_id_map={
                        "S1_负责人": JACKY_OPEN_ID,
                        "当前负责人": _retry_next_oid,
                    })
                    stage_history.append({
                        "stage_num": 1, "role": "Stage1 售前",
                        "assignee_name": sender_name, "assignee_open_id": sender_open_id,
                        "action": "approve", "note": f"根据Stage2退回补充：{recall_reason}", "time": _now_str(),
                        "who": four_q.get("who", ""),
                        "scene": four_q.get("scene", ""),
                        "problem": four_q.get("problem", ""),
                        "expected": four_q.get("expected", ""),
                    })
                    current_assignee_name = next_assignee_name
                    current_stage_idx = 0
                    continue

                # 从第一张卡取 PM 填写的字段
                pm_acceptance_raw = action.get("acceptance_criteria", "")
                pm_core_value = action.get("core_value", "")
                pm_feature_def = action.get("feature_def", "")
                pm_priority = action.get("priority", "")

                # 兜底：acceptance_criteria 为空时用 core_value + feature_def 拼
                if not pm_acceptance_raw.strip():
                    _fallback_parts = []
                    if pm_core_value.strip():
                        _fallback_parts.append(f"核心价值：{pm_core_value}")
                    if pm_feature_def.strip():
                        _fallback_parts.append(f"功能定义：{pm_feature_def}")
                    if _fallback_parts:
                        pm_acceptance_raw = "\n".join(_fallback_parts)

                # ── 调用 AI 生成结构化验收标准 + 测试用例 ──
                _s2_structured_criteria = []
                _s2_test_cases = []
                try:
                    _s2_payload = (
                        f"请对以下PM填写的验收标准进行结构化，并生成客户场景测试用例。\n\n"
                        f"PM填写的验收标准（原文）：\n{pm_acceptance_raw}\n\n"
                        f"Stage 1 四字段背景：\n"
                        f"  客户是谁：{four_q.get('who', '')}\n"
                        f"  使用场景：{four_q.get('scene', '')}\n"
                        f"  遇到的问题：{four_q.get('problem', '')}\n"
                        f"  期望结果：{four_q.get('expected', '')}\n\n"
                        f"PM核心价值：{pm_core_value}\n"
                        f"PM功能定义：{pm_feature_def}\n"
                        f"PM优先级：{pm_priority}\n\n"
                        f"请输出包含 structured_criteria 和 test_cases 的 JSON。"
                    )
                    _s2_result = run_agent("02-value-transform.md", _s2_payload,
                                           extra_context={"requirement_id": req_id,
                                                          "pm_acceptance_criteria_raw": pm_acceptance_raw,
                                                          "four_q": four_q,
                                                          "pm_core_value": pm_core_value,
                                                          "pm_feature_def": pm_feature_def,
                                                          "pm_priority": pm_priority})
                    # 从 text 优先解析（根治 tool_use 截断），tool_calls 作降级
                    _s2_text = _s2_result.get("text", "")
                    _s2_tool_calls = _s2_result["tool_calls"]
                    print(f"[{req_id}] Stage2 Agent text长度={len(_s2_text)} tool_calls数={len(_s2_tool_calls)}")
                    print(f"[{req_id}] Stage2 Agent text前500字:\n{_s2_text[:500]}")
                    raw_s2 = extract_value_transform_result(
                        _s2_tool_calls,
                        text=_s2_text,
                    )
                    print(f"[{req_id}] Stage2 extract结果: raw_s2={'有' if raw_s2 else '无/None'}")
                    if raw_s2:
                        _s2_structured_criteria = raw_s2.get("structured_criteria", [])
                        _s2_test_cases = raw_s2.get("test_cases", [])
                        print(f"[{req_id}] Stage2 raw_s2 criteria={len(_s2_structured_criteria)} cases={len(_s2_test_cases)}")
                    else:
                        print(f"[{req_id}] Stage2 raw_s2 为 None！检查 Agent 输出是否有 ```json 块")
                    _s2_test_cases = [schema_builder._build_test_case(tc) for tc in _s2_test_cases]
                    _s2_structured_criteria = [schema_builder._build_criterion(c) for c in _s2_structured_criteria]
                    print(f"[{req_id}] Stage2 AI完成：{len(_s2_structured_criteria)}条验收标准，{len(_s2_test_cases)}条测试用例")
                except Exception as _e:
                    import traceback
                    print(f"[{req_id}] Stage2 AI生成失败，降级: {_e}")
                    traceback.print_exc()

                # ── 发第二张卡：测试用例确认卡 ──
                s2_confirm_id = f"s2c_{req_id}_{int(time.time())}"
                clear_action(s2_confirm_id)
                register_schema(s2_confirm_id, {
                    "req_id": req_id,
                    "stage_label": "Stage2 测试用例确认",
                    "structured_criteria": _s2_structured_criteria,
                    "test_cases": _s2_test_cases,
                })
                if DEMO_MODE:
                    print(f"\n  [DEMO] Stage2 测试用例确认卡：")
                    print(f"  验收标准：{len(_s2_structured_criteria)}条，测试用例：{len(_s2_test_cases)}条")
                    _s2_confirm_choice = input("  [0]=确认转研发 [1]=回退第一张卡 (直接回车=0)：").strip()
                    if _s2_confirm_choice == "1":
                        print(f"[{req_id}] PM回退第一张卡，重新循环")
                        continue
                    _s2_confirm_next = input(f"  下一位审批人姓名：").strip()
                    s2_confirm_action = {
                        "action": "s2_confirm_approve",
                        "next_assignee": _s2_confirm_next,
                        **{f"test_case_{i+1}": f"{tc.get('actor','')} → {tc.get('expected_result','')}"
                           for i, tc in enumerate(_s2_test_cases)},
                    }
                else:
                    _s2c_send_result = _send_card(build_stage2_confirm_card(
                        card_id=s2_confirm_id,
                        req_id=req_id,
                        structured_criteria=_s2_structured_criteria,
                        test_cases=_s2_test_cases,
                    ))
                    print(f"[{req_id}] Stage2 测试用例确认卡发送 → open_id={assignee_open_id!r} result={_s2c_send_result}")
                    print(f"[{req_id}] Stage2 测试用例确认卡已发，等待PM确认...")
                    s2_confirm_action = wait_for_card_action(s2_confirm_id)
                    clear_action(s2_confirm_id)

                # ── 回退第一张卡 ──
                if s2_confirm_action.get("action") == "s2_confirm_back":
                    print(f"[{req_id}] PM回退，重发第一张卡")
                    _inc_bitable_counter(row_id, "S2_二次确认退回次数")
                    continue  # while 循环重新发 Stage2 第一张卡

                # ── 确认通过，写入并进 Stage3 ──
                next_name = (s2_confirm_action.get("next_assignee") or "").strip() or "研发负责人"
                # 收集 PM 编辑后的测试用例文本
                _s2_edited_tc_texts = []
                for _i in range(1, len(_s2_test_cases) + 4):
                    _tc_text = s2_confirm_action.get(f"test_case_{_i}", "")
                    if _tc_text:
                        _s2_edited_tc_texts.append(_tc_text)
                _s2_test_cases_summary = "\n".join(
                    f"用例{i+1}：{t}" for i, t in enumerate(_s2_edited_tc_texts)
                ) if _s2_edited_tc_texts else "\n".join(
                    f"[{tc.get('case_id','')}] {tc.get('actor','')} → {tc.get('expected_result','')}"
                    for tc in _s2_test_cases
                )
                _s2_criteria_text = "\n".join(
                    f"[{c.get('criterion_id','')}] {c.get('description','')} 门槛：{c.get('threshold','')} 测量：{c.get('measurement_method','')}"
                    for c in _s2_structured_criteria
                ) if _s2_structured_criteria else pm_acceptance_raw

                _s2_next_oid = _search_open_id(next_name) if next_name else JACKY_OPEN_ID
                _update_bitable(row_id, {
                    f"{prefix}_决策时间": decide_time,
                    f"{prefix}_耗时_分钟": elapsed_min,
                    f"{prefix}_结果": "通过",
                    "S2_核心价值": pm_core_value,
                    "S2_功能定义": pm_feature_def,
                    "S2_优先级": pm_priority,
                    "S2_验收标准原文": pm_acceptance_raw,
                    "S2_结构化验收标准": _s2_criteria_text,
                    "S2_测试用例": _s2_test_cases_summary,
                    "S2_预计影响用户数": action.get("impact_users", ""),
                    "S2_补充说明": action.get("extra_note", ""),
                    "当前阶段": "Stage3 研发审批",
                    "最后更新时间": _now_ms(),
                }, open_id_map={
                    "S2_负责人": assignee_open_id,
                    "当前负责人": _s2_next_oid,
                })
                stage_history.append({
                    "stage_num": sn, "role": stage["label"],
                    "assignee_name": current_assignee_name, "assignee_open_id": assignee_open_id,
                    "action": _action_name, "note": note,
                    "test_cases_summary": _s2_test_cases_summary,
                    "core_value": pm_core_value,
                    "acceptance_criteria": pm_acceptance_raw,
                    "feature_def": pm_feature_def,
                    "priority": pm_priority,
                    "structured_criteria": _s2_structured_criteria,
                    "time": decide_time,
                })
                current_assignee_name = next_name
                current_stage_idx += 1
                continue

            # Stage 3：整体通过/拒绝，不做逐条按钮
            elif sn == 3:
                if not next_name and not stage["is_last"]:
                    send_feishu_message(sender_chat_id or JACKY_OPEN_ID,
                        f"⚠️ 需求 {req_id}：请填写下一位负责人姓名后重新点通过。",
                        "chat_id" if sender_chat_id else "open_id")
                    continue

                print(f"[{req_id}] {stage['label']} 通过，下一位：{next_name}")
                bitable_fields = {
                    f"{prefix}_决策时间": decide_time,
                    f"{prefix}_耗时_分钟": elapsed_min,
                    f"{prefix}_结果": "通过",
                    "S3_技术方案": action.get("tech_plan", ""),
                    "S3_工作量_人天": action.get("workload_days", ""),
                    "S3_风险点": action.get("risks", ""),
                    "S3_客户场景自测结论": action.get("scenario_test", ""),
                    "S3_自测备注": action.get("test_note", ""),
                    "当前阶段": "Stage4发版审批",
                    "最后更新时间": _now_ms(),
                }
                _s3_next_oid = _search_open_id(next_name) if next_name else JACKY_OPEN_ID
                _update_bitable(row_id, bitable_fields, open_id_map={
                    "S3_负责人": assignee_open_id,
                    "当前负责人": _s3_next_oid,
                })
                stage_history.append({
                    "stage_num": sn, "role": stage["label"],
                    "assignee_name": current_assignee_name, "assignee_open_id": assignee_open_id,
                    "action": _action_name, "note": note,
                    # Stage3 关键字段（供历史汇总 LLM 使用）
                    "tech_plan": action.get("tech_plan", ""),
                    "workload_days": action.get("workload_days", ""),
                    "risks": action.get("risks", ""),
                    "scenario_test": action.get("scenario_test", ""),
                    "time": decide_time,
                })
                current_assignee_name = next_name or current_assignee_name
                current_stage_idx += 1
                continue

            # Stage 4 通用处理
            else:
                if not next_name and not stage["is_last"]:
                    send_feishu_message(sender_chat_id or JACKY_OPEN_ID,
                        f"⚠️ 需求 {req_id}：请填写下一位负责人姓名后重新点通过。",
                        "chat_id" if sender_chat_id else "open_id")
                    continue

                print(f"[{req_id}] {stage['label']} 通过，下一位：{next_name}")
                _s4_next_oid = _search_open_id(next_name) if next_name else JACKY_OPEN_ID
                bitable_fields = {
                    f"{prefix}_决策时间": decide_time,
                    f"{prefix}_耗时_分钟": elapsed_min,
                    f"{prefix}_结果": "通过",
                    "最后更新时间": _now_ms(),
                }
                if sn == 4:
                    print(f"[{req_id}] Stage4 表单回传 release_date={action.get('release_date')!r} next_assignee={next_name!r} resolved_open_id={_s4_next_oid!r}")
                    bitable_fields.update({
                        "S4_本版核心价值": action.get("release_value", ""),
                        "S4_版本号": action.get("version", ""),
                        "S4_计划发版日期": action.get("release_date", ""),
                        "S4_客户场景是否跑通": action.get("scenario_verified", ""),
                        "S4_发版风险": action.get("release_risk", ""),
                        "S4_回滚方案": action.get("rollback_plan", ""),
                        "当前阶段": "Stage5 客户反馈",
                    })
                _update_bitable(row_id, bitable_fields, open_id_map={
                    f"{prefix}_负责人": assignee_open_id,
                    "当前负责人": _s4_next_oid,
                })
                stage_history.append({
                    "stage_num": sn, "role": stage["label"],
                    "assignee_name": current_assignee_name, "assignee_open_id": assignee_open_id,
                    "action": _action_name, "note": note,
                    # Stage4 关键字段（供历史汇总 LLM 使用）
                    "release_value": action.get("release_value", ""),
                    "version": action.get("version", ""),
                    "scenario_verified": action.get("scenario_verified", ""),
                    "time": decide_time,
                })

                # Stage4 强制拦截 — 客户场景未跑通不允许发版
                if sn == 4 and action.get("scenario_verified") == "否":
                    print(f"[{req_id}] Stage4 客户场景未跑通，拒绝发版，重新等待")
                    send_feishu_message(sender_chat_id or JACKY_OPEN_ID,
                        f"⚠️ 需求 {req_id}：客户场景未跑通，不允许发版。请跑通后重新提交。",
                        "chat_id" if sender_chat_id else "open_id")
                    continue  # 重发同一张卡片

                # Stage4 通过后：把 next_assignee（售后）记录到 stage_history 供 Stage5 使用
                if sn == 4:
                    # 记录姓名 + 解析后的 open_id，Stage5 必须复用，不再二次搜索
                    stage_history[-1]["next_assignee_name"] = next_name
                    stage_history[-1]["next_assignee_open_id"] = _s4_next_oid
                    print(f"[{req_id}] Stage4 售后负责人：name={next_name!r} open_id={_s4_next_oid!r}")

                current_assignee_name = next_name or current_assignee_name
                current_stage_idx += 1

        # ── 拒绝 ──────────────────────────────────────────
        elif action.get("action") == "reject":
            reason = action.get("reason", "未填写原因")
            print(f"[{req_id}] {stage['label']} 拒绝，原因：{reason}")
            # Stage3 拒绝：状态为"退回PM重评估"
            reject_stage_label = "退回PM重评估" if sn == 3 else "已拒绝"
            _update_bitable(row_id, {
                f"{prefix}_决策时间": decide_time,
                f"{prefix}_耗时_分钟": elapsed_min,
                f"{prefix}_结果": "拒绝",
                f"{prefix}_拒绝原因": reason,
                "当前阶段": reject_stage_label,
                "总拒绝次数": len([h for h in stage_history if h.get("action") == "reject"]) + 1,
                "最后更新时间": _now_ms(),
            })

            # 逐级回退：找上一级
            rej_result = _do_rejection_flow(
                req_id=req_id, row_id=row_id,
                rejected_stage_idx=current_stage_idx,
                rejected_by=current_assignee_name,
                reason=reason, four_q=four_q,
                stage_history=stage_history,
                sender_open_id=sender_open_id,
                sender_chat_id=sender_chat_id,
            )

            if rej_result is None:
                # 放弃或终止
                return
            else:
                # rej_result = (new_stage_idx, new_assignee_name, updated_four_q)
                current_stage_idx, current_assignee_name, four_q = rej_result
                # 更新四问字段（如果上级修改了）
                _update_bitable(row_id, {
                    "S1_客户是谁": four_q.get("who", ""),
                    "S1_使用场景": four_q.get("scene", ""),
                    "S1_遇到的问题": four_q.get("problem", ""),
                    "S1_期望结果": four_q.get("expected", ""),
                    "最后更新时间": _now_ms(),
                })
                # 继续 while 循环，从 current_stage_idx 重新开始

        # ── 延期 ──────────────────────────────────────────
        elif action.get("action") == "defer":
            reason = action.get("note") or action.get("reason") or "未填写延期原因"
            print(f"[{req_id}] {stage['label']} 延期，原因：{reason}")
            _update_bitable(row_id, {
                f"{prefix}_决策时间": decide_time,
                f"{prefix}_耗时_分钟": elapsed_min,
                f"{prefix}_结果": "延期",
                f"{prefix}_拒绝原因": reason,
                "当前阶段": "已延期",
                "最后更新时间": _now_ms(),
            })
            stage_history.append({
                "stage_num": sn, "role": stage["label"],
                "assignee_name": current_assignee_name, "assignee_open_id": assignee_open_id,
                "action": "defer", "note": reason, "time": _now_str(),
            })
            send_feishu_message(sender_chat_id or JACKY_OPEN_ID,
                f"⏸️ 需求 {req_id} 已延期至下一迭代。原因：{reason}",
                "chat_id" if sender_chat_id else "open_id")
            return  # 终止当前流程，等下一迭代重新触发

        # ── 需补充信息 ────────────────────────────────────
        elif action.get("action") == "info_needed":
            reason = action.get("note") or action.get("reason") or "未填写需要哪些补充信息"
            print(f"[{req_id}] {stage['label']} 请求补充信息：{reason}")
            _update_bitable(row_id, {
                f"{prefix}_决策时间": decide_time,
                f"{prefix}_耗时_分钟": elapsed_min,
                f"{prefix}_结果": "需补充信息",
                f"{prefix}_拒绝原因": reason,
                "当前阶段": f"{stage['bitable_stage']}（等待补充信息）",
                "最后更新时间": _now_ms(),
            })
            stage_history.append({
                "stage_num": sn, "role": stage["label"],
                "assignee_name": current_assignee_name, "assignee_open_id": assignee_open_id,
                "action": "info_needed", "note": reason, "time": _now_str(),
            })
            send_feishu_message(sender_chat_id or JACKY_OPEN_ID,
                f"❓ 需求 {req_id} 需要补充信息。\n\n审批人：{current_assignee_name}\n需要补充：{reason}\n请补充后重新提交。",
                "chat_id" if sender_chat_id else "open_id")
            return  # 挂起，等待补充后重新触发

        # ── 转交 ──────────────────────────────────────────
        elif action.get("action") == "delegate":
            delegate_note = action.get("note") or action.get("reason") or ""
            # 从备注中尝试提取转交目标姓名，或从中文字段获取
            delegate_target = (action.get("next_assignee") or "").strip()
            if not delegate_target and delegate_note:
                delegate_target = delegate_note.strip()
            if not delegate_target:
                print(f"[{req_id}] 转交但未指定目标，跳过")
                continue
            _delegate_oid = _search_open_id(delegate_target)
            print(f"[{req_id}] {stage['label']} 由 {current_assignee_name} 转交至 {delegate_target}")
            _update_bitable(row_id, {
                f"{prefix}_决策时间": decide_time,
                f"{prefix}_耗时_分钟": elapsed_min,
                f"{prefix}_结果": "已转交",
                f"{prefix}_拒绝原因": f"转交至 {delegate_target}",
                "当前阶段": stage["bitable_stage"],
                f"{prefix}_负责人": _delegate_oid,
                "最后更新时间": _now_ms(),
            }, open_id_map={f"{prefix}_负责人": _delegate_oid})
            stage_history.append({
                "stage_num": sn, "role": stage["label"],
                "assignee_name": current_assignee_name, "assignee_open_id": assignee_open_id,
                "action": "delegate", "note": f"转交至 {delegate_target}", "time": _now_str(),
            })
            # 更新当前审批人，重新发卡
            current_assignee_name = delegate_target
            assignee_open_id = _delegate_oid
            # 不 advance，继续当前阶段循环（会重新发卡给新审批人）

        # 未知操作（不应该发生）
        else:
            print(f"[{req_id}] {stage['label']} 未知操作={action.get('action')}，跳过")

    # ── Stage 5：售后反馈问卷（异步）─────────────────────
    _latest_stage4_approved = next(
        (
            h for h in reversed(stage_history)
            if h.get("stage_num") == 4 and h.get("action") == "approve"
        ),
        None,
    )
    if not _latest_stage4_approved:
        print(f"[{req_id}] 未完成 Stage4 通过，不进入 Stage5")
        return

    # Stage5 进入时生成一次历史阶段汇总（售后视角，target_stage_num=5）
    _s5_llm_summary = ""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex5:
            _f5 = _ex5.submit(_llm_summarize_history, stage_history, 5)
            _s5_llm_summary = _f5.result(timeout=40)
    except Exception:
        pass

    # Stage 5：从 Stage2 验收标准生成问卷题目（直接用自然语言，不经过 ID 映射）
    _s5_s2_entry = next((h for h in stage_history if h.get("stage_num") == 2), {})
    _s5_structured_criteria = _s5_s2_entry.get("structured_criteria", [])

    # 生成问卷文本：每条验收标准生成一道问题，无序号前缀，最后加满意度题
    _s5_questions: list[str] = []
    for c in _s5_structured_criteria:
        desc = c.get("description", "").strip()
        threshold = c.get("threshold", "").strip()
        if desc:
            q = desc
            if threshold:
                q += f"（期望：{threshold}）"
            _s5_questions.append(q)
    if not _s5_questions:
        # 降级：用四问的期望结果生成一道通用问题
        expected = four_q.get("expected", "")
        if expected:
            _s5_questions.append(f"「{expected}」是否已解决您的问题？")
        else:
            _s5_questions.append("本次版本是否解决了您遇到的问题？")
    # 固定尾部：满意度打分（不加序号）
    _s5_questions.append("请对本次版本的整体满意度打分（1-10分）")

    # 把题目列表拼成文本框预填内容（换行分隔，无前缀）
    _s5_suggested_questions = "\n".join(_s5_questions)

    # ── 发第一张卡：问卷设计卡（发给售后）──
    _s5_s4_entry = next((h for h in reversed(stage_history) if h.get("stage_num") == 4), {})
    _s5_next_name = _s5_s4_entry.get("next_assignee_name", "")
    _s5_next_oid = _s5_s4_entry.get("next_assignee_open_id") or (_search_open_id(_s5_next_name) if _s5_next_name else JACKY_OPEN_ID)
    print(f"[{req_id}] Stage5 收件人：name={_s5_next_name!r} open_id={_s5_next_oid!r}")
    s5_design_id = f"s5d_{req_id}"
    clear_action(s5_design_id)
    register_schema(s5_design_id, {
        "req_id": req_id,
        "stage_label": "Stage5 问卷设计",
        "questions": _s5_questions,
    })
    _s5_design_send_result = send_feishu_card(_s5_next_oid, build_feedback_design_card(
        card_id=s5_design_id,
        req_id=req_id,
        llm_summary=_s5_llm_summary,
        suggested_questions=_s5_suggested_questions,
    ), "open_id")
    print(f"[{req_id}] Stage5 问卷设计卡发送结果 → {_s5_design_send_result}")
    if not _s5_design_send_result.get("ok"):
        _update_bitable(row_id, {
            "当前阶段": "已终止",
            "终止原因": f"Stage5问卷设计卡发送失败: {_s5_design_send_result.get('error', 'unknown')}",
            "最后更新时间": _now_ms(),
        }, open_id_map={"S5_负责人": _s5_next_oid})
        print(f"[{req_id}] ❌ Stage5 问卷设计卡发送失败，流程终止")
        return
    _update_bitable(row_id, {
        "当前阶段": "Stage5 客户反馈",
        "最后更新时间": _now_ms(),
    }, open_id_map={"S5_负责人": _s5_next_oid})
    print(f"[{req_id}] Stage5 问卷设计卡已发给售后，等待确认...")

    s5d_action = wait_for_card_action(s5_design_id)
    clear_action(s5_design_id)

    # 取售后确认/编辑后的问卷文本，解析成题目列表
    _s5_final_questionnaire_text = s5d_action.get("questionnaire", _s5_suggested_questions).strip()
    # 按换行拆成题目列表（去空行）
    _s5_final_questions = [q.strip() for q in _s5_final_questionnaire_text.splitlines() if q.strip()]
    if not _s5_final_questions:
        _s5_final_questions = _s5_questions  # 降级

    _update_bitable(row_id, {
        "S5_问卷内容": _s5_final_questionnaire_text,
        "S5_分发时间": _now_str(),
        "S5_结果": "问卷已确认",
        "最后更新时间": _now_ms(),
    })

    # ── 发第二张卡：反馈录入卡（每题一个 input 行）──
    s5_input_id = f"s5i_{req_id}"
    clear_action(s5_input_id)
    register_schema(s5_input_id, {
        "req_id": req_id,
        "stage_label": "Stage5 反馈录入",
        "questions": _s5_final_questions,
    })
    _s5_input_send_result = send_feishu_card(_s5_next_oid, build_feedback_input_card(
        card_id=s5_input_id,
        req_id=req_id,
        questions=_s5_final_questions,
        llm_summary=_s5_llm_summary,
    ), "open_id")
    print(f"[{req_id}] Stage5 反馈录入卡发送结果 → {_s5_input_send_result}")
    if not _s5_input_send_result.get("ok"):
        _update_bitable(row_id, {
            "当前阶段": "已终止",
            "终止原因": f"Stage5反馈录入卡发送失败: {_s5_input_send_result.get('error', 'unknown')}",
            "最后更新时间": _now_ms(),
        }, open_id_map={"S5_负责人": _s5_next_oid})
        print(f"[{req_id}] ❌ Stage5 反馈录入卡发送失败，流程终止")
        return
    print(f"[{req_id}] Stage5 反馈录入卡已发，等待售后录入客户反馈...")

    s5i_action = wait_for_card_action(s5_input_id)
    clear_action(s5_input_id)

    # 收集每道题的答案，拼成反馈摘要
    _s5_answers = []
    for _qi, _q in enumerate(_s5_final_questions, 1):
        _ans = s5i_action.get(f"answer_{_qi}", "").strip()
        if _ans:
            _s5_answers.append("Q：" + _q + "\nA：" + _ans)
    satisfaction = s5i_action.get("satisfaction_rate", "")
    fb_summary = "\n\n".join(_s5_answers) if _s5_answers else ""

    _update_bitable(row_id, {
        "S5_反馈提交时间": _now_str(),
        "S5_满意度均分": satisfaction,
        "S5_满意度脚本计算值": satisfaction,
        "S5_反馈摘要": fb_summary,
        "S5_结果": "反馈已录入",
        "当前阶段": "Stage5 客户反馈",
        "最后更新时间": _now_ms(),
    })
    _s5_history_entry = {
        "stage_num": 5, "role": "Stage5 售后反馈",
        "assignee_name": "售后", "assignee_open_id": _s5_next_oid,
        "action": "approve", "note": "",
        "satisfaction_rate": satisfaction,
        "feedback_summary": fb_summary,
        "time": _now_str(),
    }
    stage_history.append(_s5_history_entry)

    # ── Stage 5 AI 分析：反馈收集Agent（阶段2：仅AI分析，不做问卷生成）──
    _s5_ai_result = {}
    try:
        _s5_customer_name = four_q.get("who", customer or "")
        _s5_payload = (
            f"反馈数据已收集完毕，请运行AI分析（阶段2），输出 Schema 5 JSON。\n\n"
            f"需求ID：{req_id}\n"
            f"客户：{customer}\n"
            f"客户角色：{_s5_customer_name}\n"
            f"使用场景：{four_q.get('scene', '')}\n"
            f"遇到的问题：{four_q.get('problem', '')}\n"
            f"期望结果：{four_q.get('expected', '')}\n"
            f"客户满意度评分：{satisfaction or '无数据'}\n"
            f"反馈原文：\n{fb_summary}\n\n"
            f"⚠️ 注意：你只需要执行阶段2（AI分析反馈），不要执行阶段1（生成问卷）。"
            f"请在 text 输出中用 ```json 代码块输出 Schema 5 JSON，"
            f"包含 ai_analysis 和 presentation_summary 字段。"
        )
        _s5_result = run_agent("05-feedback-collect.md", _s5_payload,
                               extra_context={"requirement_id": req_id,
                                              "customer": customer,
                                              "satisfaction": satisfaction,
                                              "feedback_summary": fb_summary,
                                              "stage_history": stage_history})
        _s5_ai_output = extract_json_from_response(_s5_result["text"]) or {}
        print(f"[{req_id}] Stage5 AI分析完成: satisfaction_rate={_s5_ai_output.get('ai_analysis', {}).get('satisfaction_rate', 'N/A')}")
    except Exception as _e:
        print(f"[{req_id}] Stage5 AI分析失败，降级: {_e}")
        _s5_ai_output = {}

    # 提取 AI 分析结果用于后续 Stage6
    _s5_presentation = _s5_ai_output.get("presentation_summary", "")
    _s5_key_finding = (_s5_ai_output.get("ai_analysis", {}) or {}).get("key_finding", "")

    # ── Stage 6：复盘 ────────────────────────────────────
    _update_bitable(row_id, {"当前阶段": "Stage6复盘", "最后更新时间": _now_ms()})
    all_roles = [h.get("assignee_name", "") for h in stage_history]
    rejection_count = len([h for h in stage_history if h.get("action") == "reject"])
    timeline = " → ".join([f"Stage{h['stage_num']}({h['assignee_name']})" for h in stage_history])

    # Stage 6 AI：用复盘 Agent 替代 _llm_summarize_history，生成结构化复盘报告
    try:
        _s6_full_pipeline_data = {
            "requirement_id": req_id,
            "four_q": four_q,
            "customer": customer,
            "stage_history": stage_history,
            "timeline": timeline,
            "rejection_count": rejection_count,
            "satisfaction": satisfaction or "无数据",
            "feedback_summary": fb_summary or "",
            "s5_ai_analysis": _s5_ai_output.get("ai_analysis", {}),
            "s5_presentation_summary": _s5_presentation,
        }
        _s6_payload = (
            f"请对以下需求的全流程数据进行复盘分析，输出 Schema 6 JSON。\n\n"
            f"需求ID：{req_id}\n"
            f"完整时间线：{timeline}\n"
            f"拒绝次数：{rejection_count}\n"
            f"客户满意度：{satisfaction or '无数据'}\n"
            f"客户反馈摘要：{fb_summary or '无'}\n\n"
            f"各阶段历史记录：\n"
            + "\n".join(
                f"  Stage{h['stage_num']} {h['role']}（{h['assignee_name']}）"
                f"{'通过' if h.get('action')=='approve' else '拒绝'}"
                + (f"，备注：{h['note']}" if h.get('note') else "")
                for h in stage_history
            )
            + f"\n\n请按照复盘分析Agent规范输出 Schema 6 JSON，"
              f"包含 roi_verdict、next_version_suggestions、improvement_actions、process_retrospective 等字段。"
        )
        _s6_result = run_agent("06-retrospective.md", _s6_payload, extra_context=_s6_full_pipeline_data)
        _s6_ai_output = extract_json_from_response(_s6_result["text"]) or {}
    except Exception as _e:
        print(f"[{req_id}] Stage6 AI复盘失败，降级处理: {_e}")
        _s6_ai_output = {}

    # 从 Schema 6 提取关键字段用于复盘卡片
    _s6_roi = _s6_ai_output.get("roi_verdict", {})
    _s6_roi_summary = _s6_roi.get("summary", "") if isinstance(_s6_roi, dict) else str(_s6_roi)
    _s6_health = _s6_ai_output.get("process_retrospective", {})
    # process_health_score 由脚本计算，不信任 AI 算数
    _s6_improvements = _s6_ai_output.get("improvement_actions", [])
    _s6_health_score = schema_builder.calc_health_score(len(_s6_improvements))
    _s6_next_suggestions = _s6_ai_output.get("next_version_suggestions", [])

    # 组装 ai_analysis 文本（用于复盘卡片展示）
    _s6_analysis_parts = []
    if _s6_roi_summary:
        _s6_analysis_parts.append(f"ROI结论：{_s6_roi_summary}")
    if _s6_health_score:
        _s6_analysis_parts.append(f"流程健康度：{_s6_health_score}")
    if _s6_next_suggestions:
        _s6_sug_text = "；".join(
            s.get("description", "") for s in _s6_next_suggestions[:3] if isinstance(s, dict)
        )
        if _s6_sug_text:
            _s6_analysis_parts.append(f"下版本建议：{_s6_sug_text}")
    if _s6_improvements:
        _s6_imp_text = "；".join(
            a.get("description", "") for a in _s6_improvements[:3] if isinstance(a, dict)
        )
        if _s6_imp_text:
            _s6_analysis_parts.append(f"流程改进项：{_s6_imp_text}")

    # 降级：若 AI 复盘无实质输出，回退到原 _llm_summarize_history
    if _s6_analysis_parts:
        ai_analysis = "\n".join(_s6_analysis_parts)
    else:
        ai_analysis = _llm_summarize_history(stage_history) or "全流程完成"

    retro_card_id = f"retro_{req_id}"
    retro_send_result = _send_card(build_retrospective_card(
        card_id=retro_card_id, req_id=req_id,
        timeline_text=timeline,
        rejection_summary=f"共拒绝 {rejection_count} 次" if rejection_count else "无拒绝，全程一次通过",
        satisfaction=satisfaction or "无数据",
        ai_analysis=ai_analysis,
    ))
    print(f"[{req_id}] Stage6 复盘卡片 → {retro_send_result}")
    retro_text = (
        f"时间线：{timeline}\n拒绝次数：{rejection_count}\n"
        f"客户满意度：{satisfaction}\n反馈：{fb_summary}\n"
        + (f"ROI结论：{_s6_roi_summary}\n" if _s6_roi_summary else "")
        + (f"流程健康度：{_s6_health_score}\n" if _s6_health_score else "")
    )
    _update_bitable(row_id, {
        "当前阶段": "已完成",
        "总拒绝次数": rejection_count,
        "S6_复盘报告": retro_text,
        "S6_复盘发送时间": _now_str(),
        "S6_ROI结论": _s6_roi_summary,
        "S6_流程健康度": _s6_health_score,
        "最后更新时间": _now_ms(),
    })
    print(f"\n[{req_id}] ✅ 全流程完成！")


# ─── 逐级回退流程 ─────────────────────────────────────────

def _do_rejection_flow(
    req_id, row_id, rejected_stage_idx, rejected_by,
    reason, four_q, stage_history, sender_open_id,
    sender_chat_id: str = "",
) -> tuple | None:
    """
    处理拒绝后的逐级回退。
    返回 (new_stage_idx, new_assignee_name, four_q) 表示从哪一级重新开始；
    返回 None 表示放弃/终止。

    逐级回退规则：
    - 找上一级 history 里的 assignee_open_id
    - 发回执卡片（修改重提 / 继续往上退 / 放弃）
    - 选修改重提 → 从当前 rejected_stage_idx 重新开始（不跳级）
    - 选继续往上退 → 递归往上一级
    - 选放弃 → 返回 None
    """
    _dest = sender_chat_id or sender_open_id
    _id_type = "chat_id" if sender_chat_id else "open_id"
    def _send_card(card_json): return send_feishu_card(_dest, card_json, _id_type)
    def _send_msg(text): return send_feishu_message(_dest, text, _id_type)
    # 找上一级：从 stage_history 倒序找 stage_num < 当前 stage
    current_stage_num = STAGES[rejected_stage_idx]["num"]
    upper_entry = None
    for h in reversed(stage_history):
        if h["stage_num"] < current_stage_num:
            upper_entry = h
            break

    if upper_entry is None:
        # 已经到顶了（售前级），无法再往上退 → 直接提示放弃
        send_feishu_message(sender_chat_id or JACKY_OPEN_ID,
            f"⚠️ 需求 {req_id} 被拒绝（{reason}），已无上级可退，需求终止。",
            "chat_id" if sender_chat_id else "open_id")
        _update_bitable(row_id, {"当前阶段": "已终止", "终止原因": f"逐级回退至顶后放弃: {reason}", "最后更新时间": _now_ms()})
        return None

    upper_open_id = upper_entry["assignee_open_id"]
    upper_name = upper_entry["assignee_name"]
    upper_stage_num = upper_entry["stage_num"]

    # 找到上一级对应的 stage_idx（用于修改重提后从哪里开始）
    # 修改重提：从 rejected_stage_idx 重新开始（不是从上一级开始）
    # 继续往上退：再往上一层

    notice_card_id = f"notice_{current_stage_num}_{req_id}_{int(time.time())}"
    clear_action(notice_card_id)
    is_top = (upper_stage_num <= 1)  # Stage1=售前顶层，只能修改或放弃
    notice_card = build_rejection_notice_card(
        card_id=notice_card_id,
        req_id=req_id,
        rejected_by_role=f"Stage{current_stage_num}（{rejected_by}）",
        reason=reason,
        original_content=four_q,
        is_top_level=is_top,
    )
    register_schema(notice_card_id, {"req_id": req_id, "stage_label": f"拒绝回执→{upper_name}"})
    _send_card(notice_card)
    print(f"[{req_id}] 拒绝回执已发给 {upper_name}（Stage{upper_stage_num}），等待决定...")

    notice_action = wait_for_card_action(notice_card_id)
    clear_action(notice_card_id)
    act = notice_action.get("action", "")

    if act == "abandon":
        _update_bitable(row_id, {
            "当前阶段": "已终止",
            "终止原因": f"Stage{current_stage_num}拒绝后{upper_name}放弃: {reason}",
            "最后更新时间": _now_ms(),
        })
        return None

    elif act == "escalate":
        # 继续往上退：以 upper_entry 所在的 stage 为新的 rejected_stage
        # 找 upper_stage_idx
        upper_stage_idx = next(
            (i for i, s in enumerate(STAGES) if s["num"] == upper_stage_num),
            None
        )
        if upper_stage_idx is None or upper_stage_idx == 0:
            # 上一级是 Stage1（售前），继续往上退等于到顶
            send_feishu_message(sender_chat_id or JACKY_OPEN_ID,
                f"⚠️ 需求 {req_id} 逐级回退至售前，售前请决定是否放弃或重新提交。",
                "chat_id" if sender_chat_id else "open_id")
            # 再发一次 stage1 拒绝卡片给售前
            s1_notice_id = f"s1_rej_{req_id}_{int(time.time())}"
            clear_action(s1_notice_id)
            _send_card(build_rejection_notice_card(
                card_id=s1_notice_id, req_id=req_id,
                rejected_by_role=f"逐级回退至顶（最后一次拒绝来自Stage{current_stage_num}）",
                reason=reason, original_content=four_q,
                is_top_level=True,
            ))
            register_schema(s1_notice_id, {"req_id": req_id, "stage_label": "售前最终决定"})
            s1_final = wait_for_card_action(s1_notice_id)
            clear_action(s1_notice_id)
            if s1_final.get("action") == "retry_submit":
                new_fields = s1_final.get("s1_fields", {})
                new_assignee = s1_final.get("next_assignee", "").strip()
                if new_fields:
                    four_q = {
                        "who":      new_fields.get("s1_who", four_q.get("who", "")),
                        "scene":    new_fields.get("s1_scene", four_q.get("scene", "")),
                        "problem":  new_fields.get("s1_problem", four_q.get("problem", "")),
                        "expected": new_fields.get("s1_expected", four_q.get("expected", "")),
                    }
                return (0, new_assignee or "产品经理", four_q)
            else:
                _update_bitable(row_id, {"当前阶段": "已终止", "终止原因": "售前最终放弃", "最后更新时间": _now_ms()})
                return None
        else:
            # 递归往上退
            return _do_rejection_flow(
                req_id=req_id, row_id=row_id,
                rejected_stage_idx=upper_stage_idx,
                rejected_by=upper_name,
                reason=reason, four_q=four_q,
                stage_history=stage_history,
                sender_open_id=sender_open_id,
                sender_chat_id=sender_chat_id,
            )

    elif act == "retry_submit":
        # 修改后重新提交：从 rejected_stage_idx 重新开始（不跳级）
        new_fields = notice_action.get("s1_fields", {})
        new_assignee = notice_action.get("next_assignee", "").strip()
        if new_fields:
            four_q = {
                "who":      new_fields.get("s1_who", four_q.get("who", "")),
                "scene":    new_fields.get("s1_scene", four_q.get("scene", "")),
                "problem":  new_fields.get("s1_problem", four_q.get("problem", "")),
                "expected": new_fields.get("s1_expected", four_q.get("expected", "")),
            }
        # 跨阶段返工计数：被退回重做的是“当前将重新开始的阶段”
        _rework_map = {1: "S2_返工次数", 2: "S3_返工次数"}
        _rework_field = _rework_map.get(rejected_stage_idx)
        if _rework_field:
            _inc_bitable_counter(row_id, _rework_field)
        return (rejected_stage_idx, new_assignee or rejected_by, four_q)

    else:
        # 超时/未知 → 终止
        _update_bitable(row_id, {"当前阶段": "已终止", "终止原因": "拒绝后无响应", "最后更新时间": _now_ms()})
        return None



# ─── 主函数 ──────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  AI需求管理Pipeline v3")
    print(f"  多维表格：{BITABLE_URL}")
    print("=" * 60)
    print()
    print("  💬 给 Bot 发消息即触发 Stage1 录入卡片")
    print("  🔄 多需求并发，互不阻塞")
    print("  Ctrl+C 退出")
    print()

    # DEMO_MODE：无需飞书凭证，自动顺序运行示例需求后退出
    if DEMO_MODE:
        print("[DEMO] 无需飞书账号，自动运行3条示例需求")
        start_card_listener()  # no-op in DEMO_MODE
        demo_cases = [
            "展厅管理人员反馈机器人响应过慢，希望首次响应在15秒内",
            "零售场景收银员扫码经常失败，需要提升识别准确率",
            "Agent商店新增技能后用户找不到入口，需要优化导航",
        ]
        for text in demo_cases:
            run_single_requirement(JACKY_OPEN_ID, text)
        print("[DEMO] 全部完成")
        return

    # 生产模式：启动 WS，等待飞书消息触发
    start_card_listener()
    time.sleep(2)
    msg_queue = get_incoming_message_queue()
    active_threads = []
    print("[main] ✅ 就绪，等待飞书消息...")

    while True:
        try:
            try:
                msg = msg_queue.get(timeout=1.0)
                text = msg.get("text", "").strip()
                sender_id = msg.get("sender_open_id") or JACKY_OPEN_ID
                _chat_id_val = msg.get("sender_chat_id", "")
                print(f"\n[main] 收到消息: {text[:60]}")
                if sender_id not in AUTHORIZED_SENDERS:
                    print(f"[main] 未授权用户 {sender_id}，已拒绝")
                    _reject_dest = _chat_id_val or sender_id
                    _reject_type = "chat_id" if _chat_id_val else "open_id"
                    send_feishu_message(_reject_dest, "您没有权限提交需求，请联系售前团队。", _reject_type)
                    continue
                sender_chat_id_val = msg.get("sender_chat_id", "")
                t = threading.Thread(
                    target=run_single_requirement,
                    args=(sender_id, text, sender_chat_id_val),
                    daemon=True,
                )
                t.start()
                active_threads = [t for t in active_threads if t.is_alive()]
                active_threads.append(t)
            except Exception:
                pass
        except KeyboardInterrupt:
            print("\n[main] 退出...")
            break


if __name__ == "__main__":
    main()
