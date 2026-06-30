from __future__ import annotations
from __future__ import annotations
import json
import requests
from datetime import datetime
from config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BASE_URL,
    BITABLE_APP_TOKEN, BITABLE_TABLE_ID, DEMO_MODE
)
from people_map import get_open_id

_feishu_token_cache = {"token": None, "expires_at": 0}


def _get_feishu_token() -> str:
    now = datetime.now().timestamp()
    if _feishu_token_cache["token"] and now < _feishu_token_cache["expires_at"]:
        return _feishu_token_cache["token"]

    resp = requests.post(
        f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
    )
    data = resp.json()
    _feishu_token_cache["token"] = data["tenant_access_token"]
    _feishu_token_cache["expires_at"] = now + data["expire"] - 60
    return _feishu_token_cache["token"]


def resolve_feishu_user_id(name: str) -> dict:
    """Look up Feishu open_id by name: first people_map, then Feishu search API."""
    if DEMO_MODE:
        demo_id = f"demo_uid_{name.replace(' ', '_')}"
        print(f"[DEMO] resolve_feishu_user_id({name!r}) → {demo_id}")
        return {"open_id": demo_id, "name": name}

    # 1. 先查 people_map（角色映射）
    from people_map import PEOPLE_MAP, JACKY_OPEN_ID
    if name in PEOPLE_MAP:
        open_id = PEOPLE_MAP[name]
        print(f"  [people_map] {name!r} → {open_id}")
        return {"open_id": open_id, "name": name}

    # 2. 尝试飞书用户搜索 API
    try:
        token = _get_feishu_token()
        resp = requests.get(
            f"{FEISHU_BASE_URL}/contact/v3/users/batch_get_id",
            headers={"Authorization": f"Bearer {token}"},
            params={"user_id_type": "open_id"},
            json={"mobiles": [], "emails": []},
        )
        # 用名字搜索
        search_resp = requests.post(
            f"{FEISHU_BASE_URL}/contact/v3/users/search",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": name, "page_size": 5},
        )
        data = search_resp.json()
        if data.get("code") == 0:
            items = data.get("data", {}).get("items", [])
            if items:
                user = items[0]
                open_id = user.get("open_id", "")
                display = user.get("name", name)
                print(f"  [feishu_search] {name!r} → {open_id} ({display})")
                return {"open_id": open_id, "name": display}
        print(f"  [feishu_search] {name!r} 搜索无结果，使用 Jacky 底止")
    except Exception as e:
        print(f"  [feishu_search] 异常: {e}")

    # 3. 底止：返回 Jacky open_id
    return {"open_id": JACKY_OPEN_ID, "name": name}


def send_feishu_group_message(chat_id: str, content: str) -> dict:
    """Send a text message to a Feishu group chat."""
    if DEMO_MODE:
        print(f"\n[DEMO] send_feishu_group_message → {chat_id}")
        print("─" * 60)
        print(content)
        print("─" * 60)
        return {"message_id": f"demo_group_msg_{datetime.now().timestamp()}", "ok": True}

    token = _get_feishu_token()
    resp = requests.post(
        f"{FEISHU_BASE_URL}/im/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={"receive_id_type": "chat_id"},
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": content}),
        },
    )
    data = resp.json()
    if data.get("code") != 0:
        return {"ok": False, "error": data.get("msg")}
    return {"message_id": data["data"]["message_id"], "ok": True}


def send_feishu_message(open_id: str, content: str, id_type: str = "open_id") -> dict:
    """Send a text message to a Feishu user."""
    if DEMO_MODE:
        print(f"\n[DEMO] send_feishu_message → {open_id}")
        print("─" * 60)
        print(content)
        print("─" * 60)
        return {"message_id": f"demo_msg_{datetime.now().timestamp()}", "ok": True}

    token = _get_feishu_token()
    resp = requests.post(
        f"{FEISHU_BASE_URL}/im/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={"receive_id_type": id_type},
        json={
            "receive_id": open_id,
            "msg_type": "text",
            "content": json.dumps({"text": content}),
        },
    )
    data = resp.json()
    if data.get("code") != 0:
        return {"ok": False, "error": data.get("msg")}
    return {"message_id": data["data"]["message_id"], "ok": True}


