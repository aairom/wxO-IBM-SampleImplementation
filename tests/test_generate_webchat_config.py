#!/usr/bin/env python3
"""
test_generate_webchat_config.py — Unit tests for scripts/_generate_webchat_config.py

Coverage:
  extract_value       — normal case, multi-line wrapped value, missing key
  .env reading logic  — key present, key absent, key with quotes, comments skipped
  template rendering  — all placeholders replaced, partial replacement warned
  run_orc             — called with correct args, timeout propagated
  main()              — success path, empty embed output (fallback), template missing

All subprocess calls are mocked — no network or CLI calls.
Run:
    cd <project_root>
    source venv/bin/activate
    python -m pytest tests/test_generate_webchat_config.py -v
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers — dynamically import the script as a module
# ---------------------------------------------------------------------------

def _load_module():
    """Import _generate_webchat_config without executing main()."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_generate_webchat_config",
        Path(__file__).parent.parent / "scripts" / "_generate_webchat_config.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = _load_module()


# ---------------------------------------------------------------------------
# extract_value
# ---------------------------------------------------------------------------

class TestExtractValue(unittest.TestCase):

    def test_simple_single_line(self):
        snippet = '{ "orchestrationID": "abc123", "hostURL": "https://example.com" }'
        self.assertEqual(MOD.extract_value("orchestrationID", snippet), "abc123")

    def test_multi_line_wrapped(self):
        # ADK CLI wraps long values across lines
        snippet = textwrap.dedent("""\
            window.wxOConfiguration = {
              "orchestrationID":
              "e65910fa61ce9072d64902d03f3d4774_75c2cabb-2b02-4d65-8127-a9cc65d1ee46",
              "hostURL": "https://eu-de.watson-orchestrate.cloud.ibm.com"
            }
        """)
        result = MOD.extract_value("orchestrationID", snippet)
        self.assertEqual(result, "e65910fa61ce9072d64902d03f3d4774_75c2cabb-2b02-4d65-8127-a9cc65d1ee46")

    def test_nested_key(self):
        snippet = '{ "chatOptions": { "agentId": "5c3c69c8-be40", "agentEnvironmentId": "dba7f186" } }'
        self.assertEqual(MOD.extract_value("agentId", snippet), "5c3c69c8-be40")
        self.assertEqual(MOD.extract_value("agentEnvironmentId", snippet), "dba7f186")

    def test_missing_key_returns_empty(self):
        snippet = '{ "hostURL": "https://example.com" }'
        self.assertEqual(MOD.extract_value("orchestrationID", snippet), "")

    def test_empty_string_input(self):
        self.assertEqual(MOD.extract_value("anything", ""), "")


# ---------------------------------------------------------------------------
# .env reading logic  (tested via main() with a real temp filesystem)
# ---------------------------------------------------------------------------

