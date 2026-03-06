"""Embedding interface: real (sentence-transformers) and mock for tests."""

from abc import ABC, abstractmethod
from typing import List

from code_review_agent.config import get_chroma_path


class EmbeddingProvider(ABC):
    """Abstract embedding provider."""

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Return embedding vector for a single text."""
        ...

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Return embedding vectors for multiple texts. Default: call embed in loop."""
        return [self.embed(t) for t in texts]


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Real embeddings using sentence-transformers (all-MiniLM-L6-v2)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> List[float]:
        vec = self._model.encode(text, convert_to_numpy=True)
        return vec.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        vecs = self._model.encode(texts, convert_to_numpy=True)
        return [v.tolist() for v in vecs]


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic mock: prefix-based vectors so similar texts get similar vectors (for tests)."""

    def __init__(self, dim: int = 384):
        self._dim = dim

    def embed(self, text: str) -> List[float]:
        normalized = " ".join(text.split()).strip()
        vec = []
        for i in range(self._dim):
            if i < len(normalized):
                vec.append(float(ord(normalized[i]) % 256) / 256.0)
            else:
                vec.append(0.0)
        return vec


_provider: EmbeddingProvider | None = None


def get_embedding_provider(force_mock: bool = False) -> EmbeddingProvider:
    """Return singleton embedding provider. Use force_mock=True in tests."""
    global _provider
    if force_mock:
        return MockEmbeddingProvider()
    if _provider is None:
        _provider = SentenceTransformerEmbeddingProvider()
    return _provider


def set_embedding_provider(provider: EmbeddingProvider | None) -> None:
    """Inject provider (e.g. mock). Set to None to reset to default."""
    global _provider
    _provider = provider
