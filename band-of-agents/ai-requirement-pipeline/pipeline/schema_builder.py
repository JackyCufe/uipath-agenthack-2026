"""
schema_builder.py — Pipeline Schema 组装、校验与纯算术计算

原则：
- AI 只做语义判断（填原子字段值）
- 本模块负责把原子字段组装成标准 Schema JSON
- 所有 enum 校验、null 保护、纯算术在这里，不在 Prompt 里

对外接口：
  build_schema1(...)          → Schema 1 dict
  build_schema2(...)          → Schema 2 dict
  build_schema4_verdict(...)  → "approved" | "blocked"（纯规则，替代 Agent 04 AI 判断）
  calc_satisfaction_rate(...) → float（替代 Agent 05 AI 计算）
  calc_health_score(...)      → float（替代 Agent 06 AI 计算）
  validate_and_repair(...)    → 对任意 schema dict 补全缺字段
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

# ─── 合法枚举值 ──────────────────────────────────────────

VERDICT_VALUES = {"approved", "rejected", "info_needed"}
STAGE1_STAGE_MAP = {
    "approved":   "gatekeeping_approved",
    "rejected":   "gatekeeping_rejected",
    "info_needed": "gatekeeping_pending",
}
REQUIREMENT_SOURCE_VALUES = {"客户", "售前", "内部研发", "老板/战略", "合作伙伴", "未知"}
REQUIREMENT_TYPE_VALUES = {"customer_reported", "internal_improvement", "compliance", "competitive"}
IMPORTANCE_VALUES = {"P0", "P1", "P2"}
RELEASE_VERDICT_VALUES = {"approved", "blocked"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_str_or_null(val: Any) -> str | None:
    """将值转为 str，None/空字符串统一返回 None。"""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _coerce_list_of_str(val: Any) -> list[str]:
    """确保返回 list[str]，兼容 None / str / list。"""
    if val is None:
        return []
    if isinstance(val, str):
        return [val] if val.strip() else []
    if isinstance(val, list):
        return [str(v) for v in val if v is not None and str(v).strip()]
    return []


def _coerce_bool(val: Any, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes", "是")
    return default


# ─── Schema 1 ────────────────────────────────────────────

def build_schema1(
    *,
    verdict: str,
    customer_who: Any = None,
    usage_scenario: Any = None,
    problem: Any = None,
    expected_outcome: Any = None,
    reject_reason: Any = None,
    followup_questions: Any = None,
    requirement_source: Any = None,
    requirement_type: Any = None,
    source_traceable: Any = None,
    req_id: str,
    original_text: str,
    submitted_by: str = "售前",
    submitted_at: str | None = None,
    rounds: int = 1,
    confirmed_by: Any = None,
    confirmed_at: Any = None,
) -> dict:
    """
    组装 Schema 1 JSON。
    - verdict 必须是合法 enum 值，非法时强制降为 "info_needed" 并记录警告
    - requirement_type 必须是合法枚举值，否则默认 customer_reported
    - 所有可空字段统一为 None（不是空字符串）
    - stage 由 verdict 自动映射，不由 AI 控制
    """
    # enum 校验
    if verdict not in VERDICT_VALUES:
        print(f"[schema_builder] ⚠️ 非法 verdict={verdict!r}，降级为 info_needed")
        verdict = "info_needed"

    # requirement_source 校验
    src = _coerce_str_or_null(requirement_source)
    if src not in REQUIREMENT_SOURCE_VALUES:
        src = "未知"

    # requirement_type 校验
    rtype = _coerce_str_or_null(requirement_type)
    if rtype not in REQUIREMENT_TYPE_VALUES:
        rtype = "customer_reported"

    # followup_questions 仅在 info_needed 时有意义
    fqs = _coerce_list_of_str(followup_questions)
    if verdict != "info_needed":
        fqs = []

    # reject_reason 仅在 rejected 时有意义
    rr = _coerce_str_or_null(reject_reason) if verdict == "rejected" else None

    return {
        "schema_version": "1.0",
        "stage": STAGE1_STAGE_MAP[verdict],
        "requirement_id": req_id,
        "original_text": original_text,          # 绝对不修改
        "submitted_by": submitted_by,
        "submitted_at": submitted_at or _now_iso(),
        "requirement_source": src,
        "requirement_type": rtype,
        "gatekeeping": {
            "verdict": verdict,
            "rounds": rounds,
            "customer_who": _coerce_str_or_null(customer_who),
            "usage_scenario": _coerce_str_or_null(usage_scenario),
            "problem": _coerce_str_or_null(problem),
            "expected_outcome": _coerce_str_or_null(expected_outcome),
            "source_traceable": _coerce_bool(source_traceable, default=(verdict == "approved")),
            "reject_reason": rr,
            "followup_questions": fqs,
        },
        "confirmed_by": _coerce_str_or_null(confirmed_by),
        "confirmed_at": _coerce_str_or_null(confirmed_at),
    }


# ─── Schema 2 ────────────────────────────────────────────

def _build_criterion(raw: dict) -> dict:
    """规范化单条验收标准，统一字段名，补齐缺字段。"""
    return {
        "criterion_id":       _coerce_str_or_null(raw.get("criterion_id")) or "",
        "description":        _coerce_str_or_null(raw.get("description")) or "",
        "metric":             _coerce_str_or_null(raw.get("metric")) or "",
        "threshold":          _coerce_str_or_null(raw.get("threshold")) or "",
        "measurement_method": _coerce_str_or_null(raw.get("measurement_method")) or "",
        "pm_original":        _coerce_str_or_null(raw.get("pm_original")) or "",
    }


def _build_test_case(raw: dict) -> dict:
    """
    规范化单条测试用例。
    - actual_result / verdict 强制为 null（由人工填写，AI 不得预填）
    - 统一字段名：expected_result（兼容 expected_output）
    """
    steps = raw.get("steps", [])
    if isinstance(steps, str):
        steps = [s.strip() for s in steps.split("\n") if s.strip()]

    expected = (
        _coerce_str_or_null(raw.get("expected_result"))
        or _coerce_str_or_null(raw.get("expected_output"))  # 兼容旧字段名
        or ""
    )
    return {
        "case_id":          _coerce_str_or_null(raw.get("case_id")) or "",
        "criterion_id":     _coerce_str_or_null(raw.get("criterion_id") or raw.get("linked_criterion")) or "",
        "actor":            _coerce_str_or_null(raw.get("actor")) or "",
        "precondition":     _coerce_str_or_null(raw.get("precondition")) or "",
        "steps":            [str(s) for s in steps],
        "expected_result":  expected,
        "actual_result":    None,   # 强制 null，人工填写
        "verdict":          None,   # 强制 null，人工填写
    }


def build_schema2(
    *,
    requirement_id: str,
    four_q: dict,
    pm_core_value: str = "",
    pm_feature_def: str = "",
    pm_priority: str = "",
    pm_acceptance_criteria_raw: str = "",
    structured_criteria: list[dict],
    test_cases: list[dict],
    pm_confirmed_by: Any = None,
    pm_confirmed_at: Any = None,
) -> dict:
    """组装 Schema 2 JSON。actual_result/verdict 强制 null。"""
    return {
        "schema_version": "2.0",
        "stage": "value_defined",
        "requirement_id": requirement_id,
        "four_q": four_q,                           # 透传，不修改
        "pm_core_value": pm_core_value,
        "pm_feature_def": pm_feature_def,
        "pm_priority": pm_priority,
        "pm_acceptance_criteria_raw": pm_acceptance_criteria_raw,
        "structured_criteria": [_build_criterion(c) for c in structured_criteria],
        "test_cases": [_build_test_case(tc) for tc in test_cases],
        "_pending_pm_confirmation": pm_confirmed_by is None,
        "pm_confirmed_by": _coerce_str_or_null(pm_confirmed_by),
        "pm_confirmed_at": _coerce_str_or_null(pm_confirmed_at),
    }


# ─── Schema 4 verdict（纯规则，不经 AI）────────────────────

def build_schema4_verdict(requirements_list: list[dict]) -> str:
    """
    按 Rubric 规则机械计算发版 verdict：
      - 任意 P0 需求 acceptance_verdict = "fail" → "blocked"
      - 否则 → "approved"

    这是确定性逻辑，不应由 AI 判断。

    requirements_list 每条格式：
      {"requirement_id": ..., "importance": "P0|P1|P2", "acceptance_verdict": "pass|fail|blocked_by_env"}
    """
    for req in requirements_list:
        importance = (req.get("importance") or "").upper()
        av = (req.get("acceptance_verdict") or "").lower()
        if importance == "P0" and av == "fail":
            print(f"[schema_builder] 发版 blocked：P0需求 {req.get('requirement_id')} acceptance_verdict=fail")
            return "blocked"
    return "approved"


def build_bypass_log(requirements_list: list[dict]) -> list[dict]:
    """
    生成 bypass_log：P1 需求 fail 时写入。
    P2 fail 只记录 warning，不入 bypass_log。
    """
    bypass = []
    for req in requirements_list:
        importance = (req.get("importance") or "").upper()
        av = (req.get("acceptance_verdict") or "").lower()
        if importance == "P1" and av == "fail":
            bypass.append({
                "requirement_id": req.get("requirement_id"),
                "importance": "P1",
                "fail_reason": req.get("block_reason") or "P1需求测试未通过",
                "bypass_approved_by": None,
            })
    return bypass


# ─── 纯算术：替代 Agent 05 / 06 的计算 ─────────────────────

def calc_satisfaction_rate(satisfied_count: int, unsatisfied_count: int) -> float:
    """
    满意率 = satisfied / (satisfied + unsatisfied)
    不让 AI 算，避免精度问题和幻觉。
    """
    total = satisfied_count + unsatisfied_count
    if total <= 0:
        return 0.0
    return round(satisfied_count / total, 4)


def calc_health_score(improvement_actions_count: int) -> float:
    """
    流程健康度 = 1.0 - 每条 improvement_action 扣 0.1，最低 0.0
    规则来自 06-retrospective.md，搬到脚本执行，不让 AI 算。
    """
    return max(0.0, round(1.0 - improvement_actions_count * 0.1, 1))


# ─── 通用 Schema 修复（兜底）────────────────────────────────

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "1.0_s1": ["schema_version", "stage", "requirement_id", "original_text", "gatekeeping"],
    "2.0_s2": ["schema_version", "stage", "requirement_id", "four_q", "structured_criteria", "test_cases"],
}


def validate_and_repair(schema: dict) -> dict:
    """
    对 Agent 返回的 schema dict 做最后兜底：
    - 缺字段补 null，不抛异常（保证 Pipeline 不因 schema 残缺而崩溃）
    - 返回修复后的 dict（不修改原始对象）
    """
    import copy
    repaired = copy.deepcopy(schema)
    version = repaired.get("schema_version", "")
    stage = repaired.get("stage", "")

    # 判断是哪个 schema
    key = None
    if version == "1.0" and "gatekeeping" in stage:
        key = "1.0_s1"
    elif version == "2.0":
        key = "2.0_s2"

    if key and key in _REQUIRED_FIELDS:
        for field in _REQUIRED_FIELDS[key]:
            if field not in repaired:
                print(f"[schema_builder] ⚠️ 修复缺失字段: {field}")
                repaired[field] = None

    # Schema 1 专项修复
    if key == "1.0_s1" and isinstance(repaired.get("gatekeeping"), dict):
        gk = repaired["gatekeeping"]
        for f in ["verdict", "rounds", "customer_who", "usage_scenario",
                  "problem", "expected_outcome", "source_traceable",
                  "reject_reason", "followup_questions"]:
            if f not in gk:
                gk[f] = [] if f == "followup_questions" else None

    return repaired