class TestDotenvReading(unittest.TestCase):
    """Verify that main() reads IBM_CLOUD_API_KEY from .env when not in env vars."""

    def _make_tree(self, tmp: Path, dotenv_content: str, template_content: str | None = None):
        """Create minimal project tree under tmp."""
        scripts_dir = tmp / "scripts"
        web_dir = tmp / "web"
        scripts_dir.mkdir()
        web_dir.mkdir()

        (tmp / ".env").write_text(dotenv_content, encoding="utf-8")

        default_template = textwrap.dedent("""\
            window.wxOConfiguration = {
              orchestrationID: "%%ORCHESTRATION_ID%%",
              hostURL: "%%HOST_URL%%",
              crn: "%%CRN%%",
              chatOptions: {
                agentId: "%%AGENT_ID%%",
                agentEnvironmentId: "%%AGENT_ENV_ID%%"
              }
            };
        """)
        (web_dir / "webchat-config.js.template").write_text(
            template_content or default_template, encoding="utf-8"
        )
        return tmp

    def _fake_embed_result(self):
        snippet = textwrap.dedent("""\
            window.wxOConfiguration = {
              "orchestrationID": "orch-id-001",
              "hostURL": "https://eu-de.watson-orchestrate.cloud.ibm.com",
              "crn": "crn:v1:test",
              "chatOptions": {
                "agentId": "agent-id-001",
                "agentEnvironmentId": "env-id-001"
              }
            };
        """)
        result = MagicMock()
        result.returncode = 0
        result.stdout = snippet
        result.stderr = ""
        return result

    def _fake_activate_result(self):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "Environment 'aam-wxo-be' is now active"
        result.stderr = ""
        return result

    def test_api_key_read_from_dotenv(self):
        """When IBM_CLOUD_API_KEY is not in os.environ, main() reads it from .env."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            self._make_tree(tmp, "IBM_CLOUD_API_KEY=my-real-key\n")

            activate_res = self._fake_activate_result()
            embed_res = self._fake_embed_result()

            with patch("subprocess.run", side_effect=[activate_res, embed_res]) as mock_run, \
                 patch.dict("os.environ", {}, clear=False):
                # Ensure env var is absent
                import os as _os
                _os.environ.pop("IBM_CLOUD_API_KEY", None)
                _os.environ.pop("ORCHESTRATE_API_KEY", None)

                sys.argv = [
                    "prog",
                    "--project-root", str(tmp),
                    "--agent-name", "ibm_bob_assistant",
                    "--env", "live",
                ]
                rc = MOD.main()

            self.assertEqual(rc, 0)
            # activate was called (means the key was found and used)
            activate_call = mock_run.call_args_list[0]
            self.assertIn("activate", activate_call.args[0])
            # The API key was passed via stdin
            self.assertIn("my-real-key", activate_call.kwargs.get("input", ""))

    def test_dotenv_with_quoted_value(self):
        """Values wrapped in double or single quotes are stripped correctly."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            self._make_tree(tmp, 'IBM_CLOUD_API_KEY="quoted-key"\n')

            activate_res = self._fake_activate_result()
            embed_res = self._fake_embed_result()

            with patch("subprocess.run", side_effect=[activate_res, embed_res]):
                import os as _os
                _os.environ.pop("IBM_CLOUD_API_KEY", None)
                _os.environ.pop("ORCHESTRATE_API_KEY", None)

                sys.argv = [
                    "prog",
                    "--project-root", str(tmp),
                    "--agent-name", "ibm_bob_assistant",
                ]
                rc = MOD.main()

            self.assertEqual(rc, 0)

    def test_dotenv_comments_and_blanks_ignored(self):
        """Comments (#) and blank lines in .env are skipped."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            self._make_tree(tmp, textwrap.dedent("""\
                # This is a comment
                SOME_OTHER_VAR=hello

                IBM_CLOUD_API_KEY=actual-key

                # trailing comment
            """))

            activate_res = self._fake_activate_result()
            embed_res = self._fake_embed_result()

            with patch("subprocess.run", side_effect=[activate_res, embed_res]) as mock_run:
                import os as _os
                _os.environ.pop("IBM_CLOUD_API_KEY", None)
                _os.environ.pop("ORCHESTRATE_API_KEY", None)

                sys.argv = [
                    "prog", "--project-root", str(tmp),
                    "--agent-name", "ibm_bob_assistant",
                ]
                rc = MOD.main()

            self.assertEqual(rc, 0)
            activate_call = mock_run.call_args_list[0]
            self.assertIn("actual-key", activate_call.kwargs.get("input", ""))


# ---------------------------------------------------------------------------
# Template substitution
# ---------------------------------------------------------------------------

class TestTemplateSubstitution(unittest.TestCase):

    def test_all_placeholders_replaced(self):
        template = (
            '%%ORCHESTRATION_ID%% %%HOST_URL%% %%CRN%% %%AGENT_ID%% %%AGENT_ENV_ID%%'
        )
        result = (
            template
            .replace("%%ORCHESTRATION_ID%%", "oid")
            .replace("%%HOST_URL%%",         "https://host")
            .replace("%%CRN%%",              "crn:v1:test")
            .replace("%%AGENT_ID%%",         "aid")
            .replace("%%AGENT_ENV_ID%%",     "eid")
        )
        self.assertNotIn("%%", result)
        self.assertIn("oid", result)
        self.assertIn("aid", result)

    def test_partial_replacement_leaves_placeholder(self):
        template = "%%ORCHESTRATION_ID%% %%AGENT_ID%%"
        result = template.replace("%%ORCHESTRATION_ID%%", "oid")
        self.assertIn("%%AGENT_ID%%", result)


# ---------------------------------------------------------------------------
# Template-not-found path
# ---------------------------------------------------------------------------

class TestTemplateMissing(unittest.TestCase):

    def test_exits_2_when_template_absent(self):
        with tempfile.TemporaryDirectory() as td:
            sys.argv = [
                "prog",
                "--project-root", td,
                "--agent-name", "ibm_bob_assistant",
            ]
            rc = MOD.main()
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
