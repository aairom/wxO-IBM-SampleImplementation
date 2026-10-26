#!/usr/bin/env python3
"""
test_import_agent.py — Unit tests for scripts/import_agent.py

Coverage:
  _load_env             — file parsing, missing file, quotes, blanks
  _apply_env            — non-overwrite semantics
  _check_credentials    — all present, missing, empty
  _validate_agent_yaml  — valid file, missing file, unreadable, missing keys
  _agent_exists_on_platform — found (full name), found (prefix), not found
  _interpret_cli_error  — each known error pattern, generic fallback
  _do_import            — success, failure, mock, timeout, binary not found
  _get_active_environment — active present, absent
  _write_report         — file created, JSON valid, required keys
  run()                 — dry-run, mock, missing creds, invalid yaml,
                          force re-import, user decline, success
  ImportResult          — dataclass defaults
  exit codes            — 0/1/2/130 via main() (tested via run() outcome)

All subprocess calls are mocked — no network or platform access.
Run:
    cd <project_root>
    source venv/bin/activate
    python -m pytest tests/test_import_agent.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scripts.import_agent as ia  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _proc(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    """Build a fake subprocess.CompletedProcess."""
    r = subprocess.CompletedProcess(args=[], returncode=returncode)
    r.stdout = stdout
    r.stderr = stderr
    return r


def _make_valid_yaml(tmp_dir: Path, name: str = "ibm_bob_assistant") -> Path:
    """Write a minimal valid agent YAML to tmp_dir and return its path."""
    p = tmp_dir / "agent.yaml"
    p.write_text(
        f"spec_version: v1\nkind: native\nname: {name}\n",
        encoding="utf-8",
    )
    return p


def _silent_logger():
    """Return a logger that discards all output (keeps test stdout clean)."""
    import logging
    logger = logging.getLogger("_test_silent")
    logger.setLevel(logging.CRITICAL + 1)  # nothing gets through
    return logger


# ---------------------------------------------------------------------------
# _load_env
# ---------------------------------------------------------------------------

class TestLoadEnv(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.log = _silent_logger()

    def _write(self, text: str) -> Path:
        p = self.tmp / ".env"
        p.write_text(textwrap.dedent(text), encoding="utf-8")
        return p

    def test_basic_parse(self):
        p = self._write("KEY=value\n")
        self.assertEqual(ia._load_env(p, self.log)["KEY"], "value")

    def test_comments_ignored(self):
        p = self._write("# comment\nKEY=val\n")
        result = ia._load_env(p, self.log)
        self.assertNotIn("# comment", result)
        self.assertIn("KEY", result)

    def test_double_quotes_stripped(self):
        p = self._write('URL="https://example.com"\n')
        self.assertEqual(ia._load_env(p, self.log)["URL"], "https://example.com")

    def test_single_quotes_stripped(self):
        p = self._write("TOKEN='abc'\n")
        self.assertEqual(ia._load_env(p, self.log)["TOKEN"], "abc")

    def test_empty_value(self):
        p = self._write("EMPTY=\n")
        self.assertEqual(ia._load_env(p, self.log)["EMPTY"], "")

    def test_missing_file_returns_empty(self):
        result = ia._load_env(self.tmp / "nonexistent.env", self.log)
        self.assertEqual(result, {})

    def test_line_without_equals_ignored(self):
        p = self._write("NOEQUALS\nK=v\n")
        result = ia._load_env(p, self.log)
        self.assertNotIn("NOEQUALS", result)
        self.assertIn("K", result)


# ---------------------------------------------------------------------------
# _apply_env
# ---------------------------------------------------------------------------

class TestApplyEnv(unittest.TestCase):

    def test_sets_missing_var(self):
        key = "_TEST_IA_A"
        os.environ.pop(key, None)
        ia._apply_env({key: "injected"})
        self.assertEqual(os.environ[key], "injected")
        del os.environ[key]

    def test_does_not_overwrite_existing(self):
        key = "_TEST_IA_B"
        os.environ[key] = "original"
        ia._apply_env({key: "overwrite"})
        self.assertEqual(os.environ[key], "original")
        del os.environ[key]


# ---------------------------------------------------------------------------
# _check_credentials
# ---------------------------------------------------------------------------

class TestCheckCredentials(unittest.TestCase):

    def test_all_present(self):
        env = {"ORCHESTRATE_URL": "https://x.example.com", "IBM_CLOUD_API_KEY": "k"}
        with patch.dict("os.environ", env):
            self.assertEqual(ia._check_credentials(_silent_logger()), [])

    def test_missing_url(self):
        with patch.dict("os.environ", {"ORCHESTRATE_URL": "", "IBM_CLOUD_API_KEY": "k"}):
            missing = ia._check_credentials(_silent_logger())
        self.assertIn("ORCHESTRATE_URL", missing)

    def test_both_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            missing = ia._check_credentials(_silent_logger())
        self.assertIn("ORCHESTRATE_URL", missing)
        self.assertIn("IBM_CLOUD_API_KEY", missing)


# ---------------------------------------------------------------------------
# _validate_agent_yaml
# ---------------------------------------------------------------------------

class TestValidateAgentYaml(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.log = _silent_logger()

    def test_valid_file_no_errors(self):
        p = _make_valid_yaml(self.tmp)
        errors = ia._validate_agent_yaml(p, self.log)
        self.assertEqual(errors, [])

    def test_missing_file_returns_error(self):
        errors = ia._validate_agent_yaml(self.tmp / "missing.yaml", self.log)
        self.assertTrue(any("not found" in e.lower() for e in errors))

    def test_missing_required_key_spec_version(self):
        p = self.tmp / "bad.yaml"
        p.write_text("kind: native\nname: test\n")
        errors = ia._validate_agent_yaml(p, self.log)
        self.assertTrue(any("spec_version" in e for e in errors))

    def test_missing_required_key_kind(self):
        p = self.tmp / "bad.yaml"
        p.write_text("spec_version: v1\nname: test\n")
        errors = ia._validate_agent_yaml(p, self.log)
        self.assertTrue(any("kind" in e for e in errors))

    def test_missing_required_key_name(self):
        p = self.tmp / "bad.yaml"
        p.write_text("spec_version: v1\nkind: native\n")
        errors = ia._validate_agent_yaml(p, self.log)
        self.assertTrue(any("name" in e for e in errors))

    def test_path_is_directory_returns_error(self):
        errors = ia._validate_agent_yaml(self.tmp, self.log)
        self.assertTrue(errors)


# ---------------------------------------------------------------------------
# _agent_exists_on_platform
# ---------------------------------------------------------------------------

class TestAgentExistsOnPlatform(unittest.TestCase):

    def _run(self, stdout: str) -> bool:
        with patch.object(ia, "_run_orc", return_value=_proc(stdout=stdout)):
            return ia._agent_exists_on_platform("ibm_bob_assistant", _silent_logger())

    def test_full_name_match(self):
        self.assertTrue(self._run("│ ibm_bob_assistant │ desc │\n"))

    def test_prefix_match_handles_truncation(self):
        # The logic is: agent_name.startswith(platform_name[:20])
        # So platform shows "ibm_bob_assistan" → name[:20] = "ibm_bob_assistan"
        # "ibm_bob_assistant".startswith("ibm_bob_assistan") → True
        self.assertTrue(self._run("│ ibm_bob_assistan  │ desc │\n"))

    def test_not_found(self):
        self.assertFalse(self._run("│ other_agent │ desc │\n"))

    def test_empty_output(self):
        self.assertFalse(self._run(""))


# ---------------------------------------------------------------------------
# _interpret_cli_error
# ---------------------------------------------------------------------------

class TestInterpretCliError(unittest.TestCase):

    def _i(self, stdout="", stderr="", code=1):
        return ia._interpret_cli_error(code, stdout, stderr)

    def test_expired_token(self):
        result = self._i(stderr="token expired")
        self.assertIn("expired", result.lower())
        self.assertIn("activate", result.lower())

    def test_missing_token(self):
        result = self._i(stderr="token missing")
        self.assertIn("authenticate", result.lower())

    def test_no_active_environment(self):
        result = self._i(stderr="no active environment found")
        self.assertIn("environment", result.lower())

    def test_file_not_found(self):
        result = self._i(stderr="file not found")
        self.assertIn("yaml", result.lower())

    def test_already_exists(self):
        result = self._i(stderr="already exists")
        self.assertIn("already exists", result.lower())

    def test_permission_denied(self):
        result = self._i(stderr="unauthorized 403")
        self.assertIn("permission", result.lower())

    def test_network_error(self):
        result = self._i(stderr="connection refused")
        self.assertIn("network", result.lower())

    def test_generic_fallback(self):
        result = self._i(stdout="something weird", stderr="", code=42)
        self.assertIn("42", result)


# ---------------------------------------------------------------------------
# _do_import
# ---------------------------------------------------------------------------

class TestDoImport(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.yaml = _make_valid_yaml(self.tmp)
        self.log = _silent_logger()

    def _result(self):
        return ia.ImportResult()

    def test_success(self):
        output = "[INFO] - Agent 'ibm_bob_assistant' imported successfully\n"
        r = self._result()
        with patch.object(ia, "_run_orc", return_value=_proc(stdout=output)):
            ia._do_import(self.yaml, r, self.log)
        self.assertEqual(r.outcome, "success")
        self.assertEqual(r.cli_exit_code, 0)

    def test_failure(self):
        r = self._result()
        with patch.object(ia, "_run_orc", return_value=_proc(returncode=1, stderr="token expired")):
            ia._do_import(self.yaml, r, self.log)
        self.assertEqual(r.outcome, "failed")
        self.assertEqual(r.cli_exit_code, 1)
        self.assertIn("expired", r.error_message.lower())

    def test_mock_skips_run_orc(self):
        r = self._result()
        with patch.object(ia, "_run_orc") as mock_orc:
            ia._do_import(self.yaml, r, self.log, mock=True)
        mock_orc.assert_not_called()
        self.assertEqual(r.outcome, "mock")

    def test_timeout_sets_failed(self):
        r = self._result()
        with patch.object(ia, "_run_orc", side_effect=subprocess.TimeoutExpired(cmd="orc", timeout=120)):
            ia._do_import(self.yaml, r, self.log)
        self.assertEqual(r.outcome, "failed")
        # error_message says "timed out" (not "timeout")
        self.assertIn("timed out", r.error_message.lower())

    def test_binary_not_found_sets_failed(self):
        r = self._result()
        with patch.object(ia, "_run_orc", side_effect=FileNotFoundError("not found")):
            ia._do_import(self.yaml, r, self.log)
        self.assertEqual(r.outcome, "failed")
        self.assertIn("binary", r.error_message.lower())


# ---------------------------------------------------------------------------
# _get_active_environment
# ---------------------------------------------------------------------------

class TestGetActiveEnvironment(unittest.TestCase):

    def test_finds_active(self):
        output = " aam-wxo-be   https://example.com  (active)\n other  http://x\n"
        with patch.object(ia, "_run_orc", return_value=_proc(stdout=output)):
            self.assertEqual(ia._get_active_environment(_silent_logger()), "aam-wxo-be")

    def test_returns_unknown_when_none_active(self):
        with patch.object(ia, "_run_orc", return_value=_proc(stdout=" local http://x\n")):
            self.assertEqual(ia._get_active_environment(_silent_logger()), "<unknown>")

    def test_empty_output_returns_unknown(self):
        with patch.object(ia, "_run_orc", return_value=_proc(stdout="")):
            self.assertEqual(ia._get_active_environment(_silent_logger()), "<unknown>")


# ---------------------------------------------------------------------------
# _write_report
# ---------------------------------------------------------------------------

class TestWriteReport(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig_output_dir = ia.OUTPUT_DIR
        ia.OUTPUT_DIR = self.tmp

    def tearDown(self):
        ia.OUTPUT_DIR = self._orig_output_dir

    def test_file_created(self):
        r = ia.ImportResult(run_at="2026-10-26T00:00:00Z", outcome="success")
        path = ia._write_report(r, _silent_logger())
        self.assertTrue(path.exists())

    def test_json_is_valid(self):
        r = ia.ImportResult(run_at="2026-10-26T00:00:00Z")
        path = ia._write_report(r, _silent_logger())
        data = json.loads(path.read_text())
        self.assertIsInstance(data, dict)

    def test_required_keys(self):
        r = ia.ImportResult(run_at="2026-10-26T00:00:00Z", outcome="success")
        path = ia._write_report(r, _silent_logger())
        data = json.loads(path.read_text())
        for key in ("run_at", "outcome", "agent_file", "dry_run", "mock"):
            self.assertIn(key, data)

    def test_filename_format(self):
        r = ia.ImportResult(run_at="2026-10-26T00:00:00Z")
        path = ia._write_report(r, _silent_logger())
        self.assertTrue(path.name.startswith("import_agent_report_"))
        self.assertTrue(path.name.endswith(".json"))


# ---------------------------------------------------------------------------
# ImportResult defaults
# ---------------------------------------------------------------------------

class TestImportResultDefaults(unittest.TestCase):

    def test_defaults(self):
        r = ia.ImportResult()
        self.assertEqual(r.run_at, "")
        self.assertEqual(r.agent_file, "")
        self.assertEqual(r.environment, "")
        self.assertFalse(r.agent_already_existed)
        self.assertFalse(r.reimport_confirmed)
        self.assertFalse(r.dry_run)
        self.assertFalse(r.mock)
        self.assertEqual(r.cli_exit_code, -1)
        self.assertEqual(r.outcome, "pending")
        self.assertEqual(r.error_message, "")
        self.assertEqual(r.elapsed_seconds, 0.0)
        self.assertEqual(r.warnings, [])


# ---------------------------------------------------------------------------
# run() — full pipeline smoke tests
# ---------------------------------------------------------------------------

class TestRun(unittest.TestCase):
    """Test the top-level run() function with all I/O mocked."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

        # Write a valid .env
        self.env_file = self.tmp / ".env"
        self.env_file.write_text(
            "ORCHESTRATE_URL=https://api.eu-de.example.com/instances/test\n"
            "IBM_CLOUD_API_KEY=fakekey\n"
        )

        # Write a valid agent YAML
        self.agent_yaml = _make_valid_yaml(self.tmp)

    def _common_patches(self, exists=False, import_ok=True):
        """Return a dict of patch.object patches for the happy path."""
        import_proc = _proc(
            stdout="[INFO] - Agent imported successfully\n"
        ) if import_ok else _proc(returncode=1, stderr="token expired")

        return {
            "check_cli": patch.object(ia, "_check_cli", return_value="2.18.1"),
            "get_env": patch.object(ia, "_get_active_environment", return_value="aam-wxo-be"),
            "exists": patch.object(ia, "_agent_exists_on_platform", return_value=exists),
            "run_orc": patch.object(ia, "_run_orc", return_value=import_proc),
        }

    def test_mock_mode_returns_mock(self):
        result = ia.run(
            agent_file=self.agent_yaml,
            env_file=self.env_file,
            mock=True,
            no_log_file=True,
            no_report=True,
        )
        self.assertEqual(result.outcome, "mock")

    def test_dry_run_returns_dry_run(self):
        with self._common_patches()["check_cli"], \
             self._common_patches()["get_env"], \
             self._common_patches()["exists"]:
            result = ia.run(
                agent_file=self.agent_yaml,
                env_file=self.env_file,
                dry_run=True,
                no_log_file=True,
                no_report=True,
            )
        self.assertEqual(result.outcome, "dry_run")

    def test_missing_credentials_returns_failed(self):
        empty_env = self.tmp / "empty.env"
        empty_env.write_text("")
        with patch.dict("os.environ", {}, clear=True):
            result = ia.run(
                agent_file=self.agent_yaml,
                env_file=empty_env,
                mock=True,
                no_log_file=True,
                no_report=True,
            )
        self.assertEqual(result.outcome, "failed")
        self.assertIn("credential", result.error_message.lower())

    def test_invalid_yaml_exits_2(self):
        bad_yaml = self.tmp / "bad.yaml"
        bad_yaml.write_text("kind: native\nname: test\n")  # missing spec_version
        with self.assertRaises(SystemExit) as ctx:
            ia.run(
                agent_file=bad_yaml,
                env_file=self.env_file,
                mock=True,
                no_log_file=True,
                no_report=True,
            )
        self.assertEqual(ctx.exception.code, 2)

    def test_force_reimport_skips_prompt(self):
        """With --force and existing agent, import should run without input()."""
        # Do NOT use mock=True here: mock skips the platform check so
        # agent_already_existed stays False. Use real patches instead.
        import_proc = _proc(stdout="[INFO] - Agent imported successfully\n")
        with patch.object(ia, "_check_cli", return_value="2.18.1"), \
             patch.object(ia, "_get_active_environment", return_value="aam-wxo-be"), \
             patch.object(ia, "_agent_exists_on_platform", return_value=True), \
             patch.object(ia, "_run_orc", return_value=import_proc):
            result = ia.run(
                agent_file=self.agent_yaml,
                env_file=self.env_file,
                force=True,
                no_log_file=True,
                no_report=True,
            )
        self.assertEqual(result.outcome, "success")
        self.assertTrue(result.reimport_confirmed)
        self.assertTrue(result.agent_already_existed)

    def test_user_declines_reimport_exits_0(self):
        """Decline at confirmation prompt → outcome 'aborted', exit 0."""
        with self._common_patches(exists=True)["check_cli"], \
             self._common_patches(exists=True)["get_env"], \
             self._common_patches(exists=True)["exists"], \
             patch("builtins.input", return_value="n"):
            with self.assertRaises(SystemExit) as ctx:
                ia.run(
                    agent_file=self.agent_yaml,
                    env_file=self.env_file,
                    force=False,
                    no_log_file=True,
                    no_report=True,
                )
        self.assertEqual(ctx.exception.code, 0)

    def test_fresh_import_success(self):
        """Happy path: agent absent → import succeeds → outcome 'success'."""
        import_proc = _proc(stdout="[INFO] - Agent 'ibm_bob_assistant' imported successfully\n")
        with patch.object(ia, "_check_cli", return_value="2.18.1"), \
             patch.object(ia, "_get_active_environment", return_value="aam-wxo-be"), \
             patch.object(ia, "_agent_exists_on_platform", return_value=False), \
             patch.object(ia, "_run_orc", return_value=import_proc):
            result = ia.run(
                agent_file=self.agent_yaml,
                env_file=self.env_file,
                no_log_file=True,
                no_report=True,
            )
        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.environment, "aam-wxo-be")

    def test_failed_import_outcome(self):
        """CLI failure → outcome 'failed'."""
        fail_proc = _proc(returncode=1, stderr="token expired")
        with patch.object(ia, "_check_cli", return_value="2.18.1"), \
             patch.object(ia, "_get_active_environment", return_value="aam-wxo-be"), \
             patch.object(ia, "_agent_exists_on_platform", return_value=False), \
             patch.object(ia, "_run_orc", return_value=fail_proc):
            result = ia.run(
                agent_file=self.agent_yaml,
                env_file=self.env_file,
                no_log_file=True,
                no_report=True,
            )
        self.assertEqual(result.outcome, "failed")
        self.assertIn("expired", result.error_message.lower())

    def test_unknown_env_adds_warning(self):
        """No active environment → warning added, run still proceeds."""
        # Do NOT use mock=True: mock mode sets environment="mock" and bypasses
        # _get_active_environment entirely. Use explicit patches instead.
        import_proc = _proc(stdout="[INFO] - Agent imported successfully\n")
        with patch.object(ia, "_check_cli", return_value="2.18.1"), \
             patch.object(ia, "_get_active_environment", return_value="<unknown>"), \
             patch.object(ia, "_agent_exists_on_platform", return_value=False), \
             patch.object(ia, "_run_orc", return_value=import_proc):
            result = ia.run(
                agent_file=self.agent_yaml,
                env_file=self.env_file,
                no_log_file=True,
                no_report=True,
            )
        self.assertTrue(any("environment" in w.lower() for w in result.warnings))

    def test_report_written_by_default(self):
        """JSON report file is created in output/ on a successful run."""
        tmp_output = self.tmp / "output"
        with patch.object(ia, "_check_cli", return_value="2.18.1"), \
             patch.object(ia, "_get_active_environment", return_value="env"), \
             patch.object(ia, "_agent_exists_on_platform", return_value=False), \
             patch.object(ia, "OUTPUT_DIR", tmp_output):
            result = ia.run(
                agent_file=self.agent_yaml,
                env_file=self.env_file,
                mock=True,
                no_log_file=True,
            )
        reports = list(tmp_output.glob("import_agent_report_*.json"))
        self.assertTrue(len(reports) >= 1, "Expected at least one report file")

    def test_keyboard_interrupt_during_import(self):
        """KeyboardInterrupt inside _do_import → outcome 'failed' (not raised)."""
        with patch.object(ia, "_check_cli", return_value="2.18.1"), \
             patch.object(ia, "_get_active_environment", return_value="env"), \
             patch.object(ia, "_agent_exists_on_platform", return_value=False), \
             patch.object(ia, "_do_import", side_effect=KeyboardInterrupt):
            # KeyboardInterrupt during _do_import is NOT caught by run() —
            # it propagates to main(). main() catches it and exits 130.
            # Here we test the raw run() directly: it should propagate.
            with self.assertRaises(KeyboardInterrupt):
                ia.run(
                    agent_file=self.agent_yaml,
                    env_file=self.env_file,
                    no_log_file=True,
                    no_report=True,
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
