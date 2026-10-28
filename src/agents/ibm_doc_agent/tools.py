"""watsonx Orchestrate ADK Tools for IBM Documentation Agent.

Provides callable tools for semantic vector search, passage extraction, and live documentation lookups.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# ADK real import path with resilient fallback for local unit testing environments
try:
    from ibm_watsonx_orchestrate.agent_builder.tools import tool
except ImportError:
    # Minimal mock decorator for local execution when orchestrate SDK is not present
    def tool(f):
        return f

from src.agents.ibm_doc_agent.vector_store import VectorStore

logger = logging.getLogger("ibm_doc_tools")

# Point to standard knowledge store location
_DEFAULT_STORE_PATH = Path(__file__).parent.parent.parent.parent / "knowledge-bases" / "ibm_doc_store.json"
_vector_store_instance: Optional[VectorStore] = None


def _get_vector_store() -> VectorStore:
    """Singleton getter for VectorStore."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore(storage_path=_DEFAULT_STORE_PATH)
    return _vector_store_instance


@tool
def search_ibm_live_docs(query: str, limit: int = 5) -> str:
    """Search indexed live IBM documentation for relevant passages, concepts, and technical guides.

    Args:
        query: The search keywords or natural language question (e.g. 'how to build watsonx agents').
        limit: Maximum number of passages to return (default: 5, max: 10).

    Returns:
        Formatted markdown containing passages, section titles, and source URLs.
    """
    store = _get_vector_store()
    results = store.similarity_search(query, top_k=min(limit, 10))

    if not results:
        return (
            "No directly matching passages found in the indexed IBM documentation for this query. "
            "Please check the official documentation at https://www.ibm.com/docs."
        )

    output = [f"### Relevant IBM Documentation Passages for: '{query}'\n"]
    for i, (chunk, score) in enumerate(results, start=1):
        output.append(
            f"**[{i}] {chunk.page_title} — {chunk.section_header}**\n"
            f"> Source URL: {chunk.source_url}\n\n"
            f"{chunk.text}\n"
        )

    return "\n---\n".join(output)


@tool
def get_ibm_doc_by_url(url: str) -> str:
    """Retrieve indexed documentation content associated with a specific IBM doc URL.

    Args:
        url: The exact URL of the IBM documentation page.

    Returns:
        The extracted documentation sections matching the URL.
    """
    store = _get_vector_store()
    matching_chunks = [c for c in store.chunks if c.source_url == url]

    if not matching_chunks:
        return f"No indexed documentation found for URL: {url}"

    title = matching_chunks[0].page_title
    sections = "\n\n".join([f"#### {c.section_header}\n{c.text}" for c in matching_chunks])
    return f"### Document: {title}\n**URL:** {url}\n\n{sections}"
