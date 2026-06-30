"""
bitable_reader.py — Bitable 历史需求读取工具

独立调用飞书 Bitable API，不 import pipeline 代码。
routing-agent 通过这个工具查询历史需求档案。

两个核心函数：
1. search_bitable_history(keyword) — 语义搜索历史需求
2. get_requirement_chain(requirement_id) — 拉取一条需求的完整 S1~S6 链路
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

# i18n
import os as _os
import sys as _sys
_i18n_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
if _i18n_dir not in _sys.path:
    _sys.path.insert(0, _i18n_dir)
from i18n import t

# ── 配置（从环境变量读取，兼容 pipeline 的 .env 加载机制）──
# pipeline/config.py 会加载 .env.team-testing，设置环境变量
# 这里直接读环境变量，不 import pipeline

def _get_config():
    """从环境变量读取飞书配置。如果没加载，尝试加载 pipeline 的 .env。"""
    app_id = os.environ.get("FEISHU_APP_ID")
    if not app_id:
        # 尝试加载 pipeline 的 .env
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
        "app_token": os.environ.get("BITABLE_APP_TOKEN", ""),
        "table_id": os.environ.get("DEMO_BITABLE_TABLE_ID", os.environ.get("BITABLE_TABLE_ID", "")),
    }


_token_cache = {"token": None, "expires_at": 0}


def _get_token() -> str:
    """获取飞书 tenant_access_token。"""
    import time
    now = time.time()
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


def search_bitable_history(keyword: str, top_k: int = 5, product_model: str = "") -> list[dict[str, Any]]:
    """
    搜索 Bitable 历史需求记录。

    用飞书 Bitable 的筛选 API + 关键词匹配。
    如果提供 product_model，先按型号筛选，再做语义匹配。

    返回 top_k 条最匹配的记录，每条包含：
    - requirement_id: 需求ID
    - title: 需求标题
    - searchable_text: 可搜索文本
    - stage_data: 各阶段数据
    - product_model: 产品型号
    """
    cfg = _get_config()
    if not cfg["app_token"]:
        print("[bitable_reader] ⚠️ BITABLE_APP_TOKEN 未配置，返回空列表")
        return []

    token = _get_token()

    # 如果有产品型号，用 Bitable filter 先筛选
    params = {"page_size": 50}
    if product_model:
        params["filter"] = f'CurrentValue.[{t("field.product_model")}]="{product_model}"'
        print(f"  [bitable_reader] {t('log.filtering_model', model=product_model)}")

    resp = requests.get(
        f"{cfg['base_url']}/bitable/v1/apps/{cfg['app_token']}/tables/{cfg['table_id']}/records",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[bitable_reader] ❌ 搜索失败: {data.get('msg')}")
        return []

    items = data.get("data", {}).get("items", [])
    results = []
    keyword_lower = keyword.lower()

    _req_id_field = t("field.requirement_id")
    _title_field = t("field.requirement_title")
    _model_field = t("field.product_model")

    for item in items:
        fields = item.get("fields", {})
        req_id = str(fields.get(_req_id_field, "")).strip()
        if not req_id:
            continue

        # 拼接可搜索文本：从所有字段中提取文本
        searchable_parts = [req_id]
        for key, val in fields.items():
            if val:
                if isinstance(val, str):
                    searchable_parts.append(val)
                elif isinstance(val, list):
                    for sub in val:
                        if isinstance(sub, dict):
                            searchable_parts.append(sub.get("en_name", sub.get("name", "")))
                        elif isinstance(sub, str):
                            searchable_parts.append(sub)
                elif isinstance(val, (int, float)):
                    searchable_parts.append(str(val))
        searchable_text = " ".join(searchable_parts)

        # 关键词匹配：中文 2~4 字滑窗
        import re
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

        text_lower = searchable_text.lower()
        hit_count = sum(1 for kw in keywords if kw.lower() in text_lower)
        if hit_count > 0:
            results.append({
                "requirement_id": req_id,
                "title": str(fields.get(_title_field, fields.get(_req_id_field, req_id)))[:100],
                "searchable_text": searchable_text,
                "stage_data": _parse_stage_data(fields),
                "record_id": item.get("record_id", ""),
                "similarity": hit_count / len(keywords),
                "product_model": str(fields.get(_model_field, "")),
            })

    results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
    return results[:top_k]


def get_requirement_chain(requirement_id: str) -> dict[str, Any] | None:
    """
    按 requirement_id 拉取一条需求的完整 S1~S6 链路。

    返回:
    {
        "requirement_id": "REQ-089",
        "title": "...",
        "stage_data": {"S1": {...}, "S2": {...}, ...},
        "searchable_text": "..."
    }
    """
    cfg = _get_config()
    if not cfg["app_token"]:
        print("[bitable_reader] ⚠️ BITABLE_APP_TOKEN 未配置")
        return None

    token = _get_token()
    filter_expr = f'CurrentValue.[{t("field.requirement_id")}]="{requirement_id}"'
    resp = requests.get(
        f"{cfg['base_url']}/bitable/v1/apps/{cfg['app_token']}/tables/{cfg['table_id']}/records",
        headers={"Authorization": f"Bearer {token}"},
        params={"filter": filter_expr, "page_size": 1},
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[bitable_reader] ❌ 查询失败: {data.get('msg')}")
        return None

    items = data.get("data", {}).get("items", [])
    if not items:
        return None

    fields = items[0].get("fields", {})
    # 从所有字段提取可搜索文本
    searchable_parts = [requirement_id]
    for key, val in fields.items():
        if val:
            if isinstance(val, str):
                searchable_parts.append(val)
            elif isinstance(val, list):
                for sub in val:
                    if isinstance(sub, dict):
                        searchable_parts.append(sub.get("en_name", sub.get("name", "")))
                    elif isinstance(sub, str):
                        searchable_parts.append(sub)
            elif isinstance(val, (int, float)):
                searchable_parts.append(str(val))

    return {
        "requirement_id": requirement_id,
        "title": str(fields.get(t("field.requirement_title"), fields.get(t("field.requirement_id"), requirement_id)))[:100],
        "searchable_text": " ".join(searchable_parts),
        "stage_data": _parse_stage_data(fields),
        "record_id": items[0].get("record_id", ""),
    }


def _parse_stage_data(fields: dict[str, Any]) -> dict[str, Any]:
    """从 Bitable 字段解析各阶段数据。字段名以 S1~S6 为前缀。"""
    stage_data = {}
    stage_prefixes = {
        "S1": ["S1", "Stage1", "售前"],
        "S2": ["S2", "Stage2", "产品"],
        "S3": ["S3", "Stage3", "研发"],
        "S4": ["S4", "Stage4", "发版"],
        "S5": ["S5", "Stage5", "反馈"],
        "S6": ["S6", "Stage6", "复盘"],
    }

    for stage, prefixes in stage_prefixes.items():
        stage_fields = {}
        for field_name, field_value in fields.items():
            for prefix in prefixes:
                if prefix in field_name:
                    stage_fields[field_name] = field_value
                    break
        if stage_fields:
            stage_data[stage] = stage_fields

    return stage_data
