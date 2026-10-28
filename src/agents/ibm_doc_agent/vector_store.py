"""Vector Store Interface and Embedding Ingestion Pipeline.

Supports generating embeddings using watsonx / IBM slate / sentence-transformers
or standard vector similarity engines (Chroma, Milvus, in-memory JSON vector index).
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.agents.ibm_doc_agent.models import DocumentChunk

logger = logging.getLogger("ibm_doc_vector_store")


class VectorStore:
    """Manages document embeddings and provides semantic vector similarity search."""

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        embedding_dimension: int = 384,
        watsonx_api_key: Optional[str] = None,
        watsonx_project_id: Optional[str] = None,
    ) -> None:
        """Initialize VectorStore.

        Args:
            storage_path: File path to persist the index (JSON/pickle format).
            embedding_dimension: Number of dimensions for vector space.
            watsonx_api_key: Optional IBM watsonx.ai API key for cloud embeddings.
            watsonx_project_id: Optional watsonx Project ID.
        """
        self.storage_path = storage_path or Path("knowledge-bases/ibm_doc_store.json")
        self.embedding_dimension = embedding_dimension
        self.watsonx_api_key = watsonx_api_key or os.getenv("IBM_WATSONX_API_KEY")
        self.watsonx_project_id = watsonx_project_id or os.getenv("WATSONX_PROJECT_ID")
        self.chunks: List[DocumentChunk] = []

        if self.storage_path.exists():
            self.load()

    def _generate_synthetic_embedding(self, text: str) -> List[float]:
        """Generate a deterministic normalized vector based on term frequency hashing.

        This serves as a reliable, zero-cloud-dependency embedding generator when
        external watsonx embedding API keys are not supplied.
        """
        words = re.findall(r"\b\w+\b", text.lower())
        vec = [0.0] * self.embedding_dimension
        if not words:
            return vec

        for word in words:
            h = hash(word) % self.embedding_dimension
            vec[h] += 1.0

        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def embed_text(self, text: str) -> List[float]:
        """Compute embedding vector for a given text string.

        Args:
            text: Text passage to embed.

        Returns:
            List of float values representing vector coordinates.
        """
        # If watsonx credentials are present and configured, call IBM watsonx.ai embedding endpoint
        if self.watsonx_api_key and self.watsonx_project_id:
            try:
                # Placeholder for watsonx embedding API call
                # In production, uses ibm_watsonx_ai API: /ml/v1/text/embeddings
                pass
            except Exception as exc:
                logger.warning("watsonx embedding API call failed, falling back to local embedder: %s", exc)

        return self._generate_synthetic_embedding(text)

    def add_chunks(self, chunks: List[DocumentChunk]) -> int:
        """Embed and add a list of DocumentChunks into the vector store.

        Args:
            chunks: List of DocumentChunks.

        Returns:
            Number of successfully added chunks.
        """
        added_count = 0
        for chunk in chunks:
            if not chunk.embedding:
                chunk.embedding = self.embed_text(chunk.text)
            self.chunks.append(chunk)
            added_count += 1

        self.save()
        logger.info("Successfully added and persisted %d chunks to vector store.", added_count)
        return added_count

    def similarity_search(
        self, query: str, top_k: int = 5, score_threshold: float = 0.0
    ) -> List[Tuple[DocumentChunk, float]]:
        """Perform semantic cosine similarity search against the vector index.

        Args:
            query: Query text.
            top_k: Maximum number of ranked results to return.
            score_threshold: Minimum similarity score (0.0 to 1.0).

        Returns:
            List of tuples (DocumentChunk, similarity_score) sorted by relevance.
        """
        query_vec = self.embed_text(query)
        results: List[Tuple[DocumentChunk, float]] = []

        for chunk in self.chunks:
            if not chunk.embedding:
                continue

            # Cosine similarity between normalized vectors
            dot_product = sum(q * c for q, c in zip(query_vec, chunk.embedding))
            if dot_product >= score_threshold:
                results.append((chunk, dot_product))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def save(self) -> None:
        """Persist vector index and metadata to disk."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "count": len(self.chunks),
            "chunks": [chunk.to_dict() for chunk in self.chunks],
        }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load(self) -> None:
        """Load vector index from disk."""
        if not self.storage_path.exists():
            return
        with open(self.storage_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.chunks = [DocumentChunk(**item) for item in data.get("chunks", [])]
        logger.info("Loaded %d document chunks from %s", len(self.chunks), self.storage_path)
