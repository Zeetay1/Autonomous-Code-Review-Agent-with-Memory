"""Convention memory: index codebase docs by section, query by code snippet similarity."""

import re
from pathlib import Path
from typing import List, Union, Any

from code_review_agent.schemas import ConventionEntry
from code_review_agent.memory.embeddings import EmbeddingProvider


def _chunk_by_section(content: str, source_doc: str) -> List[tuple[str, str | None]]:
    """Split content by markdown ## sections. Returns list of (chunk_text, section_name)."""
    chunks: List[tuple[str, str | None]] = []
    # Split on ## or ###
    parts = re.split(r"\n(?=#{2,3}\s)", content.strip())
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.split("\n")
        section: str | None = None
        if lines and lines[0].startswith("#"):
            section = lines[0].lstrip("#").strip()
            body = "\n".join(lines[1:]).strip()
        else:
            body = part
        if body:
            chunks.append((body, section))
    if not chunks:
        chunks.append((content.strip(), None))
    return chunks


class ConventionMemory:
    """Index and query codebase documentation by semantic similarity."""

    COLLECTION_NAME = "conventions"

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
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
        name = collection_name or self.COLLECTION_NAME
        self._coll = self._client.get_or_create_collection(
            name=name,
            metadata={"description": "Codebase convention chunks"},
        )

    def index_document(self, content: str, source_doc: str) -> None:
        """Chunk content by section and add to the collection."""
        chunks = _chunk_by_section(content, source_doc)
        if not chunks:
            return
        ids = [f"{source_doc}:{i}" for i in range(len(chunks))]
        texts = [c[0] for c in chunks]
        metadatas = [
            {"source_doc": source_doc, "section": chunks[i][1] or ""}
            for i in range(len(chunks))
        ]
        embeddings = self._embed.embed_batch(texts)
        self._coll.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    def index_file(self, file_path: Union[str, Path]) -> None:
        """Read file and index its content. source_doc = file name."""
        path = Path(file_path)
        content = path.read_text(encoding="utf-8", errors="replace")
        self.index_document(content, source_doc=path.name)

    def query(self, code_snippet: str, top_k: int = 5) -> List[ConventionEntry]:
        """Return top-k convention chunks most similar to the code snippet."""
        if not code_snippet.strip():
            return []
        n = self._coll.count()
        if n == 0:
            return []
        vec = self._embed.embed(code_snippet)
        results = self._coll.query(query_embeddings=[vec], n_results=min(top_k, n))
        if not results or not results["documents"] or not results["documents"][0]:
            return []
        entries = []
        docs = results["documents"][0]
        metadatas = (results.get("metadatas") or [[]])[0]
        for i, doc in enumerate(docs):
            meta = metadatas[i] if metadatas and i < len(metadatas) else {}
            entries.append(
                ConventionEntry(
                    text=doc,
                    source_doc=meta.get("source_doc", ""),
                    section=meta.get("section") or None,
                )
            )
        return entries
