#!/usr/bin/env python3
"""Local test harness: read diff from file, run full agent pipeline, print structured review. No GitHub required."""

import argparse
import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from code_review_agent.agent.graph import create_review_graph
from code_review_agent.agent.llm import complete as llm_complete
from code_review_agent.config import get_chroma_path, get_db_path
from code_review_agent.memory.embeddings import get_embedding_provider
from code_review_agent.memory.conventions import ConventionMemory
from code_review_agent.memory.review_history import ReviewHistoryMemory
from code_review_agent.persistence.sqlite_store import SQLiteStore


def main() -> None:
    ap = argparse.ArgumentParser(description="Run code review agent on a diff file")
    ap.add_argument("diff_file", type=Path, help="Path to .diff file")
    ap.add_argument("--mock-llm", action="store_true", help="Use mock LLM (no API key)")
    ap.add_argument("--json", action="store_true", help="Output as JSON")
    args = ap.parse_args()
    diff_path = args.diff_file
    if not diff_path.exists():
        print(f"Error: {diff_path} not found", file=sys.stderr)
        sys.exit(1)
    diff = diff_path.read_text(encoding="utf-8", errors="replace")

    if args.mock_llm:
        from unittest.mock import MagicMock
        from code_review_agent.memory.embeddings import MockEmbeddingProvider, set_embedding_provider
        set_embedding_provider(MockEmbeddingProvider())
        llm = MagicMock(return_value='[{"file_path":"a.py","line_number":1,"severity":"nit","comment_text":"Sample"}]')
    else:
        llm = llm_complete

    db_path = os.environ.get("CODE_REVIEW_AGENT_DB_PATH", ":memory:")
    chroma_path = get_chroma_path()
    store = SQLiteStore(db_path)
    embed = get_embedding_provider()
    convention_memory = ConventionMemory(embed, persist_directory=chroma_path)
    review_history_memory = ReviewHistoryMemory(
        embed,
        get_rejection_count=store.get_pattern_rejection_count,
        persist_directory=chroma_path,
    )
    graph = create_review_graph(convention_memory, review_history_memory, llm)
    result = graph.invoke({"diff": diff})
    formatted = result.get("formatted")
    if not formatted:
        print("No review output", file=sys.stderr)
        sys.exit(1)
    if args.json:
        print(json.dumps(formatted.model_dump(), indent=2))
    else:
        print("Summary:", formatted.summary.model_dump())
        for c in formatted.comments:
            print(f"  {c.file_path}:{c.line_number} [{c.severity}] {c.comment_text}")


if __name__ == "__main__":
    main()
