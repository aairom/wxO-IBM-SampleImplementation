#!/usr/bin/env python3
"""
test_live_bob_search.py — Unit tests for tools/live_bob_search.py

Tests cover:
  - _validate_api_url: allowlist enforcement
  - _get_credentials: missing / present env vars
  - _call_search_api: mocked HTTP calls, error propagation
  - _format_results: empty and populated result formatting
  - search_bob_documentation: end-to-end with mocked API
  - get_bob_doc_section: valid section, unknown section, missing file, truncation

All tests use unittest.mock — no real network calls are made.
Run with:
    cd /path/to/wxO-IBM
    source venv/bin/activate
    python -m pytest tests/test_live_bob_search.py -v
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

# ---------------------------------------------------------------------------
# Stub the ADK import so tests run without ibm-watsonx-orchestrate installed
# in the local test environment. The module-level @tool decorator is replaced
# with a no-op pass-through that simply returns the decorated function.
# ---------------------------------------------------------------------------

def _make_adk_stub() -> None:
    """Insert stub modules for ibm_watsonx_orchestrate.agent_builder.tools."""
    # Build the stub hierarchy: ibm_watsonx_orchestrate.agent_builder.tools
    iwx = types.ModuleType("ibm_watsonx_orchestrate")
    ab = types.ModuleType("ibm_watsonx_orchestrate.agent_builder")
    tools_mod = types.ModuleType("ibm_watsonx_orchestrate.agent_builder.tools")

    class _ToolPermission:
        READ_ONLY = "read_only"
        READ_WRITE = "read_write"

    def _tool_decorator(**kwargs):
        """No-op @tool decorator: returns the original function unchanged."""
        def wrapper(fn):
            return fn
        return wrapper

    tools_mod.ToolPermission = _ToolPermission
    tools_mod.tool = _tool_decorator

    iwx.agent_builder = ab  # type: ignore[attr-defined]
    ab.tools = tools_mod  # type: ignore[attr-defined]

    sys.modules.setdefault("ibm_watsonx_orchestrate", iwx)
    sys.modules.setdefault("ibm_watsonx_orchestrate.agent_builder", ab)
    sys.modules.setdefault("ibm_watsonx_orchestrate.agent_builder.tools", tools_mod)


_make_adk_stub()

# Now import the module under test (stubs are in sys.modules before import)
import importlib
import tools.live_bob_search as lbs  # noqa: E402  (import after stub setup)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    chunk_id: str = "c1",
    content: str = "Bob is an AI assistant.",
    section: str = "Overview",
    source: str = "https://bob.ibm.com/docs/overview",
) -> dict:
    """Return a minimal search-result dict matching the API schema."""
    return {
        "id": chunk_id,
        "content": content,
        "metadata": {"section_path": section, "source_url": source},
    }


# ---------------------------------------------------------------------------
# _validate_api_url
# ---------------------------------------------------------------------------

class TestValidateApiUrl(unittest.TestCase):

    def test_allowed_host_internal(self):
        url = "https://internal.bob.ibm.com/api/search"
        self.assertEqual(lbs._validate_api_url(url), url)

    def test_allowed_host_public(self):
        url = "https://bob.ibm.com/api/search"
        self.assertEqual(lbs._validate_api_url(url), url)

    def test_blocked_host_raises(self):
        with self.assertRaises(ValueError) as ctx:
            lbs._validate_api_url("https://evil.example.com/steal")
        self.assertIn("evil.example.com", str(ctx.exception))

    def test_empty_string_raises(self):
        with self.assertRaises(ValueError):
            lbs._validate_api_url("https://other.com/path")


# ---------------------------------------------------------------------------
# _get_credentials
# ---------------------------------------------------------------------------

class TestGetCredentials(unittest.TestCase):

    def test_both_present(self):
        env = {"BOB_SEARCH_API_URL": "https://internal.bob.ibm.com/search",
               "BOB_SEARCH_API_TOKEN": "tok123"}
        with patch.dict("os.environ", env, clear=False):
            url, token = lbs._get_credentials()
        self.assertEqual(url, "https://internal.bob.ibm.com/search")
        self.assertEqual(token, "tok123")

    def test_missing_url_raises(self):
        with patch.dict("os.environ", {"BOB_SEARCH_API_URL": "",
                                        "BOB_SEARCH_API_TOKEN": "tok"}, clear=False):
            with self.assertRaises(EnvironmentError):
                lbs._get_credentials()

    def test_missing_token_raises(self):
        with patch.dict("os.environ", {"BOB_SEARCH_API_URL": "https://internal.bob.ibm.com/s",
                                        "BOB_SEARCH_API_TOKEN": ""}, clear=False):
            with self.assertRaises(EnvironmentError):
                lbs._get_credentials()

    def test_both_missing_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(EnvironmentError):
                lbs._get_credentials()


# ---------------------------------------------------------------------------
# _call_search_api
# ---------------------------------------------------------------------------

class TestCallSearchApi(unittest.TestCase):

    def _env(self) -> dict:
        return {
            "BOB_SEARCH_API_URL": "https://internal.bob.ibm.com/api/search",
            "BOB_SEARCH_API_TOKEN": "secret",
        }

    def test_returns_results_on_200(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": [_make_result()]}
        mock_resp.raise_for_status.return_value = None

        with patch.dict("os.environ", self._env(), clear=False):
            with patch("requests.post", return_value=mock_resp) as mock_post:
                results = lbs._call_search_api("what is Bob?")

        self.assertEqual(len(results), 1)
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        self.assertIn("query", call_kwargs.kwargs["json"])

    def test_returns_empty_list_when_no_credentials(self):
        with patch.dict("os.environ", {}, clear=True):
            results = lbs._call_search_api("any query")
        self.assertEqual(results, [])

    def test_raises_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404 Not Found")

        with patch.dict("os.environ", self._env(), clear=False):
            with patch("requests.post", return_value=mock_resp):
                with self.assertRaises(Exception):
                    lbs._call_search_api("error query")

    def test_blocked_url_raises_value_error(self):
        bad_env = {
            "BOB_SEARCH_API_URL": "https://attacker.net/exfil",
            "BOB_SEARCH_API_TOKEN": "tok",
        }
        with patch.dict("os.environ", bad_env, clear=False):
            with self.assertRaises(ValueError):
                lbs._call_search_api("query")

    def test_passes_top_k_to_payload(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status.return_value = None

        with patch.dict("os.environ", self._env(), clear=False):
            with patch("requests.post", return_value=mock_resp) as mock_post:
                lbs._call_search_api("query", top_k=3)

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["top_k"], 3)


# ---------------------------------------------------------------------------
# _format_results
# ---------------------------------------------------------------------------

class TestFormatResults(unittest.TestCase):

    def test_empty_list_returns_not_found_message(self):
        output = lbs._format_results([])
        self.assertIn("No results found", output)

    def test_single_result_contains_content(self):
        results = [_make_result(content="Bob is your AI coding assistant.")]
        output = lbs._format_results(results)
        self.assertIn("Bob is your AI coding assistant.", output)

    def test_single_result_contains_source(self):
        results = [_make_result(source="https://bob.ibm.com/docs/overview")]
        output = lbs._format_results(results)
        self.assertIn("https://bob.ibm.com/docs/overview", output)

    def test_multiple_results_numbered(self):
        results = [
            _make_result(chunk_id="c1", content="First."),
            _make_result(chunk_id="c2", content="Second."),
        ]
        output = lbs._format_results(results)
        self.assertIn("[1]", output)
        self.assertIn("[2]", output)

    def test_result_with_missing_metadata_keys(self):
        """Should not raise — fall back gracefully to defaults."""
        result = {"id": "x", "content": "Some content", "metadata": {}}
        output = lbs._format_results([result])
        self.assertIn("Some content", output)


# ---------------------------------------------------------------------------
# search_bob_documentation (the @tool function)
# ---------------------------------------------------------------------------

class TestSearchBobDocumentation(unittest.TestCase):

    def test_returns_formatted_results(self):
        mock_results = [_make_result(content="Bob Shell is a terminal AI assistant.")]
        with patch.object(lbs, "_call_search_api", return_value=mock_results):
            output = lbs.search_bob_documentation("Bob Shell commands")
        self.assertIn("Bob Shell is a terminal AI assistant.", output)

    def test_returns_not_found_message_when_empty(self):
        with patch.object(lbs, "_call_search_api", return_value=[]):
            output = lbs.search_bob_documentation("nonexistent topic")
        self.assertIn("No results found", output)

    def test_query_is_forwarded_to_api(self):
        with patch.object(lbs, "_call_search_api", return_value=[]) as mock_api:
            lbs.search_bob_documentation("custom skills")
        mock_api.assert_called_once_with("custom skills")

    def test_is_callable(self):
        """The @tool decorator must not change the function's callability."""
        self.assertTrue(callable(lbs.search_bob_documentation))


