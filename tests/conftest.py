"""Pytest fixtures: in-memory Chroma client, mock embedder, rejection count dict, memory instances."""

from pathlib import Path

import pytest
import chromadb

from code_review_agent.memory.embeddings import MockEmbeddingProvider, set_embedding_provider
from code_review_agent.memory.conventions import ConventionMemory
from code_review_agent.memory.review_history import ReviewHistoryMemory


@pytest.fixture
def chroma_client(request):
    """In-memory ChromaDB client (no file locks on Windows). Unique per test."""
    return chromadb.EphemeralClient()


@pytest.fixture
def rejection_count_map():
    """In-memory pattern_id -> rejection count for tests."""
    return {}


def get_rejection_count_factory(rejection_count_map: dict):
    def get_rejection_count(pattern_id: str) -> int:
        return rejection_count_map.get(pattern_id, 0)
    return get_rejection_count


@pytest.fixture
def mock_embedder():
    """Use mock embedder for all tests (deterministic, no GPU)."""
    provider = MockEmbeddingProvider()
    set_embedding_provider(provider)
    yield provider
    set_embedding_provider(None)


@pytest.fixture
def convention_memory(chroma_client, mock_embedder, request):
    """Convention memory with mock embedder and in-memory Chroma. Isolated per test."""
    return ConventionMemory(
        embedding_provider=mock_embedder,
        client=chroma_client,
        collection_name=f"conventions_{request.node.name}",
    )


@pytest.fixture
def review_history_memory(chroma_client, mock_embedder, rejection_count_map, request):
    """Review history memory with mock embedder and in-memory rejection counts. Isolated per test."""
    return ReviewHistoryMemory(
        embedding_provider=mock_embedder,
        get_rejection_count=get_rejection_count_factory(rejection_count_map),
        client=chroma_client,
        collection_name=f"review_history_{request.node.name}",
    )


@pytest.fixture
def fixtures_docs_path():
    """Path to tests/fixtures/docs directory."""
    return Path(__file__).resolve().parent / "fixtures" / "docs"
