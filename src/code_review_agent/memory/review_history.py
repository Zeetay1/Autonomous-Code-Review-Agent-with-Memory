"""Review history memory: store past comments with outcomes; down-weight rejected at retrieval."""

import os
import re
from typing import Any, Callable, List

from code_review_agent.schemas import PastDecisionEntry
from code_review_agent.memory.embeddings import EmbeddingProvider


def pattern_id_from_snippet(code_snippet: str) -> str:
    """Stable pattern id from normalized code snippet."""
    normalized = re.sub(r"\s+", " ", code_snippet.strip())
    return str(hash(normalized))


# Rejection count lookup: pattern_id -> count. Tests pass a dict; production uses SQLite.
GetRejectionCount = Callable[[str], int]

# Configurable per deployment (e.g. a stricter repo might want a lower threshold).
REJECTION_THRESHOLD = int(os.environ.get("REJECTION_THRESHOLD", "5"))
ACCEPTED_WEIGHT = 1.0
REJECTED_WEIGHT = 0.2


class ReviewHistoryMemory:
    """Store and query past review comments with outcome-based down-weighting."""

    COLLECTION_NAME = "review_history"

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        get_rejection_count: GetRejectionCount,
        persist_directory: str | None = None,
        *,
        client: Any = None,
        collection_name: str | None = None,
    ):
        if client is not None:
            self._client = client
        else:
            import chromadb
            from chromadb.config import Settings
            self._client = chromadb.PersistentClient(
                path=persist_directory or ".chroma",
                settings=Settings(anonymized_telemetry=False),
            )
        self._embed = embedding_provider
        self._get_rejection_count = get_rejection_count
        name = collection_name or self.COLLECTION_NAME
        self._coll = self._client.get_or_create_collection(
            name=name,
            metadata={"description": "Past review comments with outcomes"},
        )

    def add(
        self,
        code_snippet: str,
        comment_text: str,
        outcome: str,
        file_path: str,
        severity: str,
    ) -> None:
        """Store one past decision. outcome is 'accepted' or 'rejected'."""
        pid = pattern_id_from_snippet(code_snippet)
        doc_id = f"{pid}:{hash((comment_text, file_path, outcome))}"
        vec = self._embed.embed(code_snippet)
        self._coll.add(
            ids=[doc_id],
            embeddings=[vec],
            documents=[code_snippet],
            metadatas=[
                {
                    "comment_text": comment_text,
                    "outcome": outcome,
                    "file_path": file_path,
                    "severity": severity,
                    "pattern_id": pid,
                }
            ],
        )

    def query(
        self,
        code_snippet: str,
        top_k: int = 5,
        fetch_multiple: int = 20,
    ) -> List[PastDecisionEntry]:
        """
        Return top_k past decisions similar to snippet.
        Excludes patterns with >= REJECTION_THRESHOLD rejections.
        Down-weights rejected vs accepted by score * weight.
        """
        if not code_snippet.strip():
            return []
        n = self._coll.count()
        if n == 0:
            return []
        n_results = min(fetch_multiple, n)
        vec = self._embed.embed(code_snippet)
        results = self._coll.query(
            query_embeddings=[vec],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        docs = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        # Chroma returns L2 distance; lower = more similar. Convert to score ~ 1/(1+d).
        scored: List[tuple[float, dict, str]] = []
        for i, meta in enumerate(metadatas or []):
            pid = meta.get("pattern_id", "")
            if self._get_rejection_count(pid) >= REJECTION_THRESHOLD:
                continue
            outcome = meta.get("outcome", "rejected")
            weight = ACCEPTED_WEIGHT if outcome == "accepted" else REJECTED_WEIGHT
            d = distances[i] if i < len(distances) else 1.0
            score = weight / (1.0 + d)
            doc = docs[i] if i < len(docs) else ""
            scored.append((score, meta, doc))

        scored.sort(key=lambda x: -x[0])
        entries = []
        for _, meta, doc in scored[:top_k]:
            entries.append(
                PastDecisionEntry(
                    code_snippet=doc,
                    comment_text=meta.get("comment_text", ""),
                    outcome=meta.get("outcome", "rejected"),
                    file_path=meta.get("file_path", ""),
                    severity=meta.get("severity", ""),
                    pattern_id=meta.get("pattern_id"),
                )
            )
        return entries