def patch_card_with_token(card_token: str, card_json: dict) -> dict:
    """Update a card using the callback event.token.
    API: POST /interactive/v1/card/update
    token is valid for 30 minutes, can be used up to 2 times.
    card.data must be a JSON-serialized STRING, not a dict.
    """
    if DEMO_MODE:
        print(f"[DEMO] patch_card_with_token token={card_token[:20]}...")
        return {"ok": True}

    import json as _json
    token = _get_feishu_token()
    resp = requests.post(
        f"{FEISHU_BASE_URL}/interactive/v1/card/update",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "token": card_token,
            "card": {
                "type": "raw",
                "data": _json.dumps(card_json, ensure_ascii=False),  # must be string!
            },
        },
    )
    data = resp.json()
    print(f"[patch_card] API response: {data}")
    if data.get("code") != 0:
        return {"ok": False, "error": data.get("msg"), "code": data.get("code")}
    return {"ok": True}


def send_feishu_card(receive_id: str, card_json: dict, id_type: str = "open_id") -> dict:
    """Send an interactive card message to a Feishu user or chat.

    receive_id: open_id 或 chat_id
    id_type: "open_id"（默认）或 "chat_id"
    Returns {"message_id": str, "ok": True} on success.
    """
    if DEMO_MODE:
        fake_id = f"demo_card_{datetime.now().timestamp()}"
        print(f"\n[DEMO] send_feishu_card → {receive_id} ({id_type})  card_id={fake_id}")
        print("─" * 60)
        print(json.dumps(card_json, ensure_ascii=False, indent=2)[:1200])
        print("─" * 60)
        return {"message_id": fake_id, "ok": True}

    token = _get_feishu_token()
    resp = requests.post(
        f"{FEISHU_BASE_URL}/im/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={"receive_id_type": id_type},
        json={
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card_json, ensure_ascii=False),
        },
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[send_feishu_card] ⚠️ 发送失败 code={data.get('code')} msg={data.get('msg')} receive_id={receive_id} id_type={id_type}")
        return {"ok": False, "error": data.get("msg")}
    print(f"[send_feishu_card] ✅ 发送成功 receive_id={receive_id[:30]} id_type={id_type}")
    return {"message_id": data["data"]["message_id"], "ok": True}


