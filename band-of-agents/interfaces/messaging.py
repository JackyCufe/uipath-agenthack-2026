"""
messaging.py — MessagingInterface abstract definition.

Platform implementations provide:
- send_message: send a text/card message to a recipient
- on_callback: register a callback for user interactions (button clicks, form submits)
- start_listening: begin listening for incoming messages/callbacks (blocking or background)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class MessageCallback:
    """Represents a callback from a user interaction (button click, form submit)."""
    action: str
    value: dict[str, Any] = field(default_factory=dict)
    form_data: dict[str, Any] = field(default_factory=dict)
    operator_id: str = ""


class MessagingInterface(ABC):
    """Abstract interface for sending and receiving messages."""

    @abstractmethod
    def send_message(self, recipient_id: str, content: str, **kwargs: Any) -> dict[str, Any]:
        """Send a text message to a recipient.

        Args:
            recipient_id: Platform-specific recipient identifier (open_id, channel_id, etc.)
            content: Message text content
            **kwargs: Platform-specific options

        Returns:
            {"ok": bool, "message_id": str, "error": str | None}

        Raises:
            MessagingError: If the send fails after retries.
        """
        ...

    @abstractmethod
    def send_card(self, recipient_id: str, card: dict[str, Any]) -> dict[str, Any]:
        """Send an interactive card to a recipient.

        Args:
            recipient_id: Platform-specific recipient identifier
            card: Platform-specific card JSON

        Returns:
            {"ok": bool, "message_id": str, "error": str | None}
        """
        ...

    @abstractmethod
    def start_listening(
        self,
        callback_handler: Callable[[MessageCallback], Awaitable[dict[str, Any]]],
    ) -> None:
        """Start listening for user interactions (blocking call).

        Args:
            callback_handler: Async function called when a user interacts with a card.
                Receives a MessageCallback, returns {"ok": bool, "message": str, "card": dict | None}.
        """
        ...


    @abstractmethod
    def reply_in_topic(
        self,
        root_message_id: str,
        content: str,
        msg_type: str = "text",
    ) -> dict[str, Any]:
        """Reply within a topic thread using the platform's reply API.

        Args:
            root_message_id: The message ID to reply to (thread root)
            content: Message content (text or card JSON string)
            msg_type: "text" or "interactive"

        Returns:
            {"ok": bool, "message_id": str, "error": str | None}
        """
        ...

    @abstractmethod
    def update_card(
        self,
        message_id: str,
        card_json: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an existing card message (e.g. disable interactive elements).

        Args:
            message_id: The card message ID to update
            card_json: New card JSON to replace the existing one

        Returns:
            {"ok": bool, "error": str | None}
        """
        ...

    @abstractmethod
    def get_chat_member_name(
        self,
        chat_id: str,
        open_id: str,
    ) -> str:
        """Look up a user's display name from chat membership.

        Used for external users who can't be queried via contact API.

        Args:
            chat_id: Chat group ID
            open_id: User's open_id

        Returns:
            Display name, or empty string if not found.
        """
        ...

    @abstractmethod
    def get_user_name(
        self,
        open_id: str,
        chat_ids: set[str] | None = None,
    ) -> str:
        """Look up a user's display name.

        Tries contact API first (internal users), then chat membership (external users).

        Args:
            open_id: User's open_id
            chat_ids: Known chat_ids to search for external users

        Returns:
            Display name, or empty string if not found.
        """
        ...


class MessagingError(Exception):
    """Raised when a messaging operation fails after retries."""
    pass
