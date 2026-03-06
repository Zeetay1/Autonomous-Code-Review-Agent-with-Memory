#!/usr/bin/env python3
"""
Demonstrate: after 5 rejections of a pattern, retrieval no longer surfaces it.
No live GitHub required. Uses in-memory Chroma and SQLite.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from code_review_agent.memory.embeddings import MockEmbeddingProvider, set_embedding_provider
from code_review_agent.memory.review_history import ReviewHistoryMemory, pattern_id_from_snippet
from code_review_agent.persistence.sqlite_store import SQLiteStore


def main() -> None:
    from code_review_agent.memory.embeddings import get_embedding_provider
    set_embedding_provider(MockEmbeddingProvider())
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = SQLiteStore(db_path)
    chroma_client = __import__("chromadb").EphemeralClient()
    review_memory = ReviewHistoryMemory(
        embedding_provider=get_embedding_provider(),
        get_rejection_count=store.get_pattern_rejection_count,
        client=chroma_client,
        collection_name="demo_review_history",
    )

    snippet = "print('hello world')"
    pid = pattern_id_from_snippet(snippet)

    # Add one document for this pattern
    review_memory.add(
        code_snippet=snippet,
        comment_text="Use logger instead",
        outcome="rejected",
        file_path="demo.py",
        severity="warning",
    )

    # Simulate 5 rejections for this pattern
    for _ in range(5):
        store.increment_pattern_rejection(pid)

    # Query with the same snippet: pattern has 5 rejections so must not appear
    results = review_memory.query(snippet, top_k=5)
    found = [r for r in results if r.pattern_id == pid]
    if found:
        print("FAIL: Pattern still surfaced after 5 rejections")
        sys.exit(1)
    print("OK: After 5 rejections, retrieval no longer surfaces the pattern.")
    sys.exit(0)


if __name__ == "__main__":
    main()