def _schema_to_bitable_fields(record) -> dict:
    """将各类 Schema / 直接字段 dict 转换为多维表格 v3 中文字段名。"""
    # Agent 有时传 JSON 字符串而非 dict，先解析
    if isinstance(record, str):
        try:
            record = json.loads(record)
        except (json.JSONDecodeError, TypeError):
            return {"Schema JSON": record[:50000]}
    # 支持直接传入 v3 新格式字段（已含 S1/S2/S3 前缀）
    if any(k.startswith('S1_') or k.startswith('S2_') or k.startswith('S3_') for k in record):
        fields = {k: (v if isinstance(v, (int, float, list, dict)) else str(v))
                  for k, v in record.items() if v is not None and v != ''}
        if 'Schema_JSON' not in fields:
            fields['Schema_JSON'] = json.dumps(record, ensure_ascii=False)[:50000]
        return fields

    # 将旧格式 Schema JSON 映射到 v3 字段
    g = record.get('gatekeeping', {})
    verdict_map = {'approved': '通过', 'rejected': '拒绝', 'info_needed': '待补充'}
    stage_map = {
        'gatekeeping_approved': 'Stage2产品审批',
        'gatekeeping_rejected': '已终止',
        'gatekeeping_pending':  'Stage1录入中',
        'value_defined':        'Stage3研发审批',
        'testing_complete':     'Stage4发版审批',
        'release_approved':     'Stage5反馈收集',
        'feedback_collected':   'Stage6复盘',
        'retrospective_complete': '已完成',
    }

    fields = {}
    now_ms = int(datetime.now().timestamp() * 1000)

    if record.get('requirement_id'): fields['需求ID']   = str(record['requirement_id'])
    if record.get('original_text'):  fields['需求标题'] = str(record['original_text'])[:200]
    if record.get('stage'):          fields['当前阶段'] = stage_map.get(record['stage'], str(record['stage']))
    fields['最后更新时间'] = now_ms

    # S1 四问字段
    if g.get('customer_who'):    fields['S1_需求是什么'] = str(g['customer_who'])
    if g.get('problem'):         fields['S1_为什么要做'] = str(g['problem'])
    if g.get('usage_scenario'):  fields['S1_目标用户']   = str(g['usage_scenario'])
    if g.get('expected_outcome'): fields['S1_验收标准']  = str(g['expected_outcome'])
    if g.get('rounds') is not None: fields['S1_交互轮数'] = int(g['rounds'])

    # S2 产品审批
    if record.get('pm_confirmed_by'): fields['S2_负责人'] = str(record['pm_confirmed_by'])
    if record.get('pm_verdict'):      fields['S2_结果']   = '通过' if record['pm_verdict'] == 'approved' else '拒绝'

    # S3 研发审批
    if record.get('dev_verdict'):     fields['S3_结果']   = '通过' if record['dev_verdict'] == 'approved' else '拒绝'

    # S4 发版
    if record.get('version'):         fields['S4_负责人'] = str(record.get('version', ''))
    release_map = {'approved': '通过', 'blocked': '拒绝', 'pending': '待审'}
    if record.get('release_verdict'): fields['S4_结果'] = release_map.get(record['release_verdict'], '通过')

    # Schema 存档
    fields['Schema_JSON'] = json.dumps(record, ensure_ascii=False)[:50000]
    return fields


def get_bitable_record_by_key(requirement_id: str, stage: str) -> str | None:
    """Return the record_id of an existing Bitable row matching (需求ID, 当前阶段), or None.

    In DEMO_MODE always returns None (no dedup needed for console output).
    """
    if DEMO_MODE:
        return None

    token = _get_feishu_token()
    # Feishu filter syntax for AND condition
    filter_expr = (
        f'AND(CurrentValue.[需求ID]="{requirement_id}",'
        f'CurrentValue.[当前阶段]="{stage}")'
    )
    resp = requests.get(
        f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records",
        headers={"Authorization": f"Bearer {token}"},
        params={"filter": filter_expr, "page_size": 1},
    )
    data = resp.json()
    if data.get("code") != 0:
        return None
    items = data.get("data", {}).get("items", [])
    if items:
        return items[0].get("record_id")
    return None


