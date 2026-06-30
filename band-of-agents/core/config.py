"""
config.py — Centralized configuration via pydantic-settings.

All configuration in one place. No scattered os.environ.get() in business code.
Platform implementations read from this Settings object.
"""
from __future__ import annotations

import os
from typing import Any

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Central configuration for the entire system."""

    # ── LLM ──
    llm_api_key: str = Field(default="", validation_alias="DEEPSEEK_API_KEY")
    llm_base_url: str = Field(default="https://api.deepseek.com", validation_alias="DEEPSEEK_BASE_URL")
    llm_model: str = Field(default="deepseek-chat", validation_alias="DEEPSEEK_MODEL")

    # ── Language ──
    lang: str = Field(default="zh", validation_alias="LANG")

    # ── Feishu/Lark ──
    feishu_app_id: str = Field(default="", validation_alias="FEISHU_APP_ID")
    feishu_app_secret: str = Field(default="", validation_alias="FEISHU_APP_SECRET")
    feishu_base_url: str = Field(default="https://open.feishu.cn/open-apis", validation_alias="FEISHU_BASE_URL")
    feishu_env: str = Field(default="team-testing", validation_alias="FEISHU_ENV")

    # ── Bitable ──
    bitable_app_token: str = Field(default="", validation_alias="BITABLE_APP_TOKEN")
    bitable_table_id: str = Field(default="", validation_alias="BITABLE_TABLE_ID")
    demo_bitable_table_id: str = Field(default="", validation_alias="DEMO_BITABLE_TABLE_ID")

    # ── Default owner ──
    jacky_open_id: str = Field(default="", validation_alias="JACKY_OPEN_ID")

    # ── Band (optional) ──
    band_routing_agent_id: str = Field(default="", validation_alias="BAND_ROUTING_AGENT_ID")
    band_routing_api_key: str = Field(default="", validation_alias="BAND_ROUTING_API_KEY")
    band_engineering_agent_id: str = Field(default="", validation_alias="BAND_ENGINEERING_AGENT_ID")
    band_engineering_api_key: str = Field(default="", validation_alias="BAND_ENGINEERING_API_KEY")
    band_knowledge_agent_id: str = Field(default="", validation_alias="BAND_KNOWLEDGE_AGENT_ID")
    band_knowledge_api_key: str = Field(default="", validation_alias="BAND_KNOWLEDGE_API_KEY")

    # ── UiPath ──
    uipath_auth_url: str = Field(default="https://cloud.uipath.com/identity", validation_alias="UIPATH_AUTH_URL")
    uipath_orchestrator_url: str = Field(default="", validation_alias="UIPATH_ORCHESTRATOR_URL")
    uipath_client_id: str = Field(default="", validation_alias="UIPATH_CLIENT_ID")
    uipath_client_secret: str = Field(default="", validation_alias="UIPATH_CLIENT_SECRET")
    uipath_auth_scope: str = Field(default="OR.Machine", validation_alias="UIPATH_AUTH_SCOPE")
    uipath_folder_id: str = Field(default="", validation_alias="UIPATH_FOLDER_ID")
    uipath_dataservice_url: str = Field(default="", validation_alias="UIPATH_DATASERVICE_URL")
    uipath_requirement_entity: str = Field(default="", validation_alias="UIPATH_REQUIREMENT_ENTITY")
    uipath_poll_interval: int = Field(default=5, validation_alias="UIPATH_POLL_INTERVAL")

    @property
    def effective_table_id(self) -> str:
        """Return demo table ID if set, otherwise regular table ID."""
        return self.demo_bitable_table_id or self.bitable_table_id

    def load_env_file(self) -> None:
        """Load .env file from pipeline directory into os.environ."""
        _pipeline_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "ai-requirement-pipeline", "pipeline"
        )
        _env_file = os.path.join(_pipeline_dir, f".env.{self.feishu_env}")
        if os.path.exists(_env_file):
            with open(_env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        os.environ.setdefault(k.strip(), v.strip())

        # Also load band env if exists
        _band_env = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "band-routing", ".env.band"
        )
        if os.path.exists(_band_env):
            with open(_band_env) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        os.environ.setdefault(k.strip(), v.strip())

    model_config = {"extra": "ignore", "env_file": None}


# Global singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the global Settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.load_env_file()
        # Reload after env file is loaded
        _settings = Settings()
    return _settings
