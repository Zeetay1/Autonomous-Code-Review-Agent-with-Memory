"""Phase 1: Unified retrieval returns both collections with RetrievedMemory schema."""

from pathlib import Path

import pytest

from code_review_agent.memory.retrieval import retrieve
from code_review_agent.schemas import RetrievedMemory, ConventionEntry, PastDecisionEntry


def test_unified_retrieval_returns_both_collections(
    convention_memory,
    review_history_memory,
    fixtures_docs_path,
):
    """Unified interface returns both conventions and past_decisions in a single call."""
    convention_memory.index_file(fixtures_docs_path / "CONVENTIONS.md")
    review_history_memory.add(
        code_snippet="def bar(): pass",
        comment_text="Add docstring",
        outcome="accepted",
        file_path="d.py",
        severity="nit",
    )
    result = retrieve(
        "Use type hints for function arguments",
        convention_memory,
        review_history_memory,
        convention_top_k=3,
        past_decisions_top_k=3,
    )
    assert isinstance(result, RetrievedMemory)
    assert hasattr(result, "conventions")
    assert hasattr(result, "past_decisions")
    assert isinstance(result.conventions, list)
    assert isinstance(result.past_decisions, list)
    assert all(isinstance(c, ConventionEntry) for c in result.conventions)
    assert all(isinstance(p, PastDecisionEntry) for p in result.past_decisions)
    assert len(result.conventions) >= 1
    assert len(result.past_decisions) >= 0