def delete_empty_bitable_rows() -> int:
    """Delete all Bitable rows where 需求ID is empty or null. Returns count deleted.

    In DEMO_MODE prints a message and returns 0.
    """
    if DEMO_MODE:
        print("[DEMO] delete_empty_bitable_rows — skipped in DEMO_MODE")
        return 0

    token = _get_feishu_token()
    deleted = 0

    # Fetch rows with empty 需求ID
    resp = requests.get(
        f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records",
        headers={"Authorization": f"Bearer {token}"},
        params={"page_size": 100},
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[delete_empty_bitable_rows] Query failed: {data.get('msg')}")
        return 0

    items = data.get("data", {}).get("items", [])
    for item in items:
        fields = item.get("fields", {})
        req_id = fields.get("需求ID", "")
        if not req_id or str(req_id).strip() == "":
            rec_id = item["record_id"]
            del_resp = requests.delete(
                f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records/{rec_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if del_resp.json().get("code") == 0:
                deleted += 1
                print(f"[delete_empty_bitable_rows] Deleted empty row: {rec_id}")

    print(f"[delete_empty_bitable_rows] Done — deleted {deleted} empty rows")
    return deleted


def get_bitable_record_fields(record_id: str) -> dict:
    """按 record_id 读取当前记录 fields。失败时返回空 dict。"""
    if DEMO_MODE or not record_id:
        return {}

    token = _get_feishu_token()
    resp = requests.get(
        f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records/{record_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[get_bitable_record_fields] Query failed: {data.get('msg')}")
        return {}
    return data.get("data", {}).get("record", {}).get("fields", {}) or {}


def write_bitable_record(record: dict | str, record_id: str | None = None) -> dict:
    """Create or update a Bitable record. Pass record_id to update an existing row."""
    import json as _json
    if isinstance(record, str):
        import re as _re
        import ast as _ast
        _raw = record
        # Strip markdown code fences before attempting JSON parse
        _cleaned = _re.sub(r"```(?:json)?\s*", "", _raw).replace("```", "").strip()
        _parsed = None
        # Try 1: standard JSON (double-quoted)
        try:
            _parsed = _json.loads(_cleaned)
        except Exception:
            pass
        # Try 2: Python repr format (single-quoted) — Agent sometimes emits this
        if _parsed is None:
            try:
                _parsed = _ast.literal_eval(_cleaned)
                if not isinstance(_parsed, dict):
                    _parsed = None
            except Exception:
                pass
        if _parsed is None:
            print(f"[bitable] ⚠️ record 无法解析（json+ast均失败）: {_raw[:120]}")
            return {"ok": False, "error": "record 字段为无法解析的字符串"}
        record = _parsed
    if DEMO_MODE:
        op = "UPDATE" if record_id else "CREATE"
        print(f"\n[DEMO] write_bitable_record ({op}) record_id={record_id}")
        print(json.dumps(record, ensure_ascii=False, indent=2)[:800])
        return {"record_id": record_id or f"demo_rec_{datetime.now().timestamp()}", "ok": True}

    token = _get_feishu_token()
    # 如果传入的是旧格式 Schema JSON（含 schema_version），走转换函数
    if "schema_version" in record or "gatekeeping" in record or "original_text" in record:
        fields = _schema_to_bitable_fields(record)
    else:
        # 直接传入中文字段名 dict：数字保留 int/float，其余转字符串
        fields = {}
        for k, v in record.items():
            if v is None or v == "":
                continue  # 跳过空值，避免覆盖已有数据
            if isinstance(v, (int, float, bool)):
                fields[k] = v  # 数字/bool 直接传
            elif isinstance(v, (list, dict)):
                fields[k] = v  # 人员/多选等结构体直接传，不转字符串
            else:
                fields[k] = str(v)

    # Idempotency: if no record_id given, check whether a row already exists for this (需求ID, 当前阶段)
    if record_id is None:
        req_id = fields.get("需求ID") or record.get("requirement_id")
        stage = fields.get("当前阶段") or record.get("stage")
        if req_id and stage:
            existing_id = get_bitable_record_by_key(str(req_id), str(stage))
            if existing_id:
                print(f"  [bitable] Found existing row {existing_id} for ({req_id}, {stage}) — using UPDATE")
                record_id = existing_id

    import json as _json2
    print(f"[bitable] 📤 写入字段: {_json2.dumps(fields, ensure_ascii=False)[:300]}")
    if record_id:
        resp = requests.put(
            f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records/{record_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"fields": fields},
        )
    else:
        resp = requests.post(
            f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records",
            headers={"Authorization": f"Bearer {token}"},
            json={"fields": fields},
        )

    data = resp.json()
    if data.get("code") != 0:
        print(f"[bitable] ❌ 写入失败 code={data.get('code')} msg={data.get('msg')} fields={list(fields.keys())} app={BITABLE_APP_TOKEN} table={BITABLE_TABLE_ID}")
        return {"ok": False, "error": data.get("msg"), "code": data.get("code")}
    return {"record_id": data["data"]["record"]["record_id"], "ok": True}


# Tool definitions for Claude API tool_use
TOOL_DEFINITIONS = [
    {
        "name": "resolve_feishu_user_id",
        "description": "通过姓名查询飞书用户的open_id，发消息前必须先调用此工具。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "飞书用户的显示名称"}
            },
            "required": ["name"],
        },
    },
    {
        "name": "send_feishu_message",
        "description": "向指定飞书用户发送文本消息。",
        "input_schema": {
            "type": "object",
            "properties": {
                "open_id": {"type": "string", "description": "收件人的飞书open_id"},
                "content": {"type": "string", "description": "消息正文（纯文本）"},
            },
            "required": ["open_id", "content"],
        },
    },
    {
        "name": "write_bitable_record",
        "description": "写入或更新多维表格记录。仅用于直接写入中文字段名的 bitable 数据，不得用于提交 Schema JSON。",
        "input_schema": {
            "type": "object",
            "properties": {
                "record": {"type": "object", "description": "要写入的字段键值对"},
                "record_id": {"type": "string", "description": "传入则更新，不传则新建"},
            },
            "required": ["record"],
        },
    },
    # ── 专用提交工具（Agent 专用，Pipeline 从 tool_calls 取原子字段，脚本组装 Schema）──
    {
        "name": "submit_gatekeeping_result",
        "description": (
            "守门Agent专用：提交守门判断结果。"
            "只传判断值（原子字段），不传 Schema JSON，Pipeline 负责组装。"
            "调用完成后无需再输出任何 JSON。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["approved", "rejected", "info_needed"],
                    "description": "守门结论：approved=通过 / rejected=拒绝 / info_needed=需补充信息",
                },
                "requirement_source": {
                    "type": "string",
                    "enum": ["客户", "售前", "内部研发", "老板/战略", "合作伙伴", "未知"],
                    "description": "需求来源类型",
                },
                "source_traceable": {
                    "type": "boolean",
                    "description": "信息是否可追溯到客户原话或行为",
                },
                "customer_who": {
                    "type": ["string", "null"],
                    "description": "客户是谁（角色/公司），无法提取填 null",
                },
                "usage_scenario": {
                    "type": ["string", "null"],
                    "description": "使用场景，无法提取填 null",
                },
                "problem": {
                    "type": ["string", "null"],
                    "description": "遇到的问题，无法提取填 null",
                },
                "expected_outcome": {
                    "type": ["string", "null"],
                    "description": "期望结果，无法提取填 null",
                },
                "reject_reason": {
                    "type": ["string", "null"],
                    "description": "拒绝原因，仅 verdict=rejected 时填写，其余填 null",
                },
                "followup_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "追问问题列表，仅 verdict=info_needed 时填写，其余传空数组 []",
                },
            },
            "required": ["verdict", "source_traceable", "followup_questions"],
        },
    },
]


# ── 专用工具 handler（只记录，不执行飞书操作；Pipeline 从 tool_calls 取参数）──
def _handle_submit_gatekeeping_result(args: dict) -> dict:
    """守门结果提交：仅返回 ok，Pipeline 用 extract_gatekeeping_result 取参数。"""
    print(f"  [submit_gatekeeping_result] verdict={args.get('verdict')} source_traceable={args.get('source_traceable')}")
    return {"ok": True, "received": list(args.keys())}


TOOL_DISPATCH = {
    "resolve_feishu_user_id": lambda args: resolve_feishu_user_id(**args),
    "send_feishu_message": lambda args: send_feishu_message(**args),
    "write_bitable_record": lambda args: write_bitable_record(**args),
    "submit_gatekeeping_result": _handle_submit_gatekeeping_result,
}
