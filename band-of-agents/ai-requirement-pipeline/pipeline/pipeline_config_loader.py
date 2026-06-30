"""
pipeline_config_loader.py — Pipeline 配置加载器

从 pipeline_config.yaml 加载流程定义，提供类型安全的查询接口。
所有阶段属性、需求类型、审批规则均由此模块统一管理。

用法：
    from pipeline_config_loader import get_config, get_stage, get_requirement_type
    config = get_config()
    stage2 = get_stage(2)
    req_type = get_requirement_type("customer_reported")
"""

from __future__ import annotations
from pathlib import Path
from typing import Any
import functools
import yaml

_CONFIG_PATH = Path(__file__).parent / "pipeline_config.yaml"
_config_cache: dict | None = None


def _load_raw() -> dict:
    """加载 YAML 原始 dict，带缓存。"""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"配置文件不存在: {_CONFIG_PATH}")
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f)
    print(f"[config_loader] 已加载配置: {_CONFIG_PATH}")
    return _config_cache


@functools.lru_cache(maxsize=1)
def get_config() -> dict:
    """获取完整配置 dict。"""
    return _load_raw()


def get_stages() -> list[dict]:
    """获取所有阶段定义列表（按 num 排序）。"""
    stages = _load_raw().get("stages", [])
    return sorted(stages, key=lambda s: s.get("num", 99))


def get_stage(stage_num: int) -> dict | None:
    """按阶段编号获取阶段定义。"""
    for s in get_stages():
        if s["num"] == stage_num:
            return s
    return None


def get_stage_by_id(stage_id: str) -> dict | None:
    """按阶段 ID（如 'pm_review'）获取阶段定义。"""
    for s in get_stages():
        if s["id"] == stage_id:
            return s
    return None


def get_stage_count() -> int:
    """获取阶段总数。"""
    return len(get_stages())


def get_terminal_stage_num() -> int:
    """获取终态阶段编号。"""
    for s in get_stages():
        if s.get("is_terminal"):
            return s["num"]
    return get_stages()[-1]["num"]  # 兜底：最后一个阶段


def get_next_stage_num(current_num: int) -> int | None:
    """获取某阶段的下一阶段编号。stage 定义里的 next_stage 优先，否则按排序取下一个。"""
    stage = get_stage(current_num)
    if stage is None:
        return None
    ns = stage.get("next_stage")
    if ns is not None:
        return ns
    # 兜底：按列表顺序
    all_nums = [s["num"] for s in get_stages()]
    idx = all_nums.index(current_num) if current_num in all_nums else -1
    if idx >= 0 and idx + 1 < len(all_nums):
        return all_nums[idx + 1]
    return None


def get_requirement_types() -> list[dict]:
    """获取所有需求类型定义。"""
    return _load_raw().get("requirement_types", [])


def get_requirement_type(type_id: str) -> dict | None:
    """按 ID 获取需求类型定义。"""
    for rt in get_requirement_types():
        if rt["id"] == type_id:
            return rt
    return None


def get_requirement_type_default() -> dict:
    """获取默认需求类型（第一个）。"""
    types = get_requirement_types()
    return types[0] if types else {"id": "customer_reported", "name": "客户需求"}


def get_approval_outcomes() -> list[dict]:
    """获取所有审批结果枚举。"""
    return _load_raw().get("approval_outcomes", [])


def get_priorities() -> list[str]:
    """获取优先级枚举列表。"""
    return _load_raw().get("priorities", ["SP", "P0", "P1", "P2"])


def get_defaults() -> dict:
    """获取流程默认设置。"""
    return _load_raw().get("defaults", {})


