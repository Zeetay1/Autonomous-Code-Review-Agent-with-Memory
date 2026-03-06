"""Unified retrieval: given a diff snippet, return conventions and past decisions in one call."""

from typing import TYPE_CHECKING

from code_review_agent.schemas import RetrievedMemory

if TYPE_CHECKING:
    from code_review_agent.memory.conventions import ConventionMemory
    from code_review_agent.memory.review_history import ReviewHistoryMemory


def retrieve(
    diff_snippet: str,
    convention_memory: "ConventionMemory",
    review_history_memory: "ReviewHistoryMemory",
    *,
    convention_top_k: int = 5,
    past_decisions_top_k: int = 5,
) -> RetrievedMemory:
    """
    Return relevant conventions and past decisions for the given diff snippet.
    Schema: RetrievedMemory(conventions=..., past_decisions=...).
    Past decisions are down-weighted by outcome and excluded if pattern has >= 5 rejections.
    """
    conventions = convention_memory.query(diff_snippet, top_k=convention_top_k)
    past_decisions = review_history_memory.query(diff_snippet, top_k=past_decisions_top_k)
    return RetrievedMemory(conventions=conventions, past_decisions=past_decisions)
