"""
feishu_messaging.py — Feishu messaging implementation of MessagingInterface.

Sends messages/cards via Feishu API and listens for card callbacks via WebSocket.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable, Awaitable

import requests

from interfaces.messaging import MessagingInterface, MessageCallback, MessagingError
from core.i18n import t
from core.config import get_settings


class FeishuMessaging(MessagingInterface):
    """Feishu/Lark messaging implementation."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}

    def _get_token(self) -> str:
        import time
        now = time.time()
        if self._token_cache["token"] and now < self._token_cache["expires_at"]:
            return self._token_cache["token"]
        resp = requests.post(
            f"{self._settings.feishu_base_url}/auth/v3/tenant_access_token/internal",
            json={"app_id": self._settings.feishu_app_id, "app_secret": self._settings.feishu_app_secret},
        )
        data = resp.json()
        self._token_cache["token"] = data["tenant_access_token"]
        self._token_cache["expires_at"] = now + data["expire"] - 60
        return self._token_cache["token"]

    def send_message(self, recipient_id: str, content: str, **kwargs: Any) -> dict[str, Any]:
        """Send a text message to a recipient."""
        token = self._get_token()
        try:
            resp = requests.post(
                f"{self._settings.feishu_base_url}/im/v1/messages",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                params={"receive_id_type": "open_id"},
                json={"receive_id": recipient_id, "msg_type": "text", "content": json.dumps({"text": content})},
            )
            data = resp.json()
            if data.get("code") != 0:
                return {"ok": False, "message_id": "", "error": data.get("msg", "unknown")}
            return {"ok": True, "message_id": data.get("data", {}).get("message_id", ""), "error": None}
        except Exception as e:
            return {"ok": False, "message_id": "", "error": str(e)}

    def send_card(self, recipient_id: str, card: dict[str, Any]) -> dict[str, Any]:
        """Send an interactive card to a recipient."""
        if not recipient_id:
            return {"ok": False, "message_id": "", "error": "no recipient_id"}

        token = self._get_token()
        try:
            resp = requests.post(
                f"{self._settings.feishu_base_url}/im/v1/messages",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                params={"receive_id_type": "open_id"},
                json={"receive_id": recipient_id, "msg_type": "interactive", "content": json.dumps(card)},
            )
            data = resp.json()
            if data.get("code") != 0:
                return {"ok": False, "message_id": "", "error": data.get("msg", "unknown")}
            return {"ok": True, "message_id": data.get("data", {}).get("message_id", ""), "error": None}
        except Exception as e:
            return {"ok": False, "message_id": "", "error": str(e)}

    def start_listening(
        self,
        callback_handler: Callable[[MessageCallback], Awaitable[dict[str, Any]]],
    ) -> None:
        """Start WebSocket listener for card callbacks (blocking)."""
        try:
            import lark_oapi as lark
        except ImportError:
            print("⚠️ lark_oapi not installed. Install with: pip install lark-oapi")
            return

        def _handler(data: Any) -> Any:
            try:
                from lark_oapi.event.callback.model.p2_card_action_trigger import (
                    P2CardActionTriggerResponse, CallBackToast, CallBackCard
                )
            except ImportError:
                return None

            try:
                event = getattr(data, "event", None) or data
                action_obj = getattr(event, "action", None)
                value = getattr(action_obj, "value", {}) or {} if action_obj else {}
                form_value = getattr(action_obj, "form_value", {}) or {} if action_obj else {}
                operator = getattr(event, "operator", None)
                operator_open_id = getattr(operator, "open_id", "") if operator else ""

                callback = MessageCallback(
                    action=value.get("action", "") if isinstance(value, dict) else "",
                    value=value if isinstance(value, dict) else {},
                    form_data=form_value if isinstance(form_value, dict) else {},
                    operator_id=operator_open_id,
                )

                import asyncio
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(callback_handler(callback))
                loop.close()

                resp = P2CardActionTriggerResponse()
                if result.get("ok"):
                    toast = CallBackToast()
                    toast.type = "success"
                    toast.content = result.get("message", "OK")
                    resp.toast = toast
                else:
                    toast = CallBackToast()
                    toast.type = "error"
                    toast.content = result.get("message", "Error")
                    resp.toast = toast
                return resp
            except Exception as exc:
                print(f"[feishu_messaging] Callback error: {exc}")
                return None

        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_card_action_trigger(_handler)
            .register_p2_im_message_receive_v1(lambda data: None)
            .register_p2_im_message_message_read_v1(lambda data: None)
            .build()
        )

        ws_client = lark.ws.Client(
            self._settings.feishu_app_id,
            self._settings.feishu_app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.WARNING,
        )
        print("=" * 55)
        print("  Feishu Messaging — WebSocket Listener")
        print(f"  App ID: {self._settings.feishu_app_id}")
        print("  Listening for card callbacks...")
        print("=" * 55)
        ws_client.start()
