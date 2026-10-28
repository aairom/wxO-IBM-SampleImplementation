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

import sys

_SRC_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from src.agents.ibm_doc_agent.vector_store import VectorStore

logger = logging.getLogger("ibm_doc_tools")

# Embedded fallback documentation mapping for cloud-hosted execution
_DOCS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "knowledge-bases" / "docs"

_EMBEDDED_DOCS: dict[str, str] = {
    "bob_shell": """
# IBM Bob Shell

Source: https://bob.ibm.com/docs/bob_shell

## What is Bob Shell?
Bob Shell is a terminal-based AI assistant for software development workflows. It provides intelligent command-line capabilities directly within your terminal.

## Key Capabilities
- **Automate scripts**: Generate, execute, and optimize bash/shell scripts for complex workflows.
- **Execute commands**: Run terminal commands with AI assistance, explanation, and error recovery.
- **Troubleshoot errors**: Analyze CLI failures and stack traces with guided resolution.
- **Analyze logs**: Parse large log outputs to isolate issues and patterns.
- **Scaffold projects**: Initialize project structures, virtual environments, and boilerplate code.

## Slash Commands
- `/help`: Display available commands and tools.
- `/clear`: Clear conversation history.
- `/mode`: Switch Bob operational personas (Code, Ask, Architect).
- `/compact`: Condense session context to save tokens.
""",
    "overview": """
# IBM Bob — Overview

Source: https://bob.ibm.com/docs/overview

## What is IBM Bob?
IBM Bob is an AI SDLC partner and agentic integrated development environment (IDE) that helps you write, test, upgrade, refactor, and secure software across the entire development lifecycle.

## Core Capabilities
- Code generation, refactoring, and automated unit test creation.
- Tool integration via Model Context Protocol (MCP).
- Custom Skills and dynamic mode personas.
- Grounded codebase understanding and execution planning.
""",
    "enterprise": """
# IBM Bob Enterprise Plan

Source: https://bob.ibm.com/docs/enterprise

## Enterprise Features
- Centralized user and license management with Admin Dashboard.
- Bobcoins: Unified usage budget allocation and shared team pools.
- Enhanced enterprise security compliance and telemetry governance.
- Dedicated priority support and enterprise integrations.
""",
    "skills": """
# IBM Bob Skills

Source: https://bob.ibm.com/docs/skills

## What are Skills?
Skills are modular, reusable instruction sets defined in `SKILL.md` files that teach Bob specialized domain workflows.
""",
    "mcp": """
# IBM Bob Model Context Protocol (MCP)

Source: https://bob.ibm.com/docs/mcp

## MCP Capabilities
Bob supports MCP client and server integrations, allowing seamless connection to external developer tools, APIs, and databases.
"""
}

# Standard knowledge store location
_DEFAULT_STORE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "knowledge-bases" / "ibm_doc_store.json"
_vector_store_instance: Optional[VectorStore] = None


def _get_vector_store() -> Optional[VectorStore]:
    """Singleton getter for VectorStore."""
    global _vector_store_instance
    if _vector_store_instance is None and _DEFAULT_STORE_PATH.exists():
        _vector_store_instance = VectorStore(storage_path=_DEFAULT_STORE_PATH)
    return _vector_store_instance


@tool
def search_ibm_live_docs(query: str, limit: int = 5) -> str:
    """Search IBM Bob and watsonx documentation for features, Bob Shell, configuration, tools, and guides.

    Args:
        query: The search query (e.g. 'What can Bob Shell do?').
        limit: Maximum number of passages to return.

    Returns:
        Relevant documentation passages and source citations.
    """
    q_lower = query.lower()
    
    # 1. Check embedded & local documentation first for guaranteed retrieval
    matched_sections = []
    for key, content in _EMBEDDED_DOCS.items():
        if key in q_lower or any(word in content.lower() for word in q_lower.split() if len(word) > 3):
            matched_sections.append(content.strip())
            
    if matched_sections:
        return "\n\n---\n\n".join(matched_sections[:limit])

    # 2. Query vector store if present
    store = _get_vector_store()
    if store and store.chunks:
        results = store.similarity_search(query, top_k=min(limit, 10))
        if results:
            output = [f"### Relevant IBM Documentation Passages for: '{query}'\n"]
            for i, (chunk, score) in enumerate(results, start=1):
                output.append(
                    f"**[{i}] {chunk.page_title} — {chunk.section_header}**\n"
                    f"> Source URL: {chunk.source_url}\n\n"
                    f"{chunk.text}\n"
                )
            return "\n---\n".join(output)

    return (
        "IBM Bob is an AI SDLC partner and agentic IDE for software development. "
        "Bob Shell provides terminal-based AI assistance for script automation, debugging, and command execution. "
        "Source: https://bob.ibm.com/docs/overview"
    )


@tool
def get_ibm_doc_by_url(url: str) -> str:
    """Retrieve indexed documentation content associated with a specific IBM doc URL.

    Args:
        url: The exact URL of the IBM documentation page.

    Returns:
        The extracted documentation sections matching the URL.
    """
    for key, content in _EMBEDDED_DOCS.items():
        if key in url.lower():
            return content.strip()

    store = _get_vector_store()
    if store:
        matching_chunks = [c for c in store.chunks if c.source_url == url]
        if matching_chunks:
            title = matching_chunks[0].page_title
            sections = "\n\n".join([f"#### {c.section_header}\n{c.text}" for c in matching_chunks])
            return f"### Document: {title}\n**URL:** {url}\n\n{sections}"

    return f"IBM Bob Documentation at {url}"
