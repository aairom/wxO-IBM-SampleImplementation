#!/usr/bin/env python3
"""
live_bob_search.py — watsonx Orchestrate ADK tool for live IBM Bob documentation search.

This module exposes two @tool-decorated functions that can be registered with a
native wxO agent:

  search_bob_documentation(query)
      Searches the IBM Bob docs knowledge base via the Bob internal search API and
      returns a formatted list of matching passages with their source URLs.

  get_bob_doc_section(section_name)
      Retrieves all documentation content for a named IBM Bob section (e.g.
      "bob_shell", "skills", "mcp") from the pre-indexed knowledge base files.

Credentials are read at runtime from the wxO connection named "bob_search_api"
(api_key_auth). They are never passed as tool parameters.

Import into wxO:
    orchestrate tools import -k python -f tools/live_bob_search.py

Requires:
    ibm-watsonx-orchestrate >= 2.18.1
    requests >= 2.32.0
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

# ADK real import path (verified against ADK 2.18.1)
from ibm_watsonx_orchestrate.agent_builder.tools import ToolPermission, tool

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Directory containing the pre-indexed .txt knowledge-base files.
_DOCS_DIR = Path(__file__).parent.parent / "knowledge-bases" / "docs"

#: Allowed hostnames for the Bob search API (SSRF allowlist).
_ALLOWED_HOSTS = frozenset(["internal.bob.ibm.com", "bob.ibm.com"])

#: Maps friendly section names to their .txt filenames.
_SECTION_FILES: dict[str, str] = {
    "overview": "01_overview.txt",
    "bob_shell": "02_bob_shell.txt",
    "enterprise": "03_enterprise.txt",
    "premium_packages": "04_premium_packages.txt",
    "skills": "05_skills.txt",
    "mcp": "06_mcp.txt",
    "security": "07_security.txt",
    "telemetry": "08_telemetry.txt",
    "modes": "09_modes.txt",
    "bobcoins": "10_bobcoins.txt",
    "bobalytics": "11_bobalytics.txt",
}

#: Maximum number of search result chunks returned per query.
_DEFAULT_TOP_K = 8

#: Maximum characters returned per section file (prevents oversized responses).
_MAX_SECTION_CHARS = 4_000


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_api_url(url: str) -> str:
    """Raise ValueError if url hostname is not in the SSRF allowlist.

    Args:
        url: The full HTTPS URL to validate.

    Returns:
        The original url string if valid.

    Raises:
        ValueError: If the hostname is not in _ALLOWED_HOSTS.
    """
    parsed = urlparse(url)
    if parsed.hostname not in _ALLOWED_HOSTS:
        raise ValueError(
            f"Blocked API hostname '{parsed.hostname}'. "
            f"Allowed: {sorted(_ALLOWED_HOSTS)}"
        )
    return url


def _get_credentials() -> tuple[str, str]:
    """Read Bob search API credentials from environment variables.

    At runtime inside wxO the platform sets these via the registered connection.
    Locally, they are read from the .env file.

    Returns:
        A (api_url, api_token) tuple.

    Raises:
        EnvironmentError: If either variable is missing or empty.
    """
    api_url = os.environ.get("BOB_SEARCH_API_URL", "").strip()
    api_token = os.environ.get("BOB_SEARCH_API_TOKEN", "").strip()
    if not api_url or not api_token:
        raise EnvironmentError(
            "BOB_SEARCH_API_URL and BOB_SEARCH_API_TOKEN must be set. "
            "See .env.example for the required variable names."
        )
    return api_url, api_token


def _call_search_api(query: str, top_k: int = _DEFAULT_TOP_K) -> list[dict]:
    """POST to the Bob search API and return the results list.

    Args:
        query: Natural language search string.
        top_k: Maximum number of result chunks to return.

    Returns:
        A list of result dicts, each with keys: id, content, metadata.
        Returns an empty list if credentials are unavailable.
    """
    try:
        api_url, api_token = _get_credentials()
    except EnvironmentError:
        return []

    safe_url = _validate_api_url(api_url)

    resp = requests.post(
        safe_url,
        json={"query": query, "top_k": top_k, "library_name": "bob"},
        headers={"Authorization": f"Bearer {api_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def _format_results(results: list[dict]) -> str:
    """Convert raw API result dicts into a human-readable string.

    Args:
        results: List of result dicts from _call_search_api.

    Returns:
        A formatted multi-line string, or a not-found message if empty.
    """
    if not results:
        return (
            "No results found in the IBM Bob documentation for that query. "
            "Try rephrasing or visit https://bob.ibm.com/docs/ directly."
        )

    lines: list[str] = []
    for i, item in enumerate(results, start=1):
        meta = item.get("metadata", {})
        section = meta.get("section_path", "IBM Bob Docs")
        source = meta.get("source_url", "https://bob.ibm.com/docs/")
        content = item.get("content", "").strip()
        lines.append(
            f"[{i}] {section}\n"
            f"Source: {source}\n"
            f"{textwrap.fill(content, width=100)}\n"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Exported @tool functions
# ---------------------------------------------------------------------------


@tool(
    permission=ToolPermission.READ_ONLY,
    name="search_bob_documentation",
    description=(
        "Search the official IBM Bob documentation for information about Bob features, "
        "capabilities, configuration, Bob Shell, enterprise plans, premium packages, "
        "skills, MCP server integrations, security, telemetry, modes, and Bobcoins. "
        "Returns relevant documentation passages with source URLs. "
        "Use this tool to answer any question about IBM Bob."
    ),
)
def search_bob_documentation(query: str) -> str:
    """Search the IBM Bob documentation for the given query.

    Calls the Bob internal search API with the provided query string and returns
    matching documentation passages, each with a source URL citation.

    Args:
        query: A natural language question or keyword search, e.g.
               "How do I create a custom skill?" or "Bob Shell slash commands".

    Returns:
        A formatted string containing up to 8 matching documentation passages
        with section names and source URLs, or a not-found message.
    """
    results = _call_search_api(query)
    return _format_results(results)


@tool(
    permission=ToolPermission.READ_ONLY,
    name="get_bob_doc_section",
    description=(
        "Retrieve the full documentation text for a named IBM Bob section. "
        "Valid section names: overview, bob_shell, enterprise, premium_packages, "
        "skills, mcp, security, telemetry, modes, bobcoins, bobalytics. "
        "Use this when you need comprehensive detail about a specific topic area "
        "rather than a targeted keyword search."
    ),
)
def get_bob_doc_section(section_name: str) -> str:
    """Return the pre-indexed documentation text for a named IBM Bob section.

    Reads the corresponding .txt file from the knowledge-bases/docs/ directory.
    Returns the first _MAX_SECTION_CHARS characters to stay within context limits.

    Args:
        section_name: One of the valid section identifiers: overview, bob_shell,
                      enterprise, premium_packages, skills, mcp, security,
                      telemetry, modes, bobcoins, bobalytics.

    Returns:
        The documentation text for the section (up to 4,000 characters), or an
        error message listing valid section names if the name is not recognised.
    """
    key = section_name.strip().lower()
    filename = _SECTION_FILES.get(key)

    if filename is None:
        valid = ", ".join(sorted(_SECTION_FILES))
        return (
            f"Unknown section '{section_name}'. "
            f"Valid section names are: {valid}."
        )

    doc_path = _DOCS_DIR / filename
    if not doc_path.exists():
        return (
            f"Documentation file for section '{section_name}' is not available locally. "
            "Run scripts/fetch_ibm_bob_docs.py to regenerate it."
        )

    text = doc_path.read_text(encoding="utf-8").strip()
    if len(text) > _MAX_SECTION_CHARS:
        text = text[:_MAX_SECTION_CHARS] + "\n\n[... truncated — use search_bob_documentation for targeted queries ...]"
    return text
