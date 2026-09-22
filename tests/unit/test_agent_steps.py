"""Phase 2: Unit tests for each agent step in isolation with mock inputs."""

import json
from unittest.mock import MagicMock

import pytest

from code_review_agent.agent.steps import (
    KEY_ANALYSIS,
    KEY_COMMENTS,
    KEY_DIFF,
    KEY_EXISTING_PR_COMMENTS,
    KEY_FORMATTED,
    KEY_PR_REFERENCE,
    KEY_RETRIEVED_MEMORY,
    analyze_step,
    format_step,
    generate_step,
    retrieve_step,
)
from code_review_agent.schemas import Comment, ReviewOutput, RetrievedMemory


def test_retrieve_step_returns_retrieved_memory(
    convention_memory, review_history_memory, fixtures_docs_path
):
    """Retrieve step puts RetrievedMemory in state."""
    convention_memory.index_file(fixtures_docs_path / "CONVENTIONS.md")
    state = {KEY_DIFF: "def foo(x): pass"}
    out = retrieve_step(state, convention_memory, review_history_memory)
    assert KEY_RETRIEVED_MEMORY in out
    assert isinstance(out[KEY_RETRIEVED_MEMORY], RetrievedMemory)
    assert hasattr(out[KEY_RETRIEVED_MEMORY], "conventions")
    assert hasattr(out[KEY_RETRIEVED_MEMORY], "past_decisions")


def test_retrieve_step_fetches_existing_pr_comments_when_pr_reference_given(
    convention_memory, review_history_memory
):
    """A PR being re-reviewed (e.g. new commit pushed) surfaces its own past comments."""
    get_existing = MagicMock(return_value=["Mutable default argument", "Missing docstring"])
    state = {KEY_DIFF: "def foo(x): pass", KEY_PR_REFERENCE: "owner/repo#5"}
    out = retrieve_step(
        state, convention_memory, review_history_memory, get_existing_pr_comments=get_existing
    )
    get_existing.assert_called_once_with("owner/repo#5")
    assert out[KEY_EXISTING_PR_COMMENTS] == ["Mutable default argument", "Missing docstring"]


def test_retrieve_step_skips_existing_pr_lookup_without_pr_reference(
    convention_memory, review_history_memory
):
    """No pr_reference (e.g. the CLI harness) means no lookup at all -- not even called."""
    get_existing = MagicMock(return_value=["should not be returned"])
    state = {KEY_DIFF: "def foo(x): pass"}
    out = retrieve_step(
        state, convention_memory, review_history_memory, get_existing_pr_comments=get_existing
    )
    get_existing.assert_not_called()
    assert out[KEY_EXISTING_PR_COMMENTS] == []


def test_analyze_step_includes_existing_pr_comments_in_prompt():
    """Already-flagged comments on this PR reach the LLM prompt, so it can avoid repeats."""
    mock_llm = MagicMock(return_value="[]")
    state = {
        KEY_DIFF: "def foo(x): pass",
        KEY_RETRIEVED_MEMORY: RetrievedMemory(conventions=[], past_decisions=[]),
        KEY_EXISTING_PR_COMMENTS: ["Mutable default argument on line 3"],
    }
    analyze_step(state, mock_llm)
    prompt = mock_llm.call_args.args[0]
    assert "Mutable default argument on line 3" in prompt
    assert "Already flagged" in prompt


def test_analyze_step_returns_analysis_with_mock_llm():
    """Analyze step calls LLM and returns analysis string (JSON array)."""
    mock_llm = MagicMock(return_value='[{"file_path":"a.py","line_number":1,"severity":"warning","comment_text":"Add type hints"}]')
    state = {
        KEY_DIFF: "def foo(x): pass",
        KEY_RETRIEVED_MEMORY: RetrievedMemory(conventions=[], past_decisions=[]),
    }
    out = analyze_step(state, mock_llm)
    assert KEY_ANALYSIS in out
    assert "file_path" in out[KEY_ANALYSIS] or "a.py" in out[KEY_ANALYSIS]
    mock_llm.assert_called_once()


def test_generate_step_parses_json_into_comments():
    """Generate step parses analysis JSON into Comment list."""
    analysis = json.dumps([
        {"file_path": "b.py", "line_number": 10, "severity": "blocking", "comment_text": "Fix this"},
        {"file_path": "b.py", "line_number": 11, "severity": "nit", "comment_text": "Optional"},
    ])
    state = {KEY_ANALYSIS: analysis}
    out = generate_step(state)
    assert KEY_COMMENTS in out
    comments = out[KEY_COMMENTS]
    assert len(comments) == 2
    assert all(isinstance(c, Comment) for c in comments)
    assert comments[0].severity == "blocking"
    assert comments[1].severity == "nit"


def test_format_step_caps_blocking_at_three():
    """A diff with 5 blocking issues produces exactly 3 blocking and 2 warnings."""
    five_blocking = [
        Comment(file_path="f.py", line_number=i, severity="blocking", comment_text=f"Issue {i}", suggested_replacement=None)
        for i in range(1, 6)
    ]
    state = {KEY_COMMENTS: five_blocking}
    out = format_step(state)
    assert KEY_FORMATTED in out
    ro = out[KEY_FORMATTED]
    assert isinstance(ro, ReviewOutput)
    assert ro.summary.blocking_count == 3
    assert ro.summary.warning_count == 2
    assert ro.summary.nit_count == 0
    assert ro.summary.total_comments == 5
    blocking_severities = [c.severity for c in ro.comments]
    assert blocking_severities.count("blocking") == 3
    assert blocking_severities.count("warning") == 2


def test_format_step_produces_valid_review_output_schema():
    """Format step output is valid ReviewOutput with Comment and ReviewSummary."""
    state = {
        KEY_COMMENTS: [
            Comment(file_path="x.py", line_number=1, severity="nit", comment_text="Minor", suggested_replacement=None),
        ],
    }
    out = format_step(state)
    ro = out[KEY_FORMATTED]
    assert ro.summary.total_comments == 1
    assert ro.summary.nit_count == 1
    assert ro.comments[0].comment_text == "Minor"
