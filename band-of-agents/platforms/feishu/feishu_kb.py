"""
feishu_kb.py — Feishu Bitable implementation of KnowledgeBaseInterface.

Reads/writes requirement records from Feishu Bitable.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any

import requests

from interfaces.knowledge_base import KnowledgeBaseInterface, KnowledgeBaseError
from core.i18n import t
from core.config import get_settings


class FeishuKnowledgeBase(KnowledgeBaseInterface):
    """Feishu Bitable knowledge base implementation."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}

    def _get_token(self) -> str:
        """Get Feishu tenant_access_token with caching."""
        now = time.time()
        if self._token_cache["token"] and now < self._token_cache["expires_at"]:
            return self._token_cache["token"]

        resp = requests.post(
            f"{self._settings.feishu_base_url}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self._settings.feishu_app_id,
                "app_secret": self._settings.feishu_app_secret,
            },
        )
        data = resp.json()
        if "tenant_access_token" not in data:
            raise KnowledgeBaseError(f"Failed to get token: {data}")
        self._token_cache["token"] = data["tenant_access_token"]
        self._token_cache["expires_at"] = now + data["expire"] - 60
        return self._token_cache["token"]

    def search(self, keyword: str, top_k: int = 5, product_model: str = "") -> list[dict[str, Any]]:
        """Search Bitable historical requirements."""
        if not self._settings.bitable_app_token:
            return []

        token = self._get_token()
        params: dict[str, Any] = {"page_size": 50}
        if product_model:
            params["filter"] = f'CurrentValue.[{t("field.product_model")}]="{product_model}"'

        try:
            resp = requests.get(
                f"{self._settings.feishu_base_url}/bitable/v1/apps/{self._settings.bitable_app_token}/tables/{self._settings.effective_table_id}/records",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            data = resp.json()
            if data.get("code") != 0:
                return []
        except Exception as e:
            raise KnowledgeBaseError(f"Search failed: {e}")

        items = data.get("data", {}).get("items", [])
        results: list[dict[str, Any]] = []

        req_id_field = t("field.requirement_id")
        title_field = t("field.requirement_title")
        model_field = t("field.product_model")

        for item in items:
            fields = item.get("fields", {})
            req_id = str(fields.get(req_id_field, "")).strip()
            if not req_id:
                continue

            # Build searchable text
            parts = [req_id]
            for val in fields.values():
                if isinstance(val, str) and val:
                    parts.append(val)
                elif isinstance(val, list):
                    for sub in val:
                        if isinstance(sub, dict):
                            parts.append(sub.get("en_name", sub.get("name", "")))
                        elif isinstance(sub, str):
                            parts.append(sub)
                elif isinstance(val, (int, float)) and val:
                    parts.append(str(val))
            searchable_text = " ".join(parts)

            # Keyword matching: Chinese 2-4 char sliding window
            cn_chars = re.findall(r'[\u4e00-\u9fa5]+', keyword)
            keywords: set[str] = set()
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
                    "title": str(fields.get(title_field, fields.get(req_id_field, req_id)))[:100],
                    "searchable_text": searchable_text,
                    "stage_data": self._parse_stage_data(fields),
                    "record_id": item.get("record_id", ""),
                    "similarity": hit_count / len(keywords),
                    "product_model": str(fields.get(model_field, "")),
                })

        results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        return results[:top_k]

    def get_chain(self, requirement_id: str) -> dict[str, Any] | None:
        """Get full requirement chain by ID."""
        if not self._settings.bitable_app_token:
            return None

        token = self._get_token()
        filter_expr = f'CurrentValue.[{t("field.requirement_id")}]="{requirement_id}"'

        try:
            resp = requests.get(
                f"{self._settings.feishu_base_url}/bitable/v1/apps/{self._settings.bitable_app_token}/tables/{self._settings.effective_table_id}/records",
                headers={"Authorization": f"Bearer {token}"},
                params={"filter": filter_expr, "page_size": 1},
            )
            data = resp.json()
            if data.get("code") != 0:
                return None
        except Exception:
            return None

        items = data.get("data", {}).get("items", [])
        if not items:
            return None

        fields = items[0].get("fields", {})
        parts = [requirement_id]
        for val in fields.values():
            if isinstance(val, str) and val:
                parts.append(val)
            elif isinstance(val, list):
                for sub in val:
                    if isinstance(sub, dict):
                        parts.append(sub.get("en_name", sub.get("name", "")))
                    elif isinstance(sub, str):
                        parts.append(sub)
            elif isinstance(val, (int, float)) and val:
                parts.append(str(val))

        return {
            "requirement_id": requirement_id,
            "title": str(fields.get(t("field.requirement_title"), fields.get(t("field.requirement_id"), requirement_id)))[:100],
            "searchable_text": " ".join(parts),
            "stage_data": self._parse_stage_data(fields),
            "record_id": items[0].get("record_id", ""),
        }

    def update_record(self, requirement_id: str, fields: dict[str, Any]) -> bool:
        """Update a requirement record in Bitable."""
        if not self._settings.bitable_app_token:
            return False

        token = self._get_token()
        filter_expr = f'CurrentValue.[{t("field.requirement_id")}]="{requirement_id}"'

        try:
            resp = requests.get(
                f"{self._settings.feishu_base_url}/bitable/v1/apps/{self._settings.bitable_app_token}/tables/{self._settings.effective_table_id}/records",
                headers={"Authorization": f"Bearer {token}"},
                params={"filter": filter_expr, "page_size": 1},
            )
            data = resp.json()
            items = data.get("data", {}).get("items", [])
            if not items:
                return False

            record_id = items[0].get("record_id", "")
            resp = requests.put(
                f"{self._settings.feishu_base_url}/bitable/v1/apps/{self._settings.bitable_app_token}/tables/{self._settings.effective_table_id}/records/{record_id}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"fields": fields},
            )
            result = resp.json()
            return result.get("code") == 0
        except Exception:
            return False

    def write_trace(self, trace: dict[str, Any]) -> bool:
        """Write a feedback trace by updating the requirement record."""
        req_id = trace.get("matched_requirement_id", "")
        if not req_id:
            return False
        status = trace.get("resolution") or trace.get("diagnosis_type", "processed")
        return self.update_record(req_id, {
            t("field.current_stage"): t("callback.feedback_processed", status=status),
        })

    def _parse_stage_data(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Parse stage data from Bitable fields."""
        stage_data: dict[str, Any] = {}
        stage_prefixes = {
            "S1": ["S1", "Stage1", "售前"],
            "S2": ["S2", "Stage2", "产品"],
            "S3": ["S3", "Stage3", "研发"],
            "S4": ["S4", "Stage4", "发版"],
            "S5": ["S5", "Stage5", "反馈"],
            "S6": ["S6", "Stage6", "复盘"],
        }
        for stage, prefixes in stage_prefixes.items():
            stage_fields: dict[str, Any] = {}
            for field_name, field_value in fields.items():
                for prefix in prefixes:
                    if prefix in field_name:
                        stage_fields[field_name] = field_value
                        break
            if stage_fields:
                stage_data[stage] = stage_fields
        return stage_data
