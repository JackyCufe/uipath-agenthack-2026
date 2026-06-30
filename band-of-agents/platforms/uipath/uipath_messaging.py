"""
uipath_messaging.py — UiPath Orchestrator implementation of MessagingInterface.

Sends Action Center tasks and listens for task completion callbacks.
Replaces Feishu WebSocket with UiPath Orchestrator API + webhook polling.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable, Awaitable

import requests

from interfaces.messaging import MessagingInterface, MessageCallback, MessagingError
from core.config import get_settings


class UiPathMessaging(MessagingInterface):
    """UiPath Orchestrator messaging implementation.

    - send_message: send text notification via Orchestrator queue item
    - send_card: create Action Center task (Action Center Form)
    - start_listening: poll Orchestrator queue for completed tasks
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}

    def _get_token(self) -> str:
        """Get OAuth2 access token."""
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
            raise MessagingError(f"Auth failed: {resp.status_code} {resp.text}")

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

    def send_message(self, recipient_id: str, content: str, **kwargs: Any) -> dict[str, Any]:
        """Send a text message as an Orchestrator queue item."""
        base_url = self._settings.uipath_orchestrator_url
        queue_name = kwargs.get("queue_name", "MindTheGapNotifications")

        try:
            resp = requests.post(
                f"{base_url}/orchestrator_/odata/Queues/UiPathODataSvc.AddQueueItem",
                headers=self._headers(),
                json={
                    "itemData": {
                        "Name": queue_name,
                        "Priority": "Normal",
                        "SpecificContent": {
                            "recipient_id": recipient_id,
                            "content": content,
                            "type": "text_message",
                        },
                    }
                },
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return {"ok": True, "message_id": str(data.get("Id", "")), "error": None}
            return {"ok": False, "message_id": "", "error": f"HTTP {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"ok": False, "message_id": "", "error": str(e)}

    def send_card(self, recipient_id: str, card: dict[str, Any]) -> dict[str, Any]:
        """Create an Action Center task from card JSON.

        The card dict (from UiPathCard) is converted to an Action Center task.
        recipient_id maps to the assigned user in Action Center.
        """
        base_url = self._settings.uipath_orchestrator_url
        task_title = card.get("title", "MindTheGap Task")
        task_type = card.get("type", "generic")

        try:
            resp = requests.post(
                f"{base_url}/orchestrator_/odata/Tasks",
                headers=self._headers(),
                json={
                    "Title": task_title,
                    "Type": task_type,
                    "Priority": "Medium",
                    "AssignedToUserId": recipient_id,
                    "Data": json.dumps(card),
                    "Status": "Unassigned",
                },
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return {"ok": True, "message_id": str(data.get("Id", "")), "error": None}
            return {"ok": False, "message_id": "", "error": f"HTTP {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"ok": False, "message_id": "", "error": str(e)}

    def start_listening(
        self,
        callback_handler: Callable[[MessageCallback], Awaitable[dict[str, Any]]],
    ) -> None:
        """Poll Orchestrator for completed Action Center tasks.

        This is a blocking call. In production, this would use Orchestrator
        webhooks instead of polling. For hackathon demo, polling is sufficient.
        """
        base_url = self._settings.uipath_orchestrator_url
        poll_interval = self._settings.uipath_poll_interval
        queue_name = "MindTheGapCallbacks"

        async def _poll_loop():
            processed_ids: set[str] = set()
            while True:
                try:
                    resp = requests.get(
                        f"{base_url}/orchestrator_/odata/QueueItems"
                        f"?$filter=QueueDefinitionName eq '{queue_name}' and Status eq 'Successful'"
                        f"&$top=10",
                        headers=self._headers(),
                    )
                    if resp.status_code == 200:
                        items = resp.json().get("value", [])
                        for item in items:
                            item_id = str(item.get("Id", ""))
                            if item_id in processed_ids:
                                continue
                            processed_ids.add(item_id)

                            content = item.get("Output", {}).get("SpecificContent", {})
                            callback = MessageCallback(
                                action=content.get("action", "unknown"),
                                value=content.get("value", {}),
                                form_data=content.get("form_data", {}),
                                operator_id=content.get("operator_id", ""),
                            )

                            result = await callback_handler(callback)
                            # Could send result back via Orchestrator if needed
                except Exception as e:
                    print(f"[UiPathMessaging] Poll error: {e}")

                await asyncio.sleep(poll_interval)

        # Run the polling loop
        asyncio.run(_poll_loop())
