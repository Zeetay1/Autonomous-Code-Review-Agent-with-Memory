"""seed_demo_data: populates sample review data once, idempotently."""

import chromadb
import pytest

from code_review_agent.demo_seed import seed_demo_data
from code_review_agent.memory.embeddings import MockEmbeddingProvider, set_embedding_provider
from code_review_agent.memory.review_history import ReviewHistoryMemory, pattern_id_from_snippet
from code_review_agent.persistence.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    return SQLiteStore(str(tmp_path / "seed_test.db"))


@pytest.fixture
def review_history_memory(store, request):
    set_embedding_provider(MockEmbeddingProvider())
    return ReviewHistoryMemory(
        MockEmbeddingProvider(),
        get_rejection_count=store.get_pattern_rejection_count,
        client=chromadb.EphemeralClient(),
        collection_name=f"seed_test_{request.node.name}",
    )


def test_seed_populates_reviews_and_returns_true(store, review_history_memory):
    seeded = seed_demo_data(store, review_history_memory)
    assert seeded is True
    with store._conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM review_comments").fetchone()[0]
    assert count == 4


def test_seed_pushes_a_pattern_past_the_rejection_threshold(store, review_history_memory):
    seed_demo_data(store, review_history_memory)
    snippet = "def f(x: List[str])"
    pid = pattern_id_from_snippet(snippet)
    assert store.get_pattern_rejection_count(pid) >= 5
    results = review_history_memory.query(snippet, top_k=5)
    assert not any(r.pattern_id == pid for r in results)


def test_seed_is_idempotent(store, review_history_memory):
    first = seed_demo_data(store, review_history_memory)
    second = seed_demo_data(store, review_history_memory)
    assert first is True
    assert second is False
    with store._conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM review_comments").fetchone()[0]
    assert count == 4
