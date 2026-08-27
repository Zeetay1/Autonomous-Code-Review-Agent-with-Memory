#!/usr/bin/env python3
"""Manually seed sample review data into the configured SQLite/Chroma stores.

Useful for trying the dashboard locally without a real GitHub PR + Anthropic key.
The hosted demo deployment does this automatically at startup via SEED_DEMO_DATA=1.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from code_review_agent.config import get_chroma_path, get_db_path
from code_review_agent.demo_seed import seed_demo_data
from code_review_agent.memory.embeddings import get_embedding_provider
from code_review_agent.memory.review_history import ReviewHistoryMemory
from code_review_agent.persistence.sqlite_store import SQLiteStore


def main() -> None:
    store = SQLiteStore(get_db_path())
    embed = get_embedding_provider()
    review_history_memory = ReviewHistoryMemory(
        embed,
        get_rejection_count=store.get_pattern_rejection_count,
        persist_directory=get_chroma_path(),
    )
    seeded = seed_demo_data(store, review_history_memory)
    if seeded:
        print("Seeded sample review data.")
    else:
        print("review_comments already has data; skipped (idempotent).")


if __name__ == "__main__":
    main()
