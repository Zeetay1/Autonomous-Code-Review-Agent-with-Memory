"""Phase 1: Review history memory - down-weighting and pattern rejection threshold."""

import pytest

from code_review_agent.memory.review_history import (
    ReviewHistoryMemory,
    pattern_id_from_snippet,
    REJECTION_THRESHOLD,
)


def test_rejected_scores_lower_than_accepted(
    review_history_memory, rejection_count_map
):
    """With two stored decisions of equal similarity, accepted ranks higher than rejected."""
    snippet = "def foo(x): return x"
    review_history_memory.add(
        code_snippet=snippet,
        comment_text="Add type hints",
        outcome="accepted",
        file_path="a.py",
        severity="warning",
    )
    review_history_memory.add(
        code_snippet=snippet,
        comment_text="Use a different style",
        outcome="rejected",
        file_path="a.py",
        severity="nit",
    )
    results = review_history_memory.query(snippet, top_k=5)
    assert len(results) >= 2
    # First result should be accepted (higher weight)
    assert results[0].outcome == "accepted"
    assert results[0].comment_text == "Add type hints"


def test_after_five_rejections_pattern_excluded(
    review_history_memory, rejection_count_map
):
    """After 5 rejections for a pattern, retrieval does not surface that pattern."""
    snippet = "print('hello')"
    pid = pattern_id_from_snippet(snippet)
    rejection_count_map[pid] = REJECTION_THRESHOLD  # 5
    review_history_memory.add(
        code_snippet=snippet,
        comment_text="Use logger",
        outcome="rejected",
        file_path="b.py",
        severity="warning",
    )
    results = review_history_memory.query(snippet, top_k=5)
    # Pattern has 5 rejections so should be filtered out (no results for this pattern)
    assert not any(p.pattern_id == pid for p in results)
    assert len(results) == 0  # only doc in collection was our pattern, so empty


def test_pattern_below_threshold_still_returned(
    review_history_memory, rejection_count_map
):
    """With fewer than 5 rejections, pattern is still returned."""
    snippet = "x = 1"
    pid = pattern_id_from_snippet(snippet)
    rejection_count_map[pid] = 2
    review_history_memory.add(
        code_snippet=snippet,
        comment_text="Use constant",
        outcome="rejected",
        file_path="c.py",
        severity="nit",
    )
    results = review_history_memory.query(snippet, top_k=5)
    assert len(results) >= 1
