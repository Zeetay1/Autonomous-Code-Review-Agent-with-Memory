"""Phase 1: Convention memory - index docs, query by snippet."""

from pathlib import Path

import pytest

from code_review_agent.memory.conventions import ConventionMemory
from code_review_agent.schemas import ConventionEntry


def test_index_and_query_returns_related_convention(
    convention_memory, fixtures_docs_path
):
    """A relevant convention is retrieved for a semantically related code snippet."""
    convention_memory.index_file(fixtures_docs_path / "CONVENTIONS.md")
    snippet = "Use type hints for function arguments"
    results = convention_memory.query(snippet, top_k=3)
    assert len(results) >= 1
    texts = [r.text for r in results]
    assert any("type hints" in t for t in texts)
    assert all(isinstance(r, ConventionEntry) for r in results)
    assert results[0].source_doc == "CONVENTIONS.md"


def test_unrelated_snippet_does_not_return_unrelated_convention(
    convention_memory, fixtures_docs_path
):
    """An irrelevant convention is not retrieved for an unrelated snippet."""
    convention_memory.index_file(fixtures_docs_path / "CONVENTIONS.md")
    # Query with clearly unrelated snippet; type-hints convention should not be top result
    snippet = "xyzzy quux unrelated code"
    results = convention_memory.query(snippet, top_k=5)
    assert len(results) >= 1
    # Top result should not be the "Use type hints" convention (irrelevant to this query)
    top_text = results[0].text
    assert "type hints" not in top_text.lower()


def test_query_empty_snippet_returns_empty(convention_memory, fixtures_docs_path):
    convention_memory.index_file(fixtures_docs_path / "README.md")
    assert convention_memory.query("", top_k=5) == []
    assert convention_memory.query("   ", top_k=5) == []


def test_index_document_chunks_by_section(convention_memory):
    content = "## Section A\nContent A.\n\n## Section B\nContent B."
    convention_memory.index_document(content, source_doc="test.md")
    results = convention_memory.query("Content A", top_k=2)
    assert len(results) >= 1
    assert any("Content A" in r.text for r in results)
