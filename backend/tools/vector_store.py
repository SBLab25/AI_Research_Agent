"""
FAISS-based vector store for semantic paper search.
Uses sentence-transformers for embeddings.
"""

import asyncio
import numpy as np
from typing import Optional

# Lazy-loaded globals to avoid slow startup
_model = None
_index = None
_documents: list[dict] = []


def _get_model():
    """Lazy-load the sentence transformer model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _get_or_create_index(dimension: int = 384):
    """Lazy-init the FAISS index."""
    global _index
    if _index is None:
        import faiss
        _index = faiss.IndexFlatL2(dimension)
    return _index


async def add_documents(texts: list[str], metadata: list[dict]) -> int:
    """Embed and store documents in the vector store."""

    def _add():
        model = _get_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        embeddings = np.array(embeddings, dtype=np.float32)

        index = _get_or_create_index(embeddings.shape[1])
        start_id = len(_documents)
        index.add(embeddings)

        for i, meta in enumerate(metadata):
            _documents.append({**meta, "text": texts[i], "id": start_id + i})

        return len(texts)

    return await asyncio.to_thread(_add)


async def search(query: str, k: int = 5) -> list[dict]:
    """Search for the most similar documents."""

    def _search():
        if not _documents:
            return []

        model = _get_model()
        index = _get_or_create_index()

        query_embedding = model.encode([query], normalize_embeddings=True)
        query_embedding = np.array(query_embedding, dtype=np.float32)

        k_actual = min(k, len(_documents))
        distances, indices = index.search(query_embedding, k_actual)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(_documents) and idx >= 0:
                doc = _documents[idx].copy()
                doc["score"] = float(distances[0][i])
                results.append(doc)
        return results

    return await asyncio.to_thread(_search)


def clear():
    """Clear the vector store (useful between sessions)."""
    global _index, _documents
    _index = None
    _documents = []
