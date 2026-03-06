"""Phase 4: Feedback loop - resolve/dismiss updates outcome and memory; 5 rejections exclude pattern."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from code_review_agent.api.app import create_app
from code_review_agent.memory.embeddings import MockEmbeddingProvider, set_embedding_provider
from code_review_agent.memory.review_history import ReviewHistoryMemory, pattern_id_from_snippet
from code_review_agent.persistence.sqlite_store import SQLiteStore
from code_review_agent.schemas import Comment


@pytest.fixture
def chroma_client():
    import chromadb
    return chromadb.EphemeralClient()


@pytest.fixture
def feedback_store(tmp_path):
    return SQLiteStore(str(tmp_path / "feedback.db"))


@pytest.fixture
def review_history_memory(chroma_client, feedback_store):
    set_embedding_provider(MockEmbeddingProvider())
    return ReviewHistoryMemory(
        embedding_provider=MockEmbeddingProvider(),
        get_rejection_count=feedback_store.get_pattern_rejection_count,
        client=chroma_client,
        collection_name="test_feedback_history",
    )


def test_resolving_comment_updates_outcome_and_writes_to_memory(
    feedback_store,
    review_history_memory,
):
    """Resolving a comment (accepted) updates SQLite outcome and adds to review_history."""
    ids = feedback_store.save_review("o/r#1", [
        Comment(file_path="a.py", line_number=1, severity="warning", comment_text="Add types", suggested_replacement=None),
    ])
    feedback_store.set_github_comment_id(ids[0], "gh_123")
    app = create_app(store=feedback_store, review_history_memory=review_history_memory)
    client = TestClient(app)
    resp = client.post("/api/feedback", json={"github_comment_id": "gh_123", "outcome": "accepted"})
    assert resp.status_code == 200
    rows = feedback_store.get_review_by_pr("o/r#1")
    assert rows[0]["outcome"] == "accepted"
    # Memory should have the entry (query for similar snippet)
    results = review_history_memory.query("a.py:1", top_k=3)
    assert any(r.outcome == "accepted" for r in results)


def test_dismissing_comment_updates_outcome_and_increments_pattern_rejection(
    feedback_store,
    review_history_memory,
):
    """Dismissing (rejected) updates outcome and increments pattern_rejection count."""
    ids = feedback_store.save_review("o/r#2", [
        Comment(file_path="b.py", line_number=2, severity="nit", comment_text="Optional", suggested_replacement=None),
    ])
    feedback_store.set_github_comment_id(ids[0], "gh_456")
    app = create_app(store=feedback_store, review_history_memory=review_history_memory)
    client = TestClient(app)
    resp = client.post("/api/feedback", json={"github_comment_id": "gh_456", "outcome": "rejected"})
    assert resp.status_code == 200
    rows = feedback_store.get_review_by_pr("o/r#2")
    assert rows[0]["outcome"] == "rejected"
    pid = pattern_id_from_snippet("b.py:2")
    assert feedback_store.get_pattern_rejection_count(pid) == 1


def test_after_five_rejections_retrieval_excludes_pattern(
    chroma_client,
    feedback_store,
):
    """After 5 rejections for a pattern, retrieval does not surface it."""
    set_embedding_provider(MockEmbeddingProvider())
    review_memory = ReviewHistoryMemory(
        embedding_provider=MockEmbeddingProvider(),
        get_rejection_count=feedback_store.get_pattern_rejection_count,
        client=chroma_client,
        collection_name="test_five_rejections",
    )
    snippet = "x = 1"
    pid = pattern_id_from_snippet(snippet)
    review_memory.add(snippet, "Use constant", "rejected", "c.py", "nit")
    for _ in range(5):
        feedback_store.increment_pattern_rejection(pid)
    results = review_memory.query(snippet, top_k=5)
    assert not any(r.pattern_id == pid for r in results)


def test_dashboard_renders_from_stored_data(feedback_store):
    """Dashboard loads and returns HTML with stats/reviews."""
    feedback_store.save_review("owner/repo#1", [
        Comment(file_path="x.py", line_number=1, severity="blocking", comment_text="Fix", suggested_replacement=None),
    ])
    app = create_app(store=feedback_store)
    client = TestClient(app)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text or "dashboard" in resp.text.lower()
    resp2 = client.get("/api/stats")
    assert resp2.status_code == 200
    data = resp2.json()
    assert "by_severity" in data
    assert data["by_severity"].get("blocking") == 1