# ---------------------------------------------------------------------------
# get_bob_doc_section (the @tool function)
# ---------------------------------------------------------------------------

class TestGetBobDocSection(unittest.TestCase):

    def test_known_section_reads_file(self):
        fake_content = "IBM Bob overview content here."
        m = mock_open(read_data=fake_content)
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=fake_content):
                output = lbs.get_bob_doc_section("overview")
        self.assertIn("IBM Bob overview content here.", output)

    def test_unknown_section_returns_error_message(self):
        output = lbs.get_bob_doc_section("nonexistent_section")
        self.assertIn("Unknown section", output)
        self.assertIn("nonexistent_section", output)

    def test_unknown_section_lists_valid_names(self):
        output = lbs.get_bob_doc_section("bad_name")
        for name in ("overview", "bob_shell", "skills", "mcp"):
            self.assertIn(name, output)

    def test_missing_file_returns_helpful_message(self):
        with patch("pathlib.Path.exists", return_value=False):
            output = lbs.get_bob_doc_section("skills")
        self.assertIn("not available locally", output)
        self.assertIn("fetch_ibm_bob_docs.py", output)

    def test_long_content_is_truncated(self):
        long_content = "x" * (lbs._MAX_SECTION_CHARS + 500)
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=long_content):
                output = lbs.get_bob_doc_section("mcp")
        self.assertIn("truncated", output)
        # Ensure we never return more than max + a small overhead for the suffix
        self.assertLessEqual(len(output), lbs._MAX_SECTION_CHARS + 200)

    def test_short_content_is_not_truncated(self):
        short_content = "Short doc."
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=short_content):
                output = lbs.get_bob_doc_section("bobcoins")
        self.assertNotIn("truncated", output)
        self.assertIn("Short doc.", output)

    def test_section_name_case_insensitive(self):
        """Section lookup must be case-insensitive."""
        fake_content = "Enterprise docs."
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=fake_content):
                output = lbs.get_bob_doc_section("ENTERPRISE")
        self.assertIn("Enterprise docs.", output)

    def test_is_callable(self):
        self.assertTrue(callable(lbs.get_bob_doc_section))


# ---------------------------------------------------------------------------
# Integration-style smoke test (no real network)
# ---------------------------------------------------------------------------

class TestEndToEndMocked(unittest.TestCase):
    """Simulate a full agent call sequence with mocked API."""

    def test_search_then_section_workflow(self):
        """Agent would first search, then optionally fetch a full section."""
        search_results = [
            _make_result(
                content="Bob Shell lets you run AI commands in the terminal.",
                section="Bob Shell / Overview",
                source="https://bob.ibm.com/docs/shell/overview",
            )
        ]
        section_content = "Full Bob Shell documentation text."

        with patch.object(lbs, "_call_search_api", return_value=search_results):
            search_output = lbs.search_bob_documentation("what is Bob Shell?")

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=section_content):
                section_output = lbs.get_bob_doc_section("bob_shell")

        self.assertIn("Bob Shell", search_output)
        self.assertIn("Full Bob Shell documentation text.", section_output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
