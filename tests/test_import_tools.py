#!/usr/bin/env python3
"""
test_import_tools.py — Unit tests for scripts/import_tools.py

Coverage:
  load_env              — parsing, comments, blank lines, quotes, missing file
  apply_env             — only sets missing vars, never overwrites
  validate_required_vars — pass, single missing, multiple missing
  discover_tools_in_file — @tool found, @tool(...) found, no tools, syntax error
  list_platform_tools   — table parsing, empty output, no-table output
  tool_exists_on_platform — exact match, prefix match (truncation), miss
  import_tool_file      — success, failure, dry-run
  validate_agent_yaml_tools — all present, one missing, file absent
  redeploy_agent        — success, failure, dry-run
  get_active_environment — (active) line present, absent
  run()                 — dry-run smoke, force-reimport path, skip-agent-deploy
  write_json_report     — file created, JSON valid, keys present
  OrchestrationReport   — dataclass fields default correctly
  ToolImportResult      — dataclass fields default correctly

All subprocess calls are mocked — no network or CLI calls.
Run:
    cd <project_root>
    source venv/bin/activate
    python -m pytest tests/test_import_tools.py -v
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Ensure scripts/ is importable (project root on sys.path)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Now import the module under test
import scripts.import_tools as it  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    """Build a fake subprocess.CompletedProcess for mocking run_orc."""
    r = subprocess.CompletedProcess(args=[], returncode=returncode)
    r.stdout = stdout
    r.stderr = stderr
    return r


def _write_tool_file(tmp_dir: Path, content: str) -> Path:
    """Write *content* to a temp .py file and return the path."""
    p = tmp_dir / "fake_tool.py"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# load_env
# ---------------------------------------------------------------------------

class TestLoadEnv(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _write(self, content: str) -> Path:
        p = self.tmp / ".env"
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return p

    def test_basic_key_value(self):
        p = self._write("KEY=value\n")
        result = it.load_env(p)
        self.assertEqual(result["KEY"], "value")

    def test_comments_and_blanks_ignored(self):
        p = self._write("""
            # This is a comment
            KEY=hello

            # Another comment
        """)
        result = it.load_env(p)
        self.assertIn("KEY", result)
        self.assertNotIn("", result)
        self.assertNotIn("# This is a comment", result)

    def test_double_quoted_value_stripped(self):
        p = self._write('URL="https://example.com"\n')
        self.assertEqual(it.load_env(p)["URL"], "https://example.com")

    def test_single_quoted_value_stripped(self):
        p = self._write("TOKEN='abc123'\n")
        self.assertEqual(it.load_env(p)["TOKEN"], "abc123")

    def test_empty_value_preserved(self):
        p = self._write("EMPTY=\n")
        self.assertEqual(it.load_env(p)["EMPTY"], "")

    def test_multiple_entries(self):
        p = self._write("A=1\nB=2\nC=3\n")
        result = it.load_env(p)
        self.assertEqual(result, {"A": "1", "B": "2", "C": "3"})

    def test_missing_file_exits_2(self):
        with self.assertRaises(SystemExit) as ctx:
            it.load_env(self.tmp / "nonexistent.env")
        self.assertEqual(ctx.exception.code, 2)

    def test_line_without_equals_ignored(self):
        p = self._write("NOEQUALS\nKEY=val\n")
        result = it.load_env(p)
        self.assertNotIn("NOEQUALS", result)
        self.assertIn("KEY", result)


# ---------------------------------------------------------------------------
# apply_env
# ---------------------------------------------------------------------------

class TestApplyEnv(unittest.TestCase):

    def test_sets_missing_var(self):
        os.environ.pop("_TEST_APPLY_A", None)
        it.apply_env({"_TEST_APPLY_A": "injected"})
        self.assertEqual(os.environ["_TEST_APPLY_A"], "injected")
        del os.environ["_TEST_APPLY_A"]

    def test_does_not_overwrite_existing(self):
        os.environ["_TEST_APPLY_B"] = "original"
        it.apply_env({"_TEST_APPLY_B": "overwrite"})
        self.assertEqual(os.environ["_TEST_APPLY_B"], "original")
        del os.environ["_TEST_APPLY_B"]


# ---------------------------------------------------------------------------
# validate_required_vars
# ---------------------------------------------------------------------------

class TestValidateRequiredVars(unittest.TestCase):

    def test_all_present_passes(self):
        with patch.dict("os.environ", {"_R1": "a", "_R2": "b"}):
            # Should not raise
            it.validate_required_vars(["_R1", "_R2"])

    def test_single_missing_exits_2(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(SystemExit) as ctx:
                it.validate_required_vars(["MISSING_VAR_XYZ"])
        self.assertEqual(ctx.exception.code, 2)

    def test_empty_string_counts_as_missing(self):
        with patch.dict("os.environ", {"EMPTY_VAR": ""}):
            with self.assertRaises(SystemExit) as ctx:
                it.validate_required_vars(["EMPTY_VAR"])
        self.assertEqual(ctx.exception.code, 2)


# ---------------------------------------------------------------------------
# discover_tools_in_file
# ---------------------------------------------------------------------------

class TestDiscoverToolsInFile(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_finds_at_tool_call_decorator(self):
        f = _write_tool_file(self.tmp, """
            from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission

            @tool(permission=ToolPermission.READ_ONLY)
            def my_search_tool(query: str) -> str:
                return ""

            @tool(permission=ToolPermission.READ_ONLY)
            def my_other_tool(name: str) -> str:
                return ""
        """)
        result = it.discover_tools_in_file(f)
        self.assertIn("my_search_tool", result)
        self.assertIn("my_other_tool", result)
        self.assertEqual(len(result), 2)

    def test_finds_bare_at_tool_decorator(self):
        f = _write_tool_file(self.tmp, """
            @tool
            def bare_decorated(): pass
        """)
        result = it.discover_tools_in_file(f)
        self.assertIn("bare_decorated", result)

    def test_ignores_non_tool_decorators(self):
        f = _write_tool_file(self.tmp, """
            @staticmethod
            def not_a_tool(): pass

            @property
            def also_not_a_tool(self): pass
        """)
        result = it.discover_tools_in_file(f)
        self.assertEqual(result, [])

    def test_returns_empty_for_no_functions(self):
        f = _write_tool_file(self.tmp, "X = 1\n")
        self.assertEqual(it.discover_tools_in_file(f), [])

    def test_missing_file_returns_empty(self):
        result = it.discover_tools_in_file(self.tmp / "nonexistent.py")
        self.assertEqual(result, [])

    def test_syntax_error_exits_2(self):
        f = _write_tool_file(self.tmp, "def broken(\n")
        with self.assertRaises(SystemExit) as ctx:
            it.discover_tools_in_file(f)
        self.assertEqual(ctx.exception.code, 2)

    def test_order_preserved(self):
        f = _write_tool_file(self.tmp, """
            @tool()
            def alpha(): pass

            @tool()
            def beta(): pass

            @tool()
            def gamma(): pass
        """)
        result = it.discover_tools_in_file(f)
        self.assertEqual(result, ["alpha", "beta", "gamma"])


# ---------------------------------------------------------------------------
# list_platform_tools
# ---------------------------------------------------------------------------

class TestListPlatformTools(unittest.TestCase):

    def test_parses_table_rows(self):
        table_output = (
            "│ Name                                    │ Description │\n"
            "│ search_bob_documentation                │ Search ...  │\n"
            "│ get_bob_doc_section                     │ Retrieve .. │\n"
        )
        with patch.object(it, "run_orc", return_value=_completed(stdout=table_output)):
            result = it.list_platform_tools()
        self.assertIn("search_bob_documentation", result)
        self.assertIn("get_bob_doc_section", result)

    def test_ignores_header_row(self):
        table_output = (
            "│ Name                    │ Description │\n"
            "│ my_tool                 │ Does stuff  │\n"
        )
        with patch.object(it, "run_orc", return_value=_completed(stdout=table_output)):
            result = it.list_platform_tools()
        self.assertNotIn("Name", result)
        self.assertIn("my_tool", result)

    def test_empty_output_returns_empty_list(self):
        with patch.object(it, "run_orc", return_value=_completed(stdout="")):
            result = it.list_platform_tools()
        self.assertEqual(result, [])

    def test_no_table_lines_returns_empty_list(self):
        with patch.object(it, "run_orc", return_value=_completed(stdout="No tools found.\n")):
            result = it.list_platform_tools()
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# tool_exists_on_platform
# ---------------------------------------------------------------------------

class TestToolExistsOnPlatform(unittest.TestCase):

    def test_exact_match(self):
        self.assertTrue(it.tool_exists_on_platform("search_bob_documentation",
                                                     ["search_bob_documentation"]))

    def test_miss(self):
        self.assertFalse(it.tool_exists_on_platform("missing_tool",
                                                      ["search_bob_documentation"]))

    def test_prefix_match_handles_truncation(self):
        # ADK table truncates to 20 chars: "search_bob_documenta"
        truncated = ["search_bob_documenta"]
        self.assertTrue(it.tool_exists_on_platform("search_bob_documentation", truncated))

    def test_empty_platform_list(self):
        self.assertFalse(it.tool_exists_on_platform("any_tool", []))


# ---------------------------------------------------------------------------
# import_tool_file
# ---------------------------------------------------------------------------

class TestImportToolFile(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.fake_file = self.tmp / "mytool.py"
        self.fake_file.write_text("# empty\n")

    def test_success_returns_true(self):
        output = "[INFO] - Tool 'my_tool' imported successfully\n"
        with patch.object(it, "run_orc", return_value=_completed(stdout=output)):
            result = it.import_tool_file(self.fake_file)
        self.assertTrue(result)

    def test_failure_returns_false(self):
        with patch.object(it, "run_orc", return_value=_completed(returncode=1, stderr="error")):
            result = it.import_tool_file(self.fake_file)
        self.assertFalse(result)

    def test_dry_run_does_not_call_run_orc(self):
        with patch.object(it, "run_orc") as mock_orc:
            result = it.import_tool_file(self.fake_file, dry_run=True)
        mock_orc.assert_not_called()
        self.assertTrue(result)

    def test_correct_cli_args_passed(self):
        with patch.object(it, "run_orc", return_value=_completed()) as mock_orc:
            it.import_tool_file(self.fake_file)
        args_passed = mock_orc.call_args[0][0]
        self.assertIn("tools", args_passed)
        self.assertIn("import", args_passed)
        self.assertIn("-k", args_passed)
        self.assertIn("python", args_passed)
        self.assertIn("-f", args_passed)


# ---------------------------------------------------------------------------
# validate_agent_yaml_tools
# ---------------------------------------------------------------------------

class TestValidateAgentYamlTools(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_all_tools_present_returns_empty(self):
        yaml_path = self.tmp / "agent.yaml"
        yaml_path.write_text("tools:\n  - search_bob_documentation\n  - get_bob_doc_section\n")
        missing = it.validate_agent_yaml_tools(
            yaml_path, ["search_bob_documentation", "get_bob_doc_section"]
        )
        self.assertEqual(missing, [])

    def test_missing_tool_returned(self):
        yaml_path = self.tmp / "agent.yaml"
        yaml_path.write_text("tools:\n  - search_bob_documentation\n")
        missing = it.validate_agent_yaml_tools(
            yaml_path, ["search_bob_documentation", "get_bob_doc_section"]
        )
        self.assertIn("get_bob_doc_section", missing)
        self.assertNotIn("search_bob_documentation", missing)

    def test_missing_yaml_file_returns_empty(self):
        missing = it.validate_agent_yaml_tools(
            self.tmp / "nonexistent.yaml", ["some_tool"]
        )
        self.assertEqual(missing, [])


# ---------------------------------------------------------------------------
# redeploy_agent
# ---------------------------------------------------------------------------

class TestRedeployAgent(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.yaml = self.tmp / "agent.yaml"
        self.yaml.write_text("name: test_agent\n")

    def test_success_returns_true(self):
        output = "[INFO] - Agent 'ibm_bob_assistant' updated successfully\n"
        with patch.object(it, "run_orc", return_value=_completed(stdout=output)):
            result = it.redeploy_agent(self.yaml)
        self.assertTrue(result)

    def test_failure_returns_false(self):
        with patch.object(it, "run_orc", return_value=_completed(returncode=1)):
            result = it.redeploy_agent(self.yaml)
        self.assertFalse(result)

    def test_dry_run_does_not_call_run_orc(self):
        with patch.object(it, "run_orc") as mock_orc:
            result = it.redeploy_agent(self.yaml, dry_run=True)
        mock_orc.assert_not_called()
        self.assertTrue(result)

    def test_correct_cli_args_passed(self):
        with patch.object(it, "run_orc", return_value=_completed()) as mock_orc:
            it.redeploy_agent(self.yaml)
        args_passed = mock_orc.call_args[0][0]
        self.assertIn("agents", args_passed)
        self.assertIn("import", args_passed)
        self.assertIn("-f", args_passed)


# ---------------------------------------------------------------------------
# get_active_environment
# ---------------------------------------------------------------------------

class TestGetActiveEnvironment(unittest.TestCase):

    def test_extracts_active_name(self):
        output = (
            " aam-wxo-be   https://api.eu-de.example.com  (active)\n"
            " local        http://localhost:4321\n"
        )
        with patch.object(it, "run_orc", return_value=_completed(stdout=output)):
            name = it.get_active_environment()
        self.assertEqual(name, "aam-wxo-be")

    def test_no_active_env_returns_unknown(self):
        output = " local   http://localhost:4321\n"
        with patch.object(it, "run_orc", return_value=_completed(stdout=output)):
            name = it.get_active_environment()
        self.assertEqual(name, "<unknown>")

    def test_empty_output_returns_unknown(self):
        with patch.object(it, "run_orc", return_value=_completed(stdout="")):
            name = it.get_active_environment()
        self.assertEqual(name, "<unknown>")


# ---------------------------------------------------------------------------
# write_json_report
# ---------------------------------------------------------------------------

class TestWriteJsonReport(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # Temporarily redirect OUTPUT_DIR to tmp
        self._orig_output_dir = it.OUTPUT_DIR
        it.OUTPUT_DIR = self.tmp

    def tearDown(self):
        it.OUTPUT_DIR = self._orig_output_dir

    def test_file_created(self):
        report = it.OrchestrationReport(
            run_at="2026-10-26T00:00:00Z",
            environment="aam-wxo-be",
            overall_status="ok",
        )
        path = it.write_json_report(report)
        self.assertTrue(path.exists())

    def test_json_is_valid(self):
        report = it.OrchestrationReport(run_at="2026-10-26T00:00:00Z")
        path = it.write_json_report(report)
        data = json.loads(path.read_text())
        self.assertIsInstance(data, dict)

    def test_required_keys_present(self):
        report = it.OrchestrationReport(
            run_at="2026-10-26T00:00:00Z",
            environment="test-env",
            overall_status="ok",
            dry_run=False,
        )
        path = it.write_json_report(report)
        data = json.loads(path.read_text())
        for key in ("run_at", "environment", "overall_status", "dry_run", "tool_results"):
            self.assertIn(key, data)

    def test_filename_contains_timestamp(self):
        report = it.OrchestrationReport(run_at="2026-01-01T00:00:00Z")
        path = it.write_json_report(report)
        self.assertTrue(path.name.startswith("tool_import_report_"))
        self.assertTrue(path.name.endswith(".json"))


# ---------------------------------------------------------------------------
# Dataclass defaults
# ---------------------------------------------------------------------------

class TestDataclassDefaults(unittest.TestCase):

    def test_tool_import_result_defaults(self):
        tr = it.ToolImportResult(file="tools/x.py", expected_tools=["my_tool"])
        self.assertEqual(tr.already_present, [])
        self.assertEqual(tr.imported, [])
        self.assertEqual(tr.verified, [])
        self.assertEqual(tr.failed, [])
        self.assertFalse(tr.import_attempted)
        self.assertEqual(tr.status, "pending")

    def test_orchestration_report_defaults(self):
        r = it.OrchestrationReport()
        self.assertEqual(r.run_at, "")
        self.assertEqual(r.environment, "")
        self.assertFalse(r.dry_run)
        self.assertFalse(r.agent_redeployed)
        self.assertEqual(r.tool_results, [])
        self.assertEqual(r.overall_status, "pending")
        self.assertEqual(r.warnings, [])


# ---------------------------------------------------------------------------
# run() — dry-run smoke test
# ---------------------------------------------------------------------------

class TestRunDryRun(unittest.TestCase):
    """
    Smoke-tests the top-level run() function with all external calls mocked.
    We verify that dry-run produces an 'ok' report without touching the platform.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

        # Write a minimal .env file
        self.env_file = self.tmp / ".env"
        self.env_file.write_text(
            "ORCHESTRATE_URL=https://api.eu-de.example.com/instances/test\n"
            "IBM_CLOUD_API_KEY=fakekey\n"
        )

        # Write a minimal agent YAML that references both tool names
        self.agent_yaml = self.tmp / "ibm_bob_assistant.agent.yaml"
        self.agent_yaml.write_text(
            "name: ibm_bob_assistant\n"
            "tools:\n"
            "  - search_bob_documentation\n"
            "  - get_bob_doc_section\n"
        )

    def _run_with_mocks(self, **run_kwargs):
        """Helper: call run() with all platform I/O mocked out."""
        with (
            patch.object(it, "check_cli_available", return_value="2.18.1"),
            patch.object(it, "get_active_environment", return_value="aam-wxo-be"),
            patch.object(it, "list_platform_tools", return_value=[]),
            patch.object(it, "import_tool_file", return_value=True),
            patch.object(it, "redeploy_agent", return_value=True),
            patch.object(it, "AGENT_YAML", self.agent_yaml),
            patch.object(it, "write_json_report"),  # don't write files in tests
        ):
            return it.run(env_file=self.env_file, **run_kwargs)

    def test_dry_run_returns_ok(self):
        report = self._run_with_mocks(dry_run=True)
        self.assertEqual(report.overall_status, "ok")
        self.assertTrue(report.dry_run)

    def test_all_tool_results_present(self):
        report = self._run_with_mocks(dry_run=True)
        # One entry per TOOL_FILES entry
        self.assertEqual(len(report.tool_results), len(it.TOOL_FILES))

    def test_environment_captured(self):
        report = self._run_with_mocks(dry_run=True)
        self.assertEqual(report.environment, "aam-wxo-be")

    def test_skip_agent_deploy_flag(self):
        with (
            patch.object(it, "check_cli_available", return_value="2.18.1"),
            patch.object(it, "get_active_environment", return_value="aam-wxo-be"),
            patch.object(it, "list_platform_tools", return_value=[]),
            patch.object(it, "import_tool_file", return_value=True),
            patch.object(it, "redeploy_agent") as mock_redeploy,
            patch.object(it, "AGENT_YAML", self.agent_yaml),
        ):
            report = it.run(
                env_file=self.env_file,
                dry_run=True,
                skip_agent_deploy=True,
            )
        mock_redeploy.assert_not_called()
        self.assertFalse(report.agent_redeployed)

    def test_force_reimport_triggers_import(self):
        with (
            patch.object(it, "check_cli_available", return_value="2.18.1"),
            patch.object(it, "get_active_environment", return_value="aam-wxo-be"),
            patch.object(it, "list_platform_tools", return_value=["search_bob_documentation", "get_bob_doc_section"]),
            patch.object(it, "import_tool_file", return_value=True) as mock_import,
            patch.object(it, "redeploy_agent", return_value=True),
            patch.object(it, "AGENT_YAML", self.agent_yaml),
        ):
            it.run(
                env_file=self.env_file,
                dry_run=False,
                force_reimport=True,
                skip_agent_deploy=True,
            )
        # With force_reimport=True, import_tool_file must be called even when
        # all tools are already present
        mock_import.assert_called()

    def test_failed_import_sets_overall_failed(self):
        with (
            patch.object(it, "check_cli_available", return_value="2.18.1"),
            patch.object(it, "get_active_environment", return_value="aam-wxo-be"),
            patch.object(it, "list_platform_tools", return_value=[]),
            patch.object(it, "import_tool_file", return_value=False),  # simulate failure
            patch.object(it, "redeploy_agent", return_value=True),
            patch.object(it, "AGENT_YAML", self.agent_yaml),
        ):
            report = it.run(env_file=self.env_file, skip_agent_deploy=True)
        self.assertEqual(report.overall_status, "failed")


# ---------------------------------------------------------------------------
# TOOL_FILES registry sanity checks
# ---------------------------------------------------------------------------

class TestToolFilesRegistry(unittest.TestCase):
    """Validate the TOOL_FILES constant against the actual source files."""

    def test_all_registry_files_exist(self):
        for entry in it.TOOL_FILES:
            path = it._PROJECT_ROOT / entry["file"]
            self.assertTrue(
                path.exists(),
                f"Registry references {entry['file']} but file does not exist",
            )

    def test_registry_tools_match_ast_discovery(self):
        """The declared tool names must match what AST discovers in each file."""
        for entry in it.TOOL_FILES:
            path = it._PROJECT_ROOT / entry["file"]
            if not path.exists():
                continue
            discovered = it.discover_tools_in_file(path)
            self.assertEqual(
                sorted(discovered),
                sorted(entry["tools"]),
                f"TOOL_FILES registry mismatch for {entry['file']}: "
                f"declared={sorted(entry['tools'])!r}, "
                f"discovered={sorted(discovered)!r}",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
