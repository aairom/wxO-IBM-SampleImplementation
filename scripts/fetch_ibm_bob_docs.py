#!/usr/bin/env python3
"""
fetch_ibm_bob_docs.py — Populate knowledge-bases/docs/ with real IBM Bob
documentation text extracted via the Bob MCP search_ibm_docs API.

The IBM Bob documentation site (bob.ibm.com) is a JavaScript SPA. Fetching
pages with requests.get() returns an empty HTML shell. This script uses the
search_ibm_docs Bob library to retrieve the actual documentation text chunks
and writes them as plain .txt files that watsonx Orchestrate can index.

Usage:
    # From the project root:
    source .venv/bin/activate
    python3 scripts/fetch_ibm_bob_docs.py

Output:
    knowledge-bases/docs/01_overview.txt  ... 11_bobalytics.txt
"""

import os
import sys
import textwrap
from pathlib import Path

import requests  # already in requirements.txt

# ---------------------------------------------------------------------------
# Each entry: (output_filename, [list of search queries])
# ---------------------------------------------------------------------------
TOPICS = [
    ("01_overview.txt", [
        "IBM Bob overview features capabilities what is Bob",
        "IBM Bob FAQ general questions SDLC coding assistant",
        "IBM Bob getting started installation IDE",
    ]),
    ("02_bob_shell.txt", [
        "Bob Shell terminal AI assistance commands interactive non-interactive",
        "Bob Shell capabilities features key capabilities",
        "Bob Shell getting started slash commands",
    ]),
    ("03_enterprise.txt", [
        "IBM Bob Enterprise plan admin dashboard users roles Bobcoin",
        "IBM Bob Enterprise centralized management spending controls",
        "IBM Bob Enterprise support subscription",
    ]),
    ("04_premium_packages.txt", [
        "IBM Bob premium packages add-ons specialized capabilities",
        "premium packages assigning removing users admin",
    ]),
    ("05_skills.txt", [
        "IBM Bob skills custom skill creation SKILL.md format",
        "IBM Bob skills how skills work supporting files locations",
        "IBM Bob skills approving auto-approve",
    ]),
    ("06_mcp.txt", [
        "IBM Bob MCP server configuration tools integration Model Context Protocol",
        "MCP server transports add configure Bob IDE",
        "MCP Bob Shell configuration DevOps",
        "MCP security guidelines authentication encryption",
    ]),
    ("07_security.txt", [
        "IBM Bob security guidelines hardening data restrictions",
        "IBM Bob auto-approve security risks bobignore",
        "IBM Bob MCP securely security requirements",
    ]),
    ("08_telemetry.txt", [
        "IBM Bob telemetry data collection privacy usage analytics enable disable",
        "Bob Shell telemetry opt in usage statistics",
    ]),
    ("09_modes.txt", [
        "IBM Bob modes custom modes code ask architect persona built-in",
        "IBM Bob custom modes YAML roleDefinition groups customInstructions",
        "Bob Shell custom modes slash commands mode switching",
    ]),
    ("10_bobcoins.txt", [
        "Bobcoins usage budget spending allocation credits monthly reset",
        "Bobcoin tier progression feedback increase budget monitoring",
        "Enterprise Bobcoins shared pool admin",
    ]),
    ("11_bobalytics.txt", [
        "IBM Bob Bobalytics analytics dashboard team adoption Enterprise",
        "Bobalytics KPI Bob factor adoption rate Bobcoin spend",
        "Bobalytics accessing navigating reviewing data",
    ]),
]

DOCS_DIR = Path(__file__).parent.parent / "knowledge-bases" / "docs"
TOP_K = 8  # chunks per query

# Allowlist of permitted Bob search API hostnames (prevents SSRF)
_ALLOWED_HOSTS = frozenset([
    "internal.bob.ibm.com",
    "bob.ibm.com",
])


def _validate_url(url: str) -> str:
    """Raise ValueError if the URL hostname is not in the allowlist."""
    from urllib.parse import urlparse  # parse only — no network call
    parsed = urlparse(url)
    if parsed.hostname not in _ALLOWED_HOSTS:
        raise ValueError(
            f"Blocked URL hostname '{parsed.hostname}'. "
            f"Allowed hosts: {sorted(_ALLOWED_HOSTS)}"
        )
    return url


def search_bob_docs(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    Call the Bob internal search API. Credentials are read from environment
    variables; the API URL is validated against an explicit allowlist to
    prevent server-side request forgery.

    Required environment variables:
        BOB_SEARCH_API_URL    — HTTPS endpoint for the Bob search API
        BOB_SEARCH_API_TOKEN  — Bearer token for authentication
    """
    bob_search_url = os.environ.get("BOB_SEARCH_API_URL", "").strip()
    bob_search_token = os.environ.get("BOB_SEARCH_API_TOKEN", "").strip()

    if not bob_search_url or not bob_search_token:
        print(
            textwrap.dedent("""
            This script requires the Bob internal search API credentials.
            Set the following environment variables and re-run:

                export BOB_SEARCH_API_URL=<internal-bob-search-endpoint>
                export BOB_SEARCH_API_TOKEN=<your-token>

            Alternatively, the documentation text files have already been
            pre-populated by the Bob MCP tool inside Bob IDE. You do not need
            to re-run this script unless the documentation has changed.
            """).strip()
        )
        return []

    # Validate URL against allowlist before making any network request
    try:
        safe_url = _validate_url(bob_search_url)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    payload = {"query": query, "top_k": top_k, "library_name": "bob"}
    resp = requests.post(
        safe_url,
        json=payload,
        headers={"Authorization": f"Bearer {bob_search_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def collect_content(queries: list[str]) -> str:
    """Run all queries for a topic, deduplicate chunks, return combined text."""
    seen_ids: set[str] = set()
    sections: list[str] = []

    for query in queries:
        results = search_bob_docs(query)
        if not results:
            continue
        for item in results:
            chunk_id = item.get("id", "")
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)
            section_path = item.get("metadata", {}).get("section_path", "")
            content = item.get("content", "").strip()
            if content:
                header = f"\n## {section_path}\n" if section_path else ""
                sections.append(f"{header}\n{content}")

    return "\n\n---\n".join(sections)


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing documentation text files to {DOCS_DIR}/")

    for filename, queries in TOPICS:
        out_path = DOCS_DIR / filename
        print(f"  Fetching {filename} ...", end=" ", flush=True)
        content = collect_content(queries)
        if not content:
            print("SKIPPED (no content returned — credentials not set)")
            continue
        out_path.write_text(content, encoding="utf-8")
        print(f"OK ({len(content):,} chars)")

    print("\nDone. Re-import the knowledge base with:")
    print("  orchestrate knowledge-bases import -f knowledge-bases/ibm_bob_docs.kb.yaml")


if __name__ == "__main__":
    main()
