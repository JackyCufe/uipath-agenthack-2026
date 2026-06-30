"""
uipath_kb.py — UiPath Data Service implementation of KnowledgeBaseInterface.

Stores/retrieves requirement records via UiPath Data Service REST API.
Replaces Feishu Bitable with Data Service Entities.

Auth: OAuth2 client credentials (external application registered in Automation Cloud).
API docs: https://docs.uipath.com/data-service
"""
from __future__ import annotations

import re
import time
from typing import Any

import requests

from interfaces.knowledge_base import KnowledgeBaseInterface, KnowledgeBaseError
from core.config import get_settings


class UiPathKnowledgeBase(KnowledgeBaseInterface):
    """UiPath Data Service knowledge base implementation."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}

    def _get_token(self) -> str:
        """Get OAuth2 access token from UiPath Automation Cloud."""
        now = time.time()
        if self._token_cache["token"] and now < self._token_cache["expires_at"]:
            return self._token_cache["token"]

        settings = self._settings
        resp = requests.post(
            f"{settings.uipath_auth_url}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.uipath_client_id,
                "client_secret": settings.uipath_client_secret,
                "scope": settings.uipath_auth_scope,
            },
        )
        if resp.status_code != 200:
            raise KnowledgeBaseError(f"Auth failed: {resp.status_code} {resp.text}")

        data = resp.json()
        self._token_cache["token"] = data["access_token"]
        self._token_cache["expires_at"] = now + data.get("expires_in", 3600) - 60
        return self._token_cache["token"]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
            "X-UIPATH-OrganizationUnitId": self._settings.uipath_folder_id,
        }

    def search(self, keyword: str, top_k: int = 5, product_model: str = "") -> list[dict[str, Any]]:
        """Search historical requirements in Data Service."""
        base_url = self._settings.uipath_dataservice_url
        entity = self._settings.uipath_requirement_entity

        # Build OData filter
        filters = []
        if product_model:
            filters.append(f"ProductModel eq '{product_model}'")

        params: dict[str, Any] = {"$top": 50}
        if filters:
            params["$filter"] = " and ".join(filters)

        try:
            resp = requests.get(
                f"{base_url}/DataService/Entities({entity})/records",
                headers=self._headers(),
                params=params,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            items = data.get("value", [])
        except Exception as e:
            raise KnowledgeBaseError(f"Search failed: {e}")

        # Keyword matching (same logic as Feishu implementation)
        results: list[dict[str, Any]] = []
        cn_chars = re.findall(r'[\u4e00-\u9fa5]+', keyword)
        keywords: set[str] = set()
        for seg in cn_chars:
            for length in (2, 3, 4):
                for i in range(len(seg) - length + 1):
                    keywords.add(seg[i:i + length])
        en_words = re.findall(r'[a-zA-Z]{3,}', keyword.lower())
        keywords.update(en_words)
        if not keywords:
            keywords = {keyword.lower()}

        for item in items:
            req_id = str(item.get("RequirementId", "")).strip()
            if not req_id:
                continue

            # Build searchable text from all string fields
            parts = [req_id]
            for val in item.values():
                if isinstance(val, str) and val:
                    parts.append(val)
                elif isinstance(val, (int, float)) and val:
                    parts.append(str(val))
            searchable_text = " ".join(parts)

            text_lower = searchable_text.lower()
            hit_count = sum(1 for kw in keywords if kw.lower() in text_lower)
            if hit_count > 0:
                results.append({
                    "requirement_id": req_id,
                    "title": str(item.get("Title", req_id))[:100],
                    "searchable_text": searchable_text,
                    "stage_data": self._parse_stage_data(item),
                    "record_id": str(item.get("Id", "")),
                    "similarity": hit_count / len(keywords),
                    "product_model": str(item.get("ProductModel", "")),
                })

        results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        return results[:top_k]

    def get_chain(self, requirement_id: str) -> dict[str, Any] | None:
        """Get full requirement chain by ID."""
        base_url = self._settings.uipath_dataservice_url
        entity = self._settings.uipath_requirement_entity

        try:
            resp = requests.get(
                f"{base_url}/DataService/Entities({entity})/records",
                headers=self._headers(),
                params={"$filter": f"RequirementId eq '{requirement_id}'", "$top": 1},
            )
            if resp.status_code != 200:
                return None

            items = resp.json().get("value", [])
            if not items:
                return None

            item = items[0]
            parts = [requirement_id]
            for val in item.values():
                if isinstance(val, str) and val:
                    parts.append(val)
                elif isinstance(val, (int, float)) and val:
                    parts.append(str(val))

            return {
                "requirement_id": requirement_id,
                "title": str(item.get("Title", requirement_id))[:100],
                "searchable_text": " ".join(parts),
                "stage_data": self._parse_stage_data(item),
                "record_id": str(item.get("Id", "")),
            }
        except Exception:
            return None

    def update_record(self, requirement_id: str, fields: dict[str, Any]) -> bool:
        """Update a requirement record in Data Service."""
        base_url = self._settings.uipath_dataservice_url
        entity = self._settings.uipath_requirement_entity

        # First find the record ID
        try:
            resp = requests.get(
                f"{base_url}/DataService/Entities({entity})/records",
                headers=self._headers(),
                params={"$filter": f"RequirementId eq '{requirement_id}'", "$top": 1},
            )
            items = resp.json().get("value", [])
            if not items:
                return False

            record_id = items[0].get("Id")
            resp = requests.put(
                f"{base_url}/DataService/Entities({entity})/records({record_id})",
                headers=self._headers(),
                json=fields,
            )
            return resp.status_code in (200, 204)
        except Exception:
            return False

    def write_trace(self, trace: dict[str, Any]) -> bool:
        """Write a feedback trace record."""
        req_id = trace.get("matched_requirement_id", "")
        if not req_id:
            return False

        status = trace.get("resolution") or trace.get("diagnosis_type", "processed")
        return self.update_record(req_id, {
            "CurrentStage": f"Feedback processed: {status}",
        })

    def _parse_stage_data(self, record: dict[str, Any]) -> dict[str, Any]:
        """Parse stage data from Data Service record fields."""
        stage_data: dict[str, Any] = {}
        stage_prefixes = {
            "S1": ["S1", "Stage1", "Gatekeeping"],
            "S2": ["S2", "Stage2", "ValueTransform", "PM"],
            "S3": ["S3", "Stage3", "Engineering", "Dev"],
            "S4": ["S4", "Stage4", "Release"],
            "S5": ["S5", "Stage5", "Feedback"],
            "S6": ["S6", "Stage6", "Retrospective"],
        }
        for stage, prefixes in stage_prefixes.items():
            stage_fields: dict[str, Any] = {}
            for field_name, field_value in record.items():
                for prefix in prefixes:
                    if prefix in field_name:
                        stage_fields[field_name] = field_value
                        break
            if stage_fields:
                stage_data[stage] = stage_fields
        return stage_data