def get_stage_fields(stage_num: int) -> dict:
    """
    获取某阶段写入 Bitable 的字段映射。
    返回 {"bitable_prefix": str, "bitable_stage": str, "role": str, ...}
    """
    stage = get_stage(stage_num)
    if stage is None:
        return {}
    return {
        "bitable_prefix": stage.get("bitable_prefix", f"S{stage_num}"),
        "bitable_stage": stage.get("bitable_stage", f"Stage{stage_num}"),
        "role": stage.get("role", ""),
        "name": stage.get("name", ""),
        "timeout_hours": stage.get("timeout_hours", 0),
        "hard_gates": stage.get("hard_gates", []),
        "tool_whitelist": stage.get("tool_whitelist", []),
        "ai_assist": stage.get("ai_assist"),
    }


def get_rejection_chain(stage_num: int) -> list[int]:
    """
    获取某阶段的逐级回退链。
    返回：[上一级, 上两级, ..., 1]（从近到远）。
    例如 stage_num=3 → [2, 1]
    """
    chain = []
    current = stage_num
    while True:
        prev = None
        for s in get_stages():
            if s.get("next_stage") == current:
                prev = s["num"]
                break
        if prev is None:
            # 兜底：按 num 递减
            prev = current - 1
        if prev < 1:
            break
        chain.append(prev)
        current = prev
    return chain


def get_all_stage_bitable_prefixes() -> dict[int, str]:
    """返回 {stage_num: bitable_prefix} 映射。"""
    return {s["num"]: s.get("bitable_prefix", f"S{s['num']}") for s in get_stages()}


# ─── 便捷查询 ─────────────────────────────────────────────

def stage_has_card_confirm(stage_num: int) -> bool:
    """某阶段是否需要二次确认卡片。"""
    s = get_stage(stage_num)
    return s.get("card", {}).get("confirm_card", False) if s else False


def stage_is_terminal(stage_num: int) -> bool:
    """某阶段是否为终态。"""
    s = get_stage(stage_num)
    return s.get("is_terminal", False) if s else False


def stage_hard_gates(stage_num: int) -> list[dict]:
    """获取某阶段的硬门禁规则。"""
    s = get_stage(stage_num)
    return s.get("hard_gates", []) if s else []


def stage_timeout_hours(stage_num: int) -> int:
    """获取某阶段的超时时间（小时），0 表示不限时。"""
    s = get_stage(stage_num)
    return s.get("timeout_hours", 0) if s else 0


# ─── 需求类型工具函数 ─────────────────────────────────────

def get_required_fields_for_type(type_id: str) -> dict[str, bool]:
    """
    获取某需求类型的必填字段规则。
    返回 {"customer_who": true, "usage_scenario": true, ...}
    """
    rt = get_requirement_type(type_id)
    if rt is None:
        rt = get_requirement_type_default()
    return rt.get("required_fields", {})


def is_source_traceable_required(type_id: str) -> bool:
    """某需求类型是否要求来源可追溯。"""
    rt = get_requirement_type(type_id)
    if rt is None:
        rt = get_requirement_type_default()
    return rt.get("source_traceable_required", True)


def validate_requirement_type(type_id: str) -> bool:
    """验证需求类型 ID 是否合法。"""
    return get_requirement_type(type_id) is not None


# ─── 调试用 ─────────────────────────────────────────────

def print_config_summary():
    """打印配置摘要（调试用）。"""
    stages = get_stages()
    types = get_requirement_types()
    print(f"\n{'='*50}")
    print(f"Pipeline 配置摘要")
    print(f"{'='*50}")
    print(f"阶段数: {len(stages)}")
    for s in stages:
        term = " [终态]" if s.get("is_terminal") else ""
        card = s.get("card", {})
        confirm = " → 二次确认" if card.get("confirm_card") else ""
        ai = " + AI" if s.get("ai_assist") else ""
        print(f"  Stage{s['num']}: {s['name']} ({s['role']}){term}{confirm}{ai}")
    print(f"\n需求类型数: {len(types)}")
    for t in types:
        req = {k for k, v in t.get("required_fields", {}).items() if v}
        src = "需溯源" if t.get("source_traceable_required") else "不强制溯源"
        print(f"  {t['id']}: {t['name']} | 必填: {req} | {src}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    print_config_summary()
