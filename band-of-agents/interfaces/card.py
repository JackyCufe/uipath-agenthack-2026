"""
card.py — CardInterface abstract definition.

Platform implementations provide card construction and rendering.
Core business logic calls these methods with platform-agnostic CardData,
and the implementation translates to platform-specific card JSON.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CardAction:
    """A button action on a card."""
    action: str
    label: str
    button_type: str = "default"  # "primary" | "default"
    value: dict[str, Any] = field(default_factory=dict)


@dataclass
class CardData:
    """Platform-agnostic card data. Implementations translate to platform-specific JSON."""
    title: str
    template: str = "blue"  # "blue" | "yellow" | "red" | "green" | "grey" | "orange"
    sections: list[dict[str, Any]] = field(default_factory=list)
    # Each section: {"type": "field_row" | "text" | "markdown" | "divider" | "actions",
    #                 "label": str, "value": str, "actions": [CardAction], ...}
    actions: list[CardAction] = field(default_factory=list)


class CardInterface(ABC):
    """Abstract interface for building and rendering interactive cards."""

    @abstractmethod
    def build_routing_card(
        self,
        feedback_text: str,
        customer_id: str,
        diagnosis_type: str,
        matched_requirement_id: str | None,
        entry_stage: int,
        severity: str,
        entry_reason: str,
        context_summary: str,
        role_name: str,
        actions: list[CardAction] | None = None,
    ) -> dict[str, Any]:
        """Build a routing notification card.

        Args:
            feedback_text: Original customer feedback
            customer_id: Customer identifier
            diagnosis_type: One of tech_bug, service_issue, new_requirement, complaint
            matched_requirement_id: Matched requirement ID or None
            entry_stage: Entry stage number (1-6)
            severity: urgent, normal, or low
            entry_reason: AI-generated routing reason
            context_summary: AI-generated context summary
            role_name: Role name of the handler
            actions: List of card actions (buttons). If None, default actions are used.

        Returns:
            Platform-specific card JSON.
        """
        ...

    @abstractmethod
    def build_confirm_card(
        self,
        feedback_text: str,
        product_model: str,
        customer_id: str,
        ai_summary: str,
    ) -> dict[str, Any]:
        """Build a customer confirmation card.

        Args:
            feedback_text: Original customer feedback
            product_model: Product model string
            customer_id: Customer identifier
            ai_summary: AI-generated summary of the feedback

        Returns:
            Platform-specific card JSON.
        """
        ...

    @abstractmethod
    def build_resolved_card(
        self,
        customer_id: str,
        requirement_id: str,
        resolved_by: str,
        resolution_note: str,
    ) -> dict[str, Any]:
        """Build a resolution notification card for the customer.

        Args:
            customer_id: Customer identifier
            requirement_id: Related requirement ID
            resolved_by: Name of the resolver
            resolution_note: Resolution note text

        Returns:
            Platform-specific card JSON.
        """
        ...

    @abstractmethod
    def build_knowledge_card(
        self,
        keyword: str,
        requirement: dict[str, Any],
        ai_summary: str,
    ) -> dict[str, Any]:
        """Build a knowledge query result card.

        Args:
            keyword: Search keyword
            requirement: Full requirement record with stage_data
            ai_summary: AI-generated summary

        Returns:
            Platform-specific card JSON.
        """
        ...

    @abstractmethod
    def build_transfer_card(
        self,
        requirement_id: str,
        feedback_text: str,
        contacts: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Build a transfer card for selecting a colleague.

        Args:
            requirement_id: Related requirement ID
            feedback_text: Original feedback text
            contacts: List of {"name": str, "open_id": str} for transfer targets

        Returns:
            Platform-specific card JSON.
        """
        ...

    # ── New flow: customer feedback confirmation + staff routing ───────────

    @abstractmethod
    def build_customer_feedback_card(
        self,
        feedback_text: str,
        diagnosis_type: str,
        topic_id: str = "",
        customer_name: str = "",
    ) -> dict[str, Any]:
        """Build a customer feedback confirmation card.

        Customer sees this card in the topic thread and confirms
        product line + feedback type + feedback content before submission.

        Args:
            feedback_text: Original customer feedback (pre-filled)
            diagnosis_type: AI-diagnosed type (tech_bug, new_requirement, usage_question)
            topic_id: Topic/thread ID for callback routing
            customer_name: Customer display name

        Returns:
            Platform-specific card JSON with form fields and submit button.
        """
        ...

    @abstractmethod
    def build_customer_feedback_card_disabled(
        self,
        feedback_text: str,
        diagnosis_type: str,
        product_line: str,
        customer_name: str = "",
    ) -> dict[str, Any]:
        """Build the disabled state of customer feedback card after submission.

        Shows the submitted content but removes interactive elements.

        Args:
            feedback_text: Confirmed feedback text
            diagnosis_type: Confirmed diagnosis type
            product_line: Confirmed product line
            customer_name: Customer display name

        Returns:
            Platform-specific card JSON with no interactive elements.
        """
        ...

    @abstractmethod
    def build_staff_routing_card(
        self,
        feedback_text: str,
        diagnosis_type: str,
        product_line: str,
        customer_name: str,
        topic_id: str,
        entry_reason: str = "",
    ) -> dict[str, Any]:
        """Build a staff routing card sent P2P to the handler.

        Staff sees customer info + feedback + reply input box.

        Args:
            feedback_text: Customer's confirmed feedback
            diagnosis_type: Confirmed diagnosis type
            product_line: Confirmed product line
            customer_name: Customer display name
            topic_id: Topic ID for callback routing
            entry_reason: AI-generated diagnosis explanation

        Returns:
            Platform-specific card JSON with reply input and submit button.
        """
        ...

    @abstractmethod
    def build_staff_routing_card_disabled(
        self,
        feedback_text: str,
        diagnosis_type: str,
        product_line: str,
        customer_name: str,
        reply_text: str,
        entry_reason: str = "",
    ) -> dict[str, Any]:
        """Build the disabled state of staff routing card after reply.

        Shows original content + the reply sent to customer, no interactive elements.

        Args:
            feedback_text: Original feedback
            diagnosis_type: Diagnosis type
            product_line: Product line
            customer_name: Customer name
            reply_text: The reply that was sent to customer
            entry_reason: AI diagnosis explanation

        Returns:
            Platform-specific card JSON with no interactive elements.
        """
        ...

    @abstractmethod
    def build_simple_disabled_card(
        self,
        text: str = "✅ 已提交",
    ) -> dict[str, Any]:
        """Build a minimal disabled card with just a text message.

        Used as fallback when no specific disabled card is available.

        Args:
            text: Text to display

        Returns:
            Platform-specific card JSON with no interactive elements.
        """
        ...


class CardError(Exception):
    """Raised when card construction fails."""
    pass
