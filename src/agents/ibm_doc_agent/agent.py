"""IBM Documentation Assistant Agent Execution Engine.

Provides an agent class that orchestrates vector retrieval, prompt grounding,
and response synthesis for questions about IBM technologies, platforms, and watsonx.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from src.agents.ibm_doc_agent.tools import get_ibm_doc_by_url, search_ibm_live_docs
from src.agents.ibm_doc_agent.vector_store import VectorStore

logger = logging.getLogger("ibm_doc_agent")


class IBMDocAgent:
    """Agent that answers technical questions grounded strictly in indexed IBM Documentation."""

    AGENT_NAME: str = "IBM_Doc_Assistant"
    DEFAULT_MODEL: str = "groq/openai/gpt-oss-120b"

    SYSTEM_INSTRUCTIONS: str = (
        "You are the IBM Documentation Assistant (Watsonx_Knowledge_Agent). "
        "Your role is to assist developers, architects, and administrators with accurate, "
        "concise technical answers grounded strictly in official IBM documentation.\n\n"
        "Rules:\n"
        "1. Always search the indexed documentation using your tools before responding.\n"
        "2. Ground every claim in retrieved passages.\n"
        "3. Provide direct source citations with full URLs.\n"
        "4. If no information is available, state that clearly and suggest visiting https://www.ibm.com/docs."
    )

    def __init__(
        self,
        name: Optional[str] = None,
        vector_store: Optional[VectorStore] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """Initialize IBMDocAgent.

        Args:
            name: Agent identifier name.
            vector_store: VectorStore instance for document retrieval.
            model_name: Foundation model identifier.
        """
        self.name = name or os.getenv("AGENT_NAME", self.AGENT_NAME)
        self.model_name = model_name or os.getenv("AGENT_MODEL", self.DEFAULT_MODEL)
        self.vector_store = vector_store or VectorStore()

    def process_query(self, query: str) -> Dict[str, Any]:
        """Process user query by searching vector index and compiling grounded response.

        Args:
            query: The user question.

        Returns:
            Dictionary containing the generated response, retrieved passages, and citations.
        """
        logger.info("Processing query for agent %s: '%s'", self.name, query)

        # Retrieve relevant passages
        retrieval_text = search_ibm_live_docs(query, limit=3)
        results = self.vector_store.similarity_search(query, top_k=3)

        citations = []
        for chunk, score in results:
            if chunk.source_url not in citations:
                citations.append(chunk.source_url)

        if not results:
            answer = (
                f"I could not locate specific information regarding '{query}' in the current "
                f"indexed documentation store. Please consult the IBM Documentation library directly at "
                f"https://www.ibm.com/docs."
            )
        else:
            top_chunk = results[0][0]
            answer = (
                f"According to the official IBM documentation for **{top_chunk.page_title}** "
                f"({top_chunk.section_header}):\n\n"
                f"{top_chunk.text}\n\n"
                f"---\n"
                f"**Source Citations:**\n"
                + "\n".join([f"- {url}" for url in citations])
            )

        return {
            "agent_name": self.name,
            "query": query,
            "answer": answer,
            "citations": citations,
            "retrieved_context": retrieval_text,
        }
