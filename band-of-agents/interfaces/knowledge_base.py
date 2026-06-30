"""
knowledge_base.py — KnowledgeBaseInterface abstract definition.

Platform implementations provide knowledge record storage and retrieval.
Core business logic calls these methods to search history and read/write records.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    """A single search result from the knowledge base."""
    requirement_id: str
    title: str
    searchable_text: str
    stage_data: dict[str, Any] = field(default_factory=dict)
    product_model: str = ""
    similarity: float = 0.0
    record_id: str = ""


@dataclass
class RequirementChain:
    """A complete requirement chain (S1-S6)."""
    requirement_id: str
    title: str
    searchable_text: str
    stage_data: dict[str, Any] = field(default_factory=dict)
    record_id: str = ""


class KnowledgeBaseInterface(ABC):
    """Abstract interface for knowledge base operations."""

    @abstractmethod
    def search(
        self,
        keyword: str,
        top_k: int = 5,
        product_model: str = "",
    ) -> list[dict[str, Any]]:
        """Search historical requirement records.

        Args:
            keyword: Search keyword
            top_k: Maximum number of results
            product_model: If provided, filter by product model (hard constraint)

        Returns:
            List of requirement dicts with keys:
            requirement_id, title, searchable_text, stage_data, product_model, similarity

        Raises:
            KnowledgeBaseError: If the search fails. Returns empty list on no results.
        """
        ...

    @abstractmethod
    def get_chain(self, requirement_id: str) -> dict[str, Any] | None:
        """Get the complete S1-S6 chain for a requirement.

        Args:
            requirement_id: The requirement ID to look up

        Returns:
            Requirement dict with keys:
            requirement_id, title, searchable_text, stage_data, record_id
            Or None if not found.

        Raises:
            KnowledgeBaseError: If the query fails.
        """
        ...

    @abstractmethod
    def update_record(
        self,
        requirement_id: str,
        fields: dict[str, Any],
    ) -> bool:
        """Update a requirement record.

        Args:
            requirement_id: The requirement ID to update
            fields: Field name → value mapping to update

        Returns:
            True if successful, False otherwise.

        Raises:
            KnowledgeBaseError: If the update fails.
        """
        ...

    @abstractmethod
    def write_trace(
        self,
        trace: dict[str, Any],
    ) -> bool:
        """Write a feedback trace record.

        Args:
            trace: Trace data dict with keys:
            original_feedback, customer_id, diagnosis_type,
            matched_requirement_id, entry_stage, severity,
            routing_target, resolution

        Returns:
            True if successful, False otherwise.
        """
        ...

    @abstractmethod
    def write_archive(
        self,
        req_id: str,
        entry_type: str,
        stage: int = 0,
        content: dict[str, Any] | None = None,
    ) -> bool:
        """Write an archive entry to the knowledge base index table.

        This is the unified entry point for all 6 entry types:
        stage_output, human_correction, rejection_feedback,
        survey_design, feedback_analysis, retrospective.

        Args:
            req_id: Requirement ID
            entry_type: One of the 6 entry types
            stage: Pipeline stage number (0 for cross-stage)
            content: Arbitrary dict with stage-specific data

        Returns:
            True if successful, False otherwise.
        """
        ...


class KnowledgeBaseError(Exception):
    """Raised when a knowledge base operation fails."""
    pass
