#!/usr/bin/env python3
"""
import_agent.py — Standalone, production-ready script for importing the
IBM Bob Assistant agent into a watsonx Orchestrate (wxO) environment.

===============================================================================
WHAT THIS SCRIPT DOES
===============================================================================
Encapsulates the single operation:

    orchestrate agents import -f agents/ibm_bob_assistant.agent.yaml

…with full validation, structured logging, idempotency checks, dry-run
support, and a machine-readable JSON report.

Use this script when you need to import or re-import the agent independently
of the full start.sh pipeline — for example:

  • After editing agent instructions without changing the KB or tools
  • In a CI/CD pipeline that manages KB and tools separately
  • When troubleshooting agent behaviour and need a quick re-deploy
  • From a Makefile or other automation that calls individual steps

For a full deployment (auth + KB + tools + agent), use start.sh instead.

===============================================================================
USAGE
===============================================================================
  # Typical first-time or re-import
  python scripts/import_agent.py

  # Import an alternative YAML file
  python scripts/import_agent.py -f agents/my_other_agent.agent.yaml

  # Dry-run: validate without executing
  python scripts/import_agent.py --dry-run

  # Re-import without confirmation prompt
  python scripts/import_agent.py --force

  # Detailed logging (shows every CLI command and output)
  python scripts/import_agent.py --verbose

  # Mock mode — simulates success without hitting the platform (for testing)
  python scripts/import_agent.py --mock

===============================================================================
EXIT CODES
===============================================================================
  0   Success — agent imported (or would be imported in dry-run / mock mode)
  1   Runtime/execution error — CLI failed, network error, unexpected output
  2   Configuration/validation error — missing file, missing credentials
  130 User interrupted (Ctrl+C)

===============================================================================
INTEGRATION WITH start.sh
===============================================================================
  start.sh calls import_agent.py implicitly in Step 6. This script can also
  be called standalone:

    python scripts/import_agent.py --force   # skip confirmation

  Or from a CI/CD pipeline:

    python scripts/import_agent.py --force --no-log-file
    echo "exit: $?"

===============================================================================
TROUBLESHOOTING
===============================================================================
  "Token expired / missing"
      Run: orchestrate env activate <env-name> --api-key $IBM_CLOUD_API_KEY
      Then retry this script.

  "No active environment"
      Run: orchestrate env list   to see registered envs
      Run: orchestrate env activate <name> --api-key $IBM_CLOUD_API_KEY

  "Agent file not found"
      Ensure agents/ibm_bob_assistant.agent.yaml exists. Check --agent-file.

  "Import succeeded but agent not responding"
      Tools or KB may be missing. Run the full pipeline: ./scripts/start.sh

  See Docs/IMPORT_AGENT_GUIDE.md for the complete troubleshooting reference.

===============================================================================
MAINTAINING AND UPDATING
===============================================================================
  To switch the default agent YAML:
      Edit DEFAULT_AGENT_YAML below.

  To add pre-import checks (e.g. lint the YAML):
      Add a step in _validate_prerequisites().

  To wire into CI/CD:
      Call with --force --mock in test stages.
      Call with --force in deploy stages.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Project layout constants
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _SCRIPT_DIR.parent.resolve()

#: Default agent YAML to import (relative to project root)
DEFAULT_AGENT_YAML = _PROJECT_ROOT / "agents" / "ibm_bob_assistant.agent.yaml"

#: Path to the orchestrate CLI inside the project venv
ORC_BIN = _PROJECT_ROOT / "venv" / "bin" / "orchestrate"

#: Default .env file path
DEFAULT_ENV_FILE = _PROJECT_ROOT / ".env"

#: Log directory (created automatically if absent)
LOG_DIR = _PROJECT_ROOT / "logs"

#: Output directory for JSON reports
OUTPUT_DIR = _PROJECT_ROOT / "output"

#: Name used in all log messages and the JSON report
AGENT_NAME = "ibm_bob_assistant"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _configure_logging(*, verbose: bool, no_log_file: bool) -> logging.Logger:
    """Configure and return the module logger.

    Attaches a StreamHandler (stdout) and — unless *no_log_file* — a
    RotatingFileHandler writing to ``logs/import_agent.log``.

    Args:
        verbose:     When True, set level to DEBUG; otherwise INFO.
        no_log_file: When True, skip the file handler.

    Returns:
        Configured :class:`logging.Logger` named ``"import_agent"``.
    """
    logger = logging.getLogger("import_agent")
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%H:%M:%S")
    )
    logger.addHandler(console)

    # File handler
    if not no_log_file:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / "import_agent.log"
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)  # always full detail in the file
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
                "%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)

    return logger


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ImportResult:
    """Complete record of a single agent import run.

    All fields are JSON-serialisable so the object can be persisted to
    ``output/import_agent_report_<timestamp>.json`` for monitoring and CI/CD.
    """

    #: ISO-8601 timestamp when the run started
    run_at: str = ""
    #: Path of the agent YAML file that was (or would be) imported
    agent_file: str = ""
    #: Name of the active wxO environment, or "<unknown>"
    environment: str = ""
    #: True if the agent was already present on the platform before this run
    agent_already_existed: bool = False
    #: True if the user confirmed (or --force was passed) for a re-import
    reimport_confirmed: bool = False
    #: True in dry-run mode — no platform changes were made
    dry_run: bool = False
    #: True in mock mode — subprocess was simulated
    mock: bool = False
    #: Raw stdout from the orchestrate CLI
    cli_stdout: str = ""
    #: Raw stderr from the orchestrate CLI
    cli_stderr: str = ""
    #: CLI exit code (or -1 if not run)
    cli_exit_code: int = -1
    #: Human-readable outcome: "success" | "dry_run" | "mock" | "failed" | "aborted"
    outcome: str = "pending"
    #: Optional error message if outcome is "failed" or "aborted"
    error_message: str = ""
    #: Wall-clock seconds for the entire run
    elapsed_seconds: float = 0.0
    #: Any non-fatal warnings collected during the run
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Environment helpers (reuse logic from import_tools.py pattern)
# ---------------------------------------------------------------------------

def _load_env(env_file: Path, logger: logging.Logger) -> dict[str, str]:
    """Parse *env_file* and return a ``{key: value}`` dict.

    Silently returns an empty dict if the file does not exist (credentials
    may already be in the shell environment).

    Args:
        env_file: Path to the .env file.
        logger:   Logger for debug messages.

    Returns:
        Dict of parsed key=value pairs.
    """
    if not env_file.exists():
        logger.debug(".env not found at %s — relying on existing shell env", env_file)
        return {}

    env: dict[str, str] = {}
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            env[key] = value

    logger.debug("Loaded %d variables from %s", len(env), env_file)
    return env


def _apply_env(env: dict[str, str]) -> None:
    """Merge *env* into ``os.environ`` without overwriting existing values.

    Args:
        env: Variables to inject.
    """
    for key, value in env.items():
        os.environ.setdefault(key, value)


def _check_credentials(logger: logging.Logger) -> list[str]:
    """Return a list of missing required credential variable names.

    Required variables:
        ORCHESTRATE_URL       — Full API service URL for the wxO instance
        IBM_CLOUD_API_KEY     — IBM Cloud API key for authentication

    Args:
        logger: Logger for debug output.

    Returns:
        List of variable names that are missing or empty; empty list = OK.
    """
    required = ["ORCHESTRATE_URL", "IBM_CLOUD_API_KEY"]
    missing = [v for v in required if not os.environ.get(v, "").strip()]
    if missing:
        logger.debug("Missing credentials: %s", missing)
    return missing


# ---------------------------------------------------------------------------
# CLI wrapper
# ---------------------------------------------------------------------------

def _rel(path: Path) -> str:
    """Return *path* relative to _PROJECT_ROOT, or its absolute string.

    Handles paths outside the project root (e.g. temp dirs in tests) gracefully.

    Args:
        path: The Path to relativise.

    Returns:
        Relative path string, or absolute string if outside project root.
    """
    try:
        return str(path.relative_to(_PROJECT_ROOT, walk_up=True))
    except (ValueError, TypeError):
        return str(path)


def _run_orc(
    args: list[str],
    logger: logging.Logger,
    *,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """Execute the ``orchestrate`` CLI with the given arguments.

    Always uses ``capture_output=True`` to prevent the ADK pager from
    blocking on interactive TTYs.

    Args:
        args:    CLI arguments appended after the binary path.
        logger:  Logger for debug output of the command and its result.
        timeout: Maximum seconds to wait before raising TimeoutExpired.

    Returns:
        A completed :class:`subprocess.CompletedProcess` instance.
    """
    cmd = [str(ORC_BIN)] + args
    logger.debug("CMD: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    logger.debug("EXIT: %d", result.returncode)
    if result.stdout:
        logger.debug("STDOUT: %s", result.stdout[:800])
    if result.stderr:
        logger.debug("STDERR: %s", result.stderr[:400])

    return result


def _check_cli(logger: logging.Logger) -> str:
    """Verify the ``orchestrate`` CLI binary is present and return its version.

    Args:
        logger: Logger for output.

    Returns:
        Version string (first line of ``--version`` output).

    Raises:
        SystemExit(2): If the binary is not found or not executable.
    """
    if not ORC_BIN.is_file() or not os.access(ORC_BIN, os.X_OK):
        logger.error(
            "orchestrate CLI not found at %s\n"
            "  Run: source venv/bin/activate && pip install ibm-watsonx-orchestrate",
            ORC_BIN,
        )
        sys.exit(2)

    result = _run_orc(["--version"], logger)
    lines = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()
    version = lines[0] if lines else "unknown"
    logger.debug("CLI version: %s", version)
    return version


def _get_active_environment(logger: logging.Logger) -> str:
    """Return the name of the currently active wxO environment.

    Parses the ``(active)`` marker in ``orchestrate env list`` output.

    Args:
        logger: Logger for debug output.

    Returns:
        Environment name string, or ``"<unknown>"`` if none is active.
    """
    result = _run_orc(["env", "list"], logger)
    for line in (result.stdout or "").splitlines():
        if "(active)" in line:
            return line.strip().split()[0]
    return "<unknown>"


# ---------------------------------------------------------------------------
# Agent existence check
# ---------------------------------------------------------------------------

def _agent_exists_on_platform(agent_name: str, logger: logging.Logger) -> bool:
    """Return True if *agent_name* is already registered on the platform.

    Uses ``orchestrate agents list`` and scans the table output for the name.
    Because the table truncates long names, it also accepts prefix matches
    (first 20 characters).

    Args:
        agent_name: The exact agent name to look for.
        logger:     Logger for debug output.

    Returns:
        True if found, False otherwise.
    """
    result = _run_orc(["agents", "list"], logger)
    output = result.stdout or ""
    # Full name match (no truncation)
    if agent_name in output:
        return True
    # Truncation match: ADK table may cut names at ~20 chars.
    # Check whether any whitespace-delimited token in the output is a
    # leading prefix of our agent name (e.g. "ibm_bob_assistan" is a
    # prefix of "ibm_bob_assistant").
    for token in output.split():
        if len(token) >= 10 and agent_name.startswith(token):
            return True
    return False


# ---------------------------------------------------------------------------
# YAML validation
# ---------------------------------------------------------------------------

def _validate_agent_yaml(agent_file: Path, logger: logging.Logger) -> list[str]:
    """Validate that *agent_file* is a readable, minimally valid agent YAML.

    Reads the file as plain text and checks for the presence of the required
    top-level keys (``spec_version``, ``kind``, ``name``).  Avoids a PyYAML
    dependency by checking string presence.

    Args:
        agent_file: Path to the agent YAML file.
        logger:     Logger for messages.

    Returns:
        List of validation error strings; empty = file is valid.
    """
    errors: list[str] = []

    if not agent_file.exists():
        errors.append(f"Agent YAML not found: {agent_file}")
        return errors  # nothing more to check

    if not agent_file.is_file():
        errors.append(f"Path is not a file: {agent_file}")
        return errors

    try:
        content = agent_file.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"Cannot read agent YAML: {exc}")
        return errors

    for required_key in ("spec_version", "kind", "name"):
        if required_key not in content:
            errors.append(f"Required key '{required_key}' not found in {agent_file.name}")

    if "kind: native" not in content and "kind:" in content:
        logger.debug(
            "Agent kind is not 'native' — verify this is intentional in %s",
            agent_file.name,
        )

    return errors


# ---------------------------------------------------------------------------
# Core import logic
# ---------------------------------------------------------------------------

def _do_import(
    agent_file: Path,
    result: ImportResult,
    logger: logging.Logger,
    *,
    mock: bool = False,
) -> None:
    """Execute ``orchestrate agents import`` and update *result* in-place.

    Args:
        agent_file: Path to the agent YAML.
        result:     :class:`ImportResult` to populate with CLI output.
        logger:     Logger for progress and error messages.
        mock:       When True, simulate success without running the CLI.
    """
    if mock:
        logger.info("[MOCK] Simulating: orchestrate agents import -f %s", _rel(agent_file))
        result.cli_stdout = "[INFO] - Agent 'ibm_bob_assistant' imported successfully (MOCK)"
        result.cli_stderr = ""
        result.cli_exit_code = 0
        result.outcome = "mock"
        return

    logger.info("Running: orchestrate agents import -f %s", _rel(agent_file))

    try:
        proc = _run_orc(["agents", "import", "-f", str(agent_file)], logger)
    except subprocess.TimeoutExpired:
        result.outcome = "failed"
        result.error_message = (
            "CLI timed out after 120 seconds. The wxO platform may be unreachable. "
            "Check ORCHESTRATE_URL and network connectivity."
        )
        logger.error(result.error_message)
        return
    except FileNotFoundError:
        result.outcome = "failed"
        result.error_message = (
            f"orchestrate CLI binary not found at {ORC_BIN}. "
            "Activate the venv: source venv/bin/activate"
        )
        logger.error(result.error_message)
        return

    result.cli_stdout = proc.stdout or ""
    result.cli_stderr = proc.stderr or ""
    result.cli_exit_code = proc.returncode

    # Log CLI output at appropriate levels
    for line in result.cli_stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "[ERROR]" in stripped or "error" in stripped.lower():
            logger.error("  CLI: %s", stripped)
        elif "[WARNING]" in stripped or "warn" in stripped.lower():
            logger.warning("  CLI: %s", stripped)
        else:
            logger.info("  CLI: %s", stripped)

    if proc.returncode == 0:
        result.outcome = "success"
        logger.info("Agent '%s' imported successfully", AGENT_NAME)
    else:
        result.outcome = "failed"
        result.error_message = _interpret_cli_error(
            proc.returncode, proc.stdout, proc.stderr
        )
        logger.error("Import failed (exit %d): %s", proc.returncode, result.error_message)


def _interpret_cli_error(
    exit_code: int, stdout: str, stderr: str
) -> str:
    """Convert raw CLI failure output into a human-readable diagnosis.

    Analyses the combined stdout+stderr for known error patterns and returns
    a specific, actionable message.  Falls back to a generic message for
    unknown errors.

    Args:
        exit_code: CLI exit code.
        stdout:    CLI standard output.
        stderr:    CLI standard error.

    Returns:
        A single-line human-readable error description.
    """
    combined = (stdout + stderr).lower()

    if "token" in combined and ("expired" in combined or "missing" in combined):
        return (
            "Session token is expired or missing. "
            "Re-authenticate: orchestrate env activate <env> --api-key $IBM_CLOUD_API_KEY"
        )
    if "no active environment" in combined or "no environment" in combined:
        return (
            "No active wxO environment. "
            "Run: orchestrate env activate <env-name> --api-key $IBM_CLOUD_API_KEY"
        )
    if "not found" in combined and "file" in combined:
        return (
            "Agent YAML file not found by the CLI. "
            "Check the --agent-file path or run from the project root."
        )
    if "already exists" in combined or "conflict" in combined:
        return (
            "Agent already exists and the platform rejected the re-import. "
            "Try --force to force an overwrite, or delete first: "
            f"orchestrate agents delete -n {AGENT_NAME}"
        )
    if "permission" in combined or "unauthorized" in combined or "403" in combined:
        return (
            "Permission denied (403). Verify IBM_CLOUD_API_KEY has the required roles."
        )
    if "connection" in combined or "timeout" in combined or "unreachable" in combined:
        return (
            "Network error — cannot reach the wxO API. "
            "Check ORCHESTRATE_URL and your network connection."
        )

    # Generic fallback
    snippet = (stdout + stderr).strip()[:200]
    return f"CLI exited with code {exit_code}. Output: {snippet!r}"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _write_report(result: ImportResult, logger: logging.Logger) -> Path:
    """Persist *result* as a timestamped JSON file in ``output/``.

    Args:
        result: Completed :class:`ImportResult` to serialise.
        logger: Logger for the path message.

    Returns:
        Path to the written report file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"import_agent_report_{ts}.json"
    out_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    logger.info("Report written to %s", _rel(out_path))
    return out_path


def _print_summary(result: ImportResult) -> None:
    """Print a human-readable one-page summary to stdout.

    Args:
        result: Completed :class:`ImportResult`.
    """
    width = 66
    icons = {"success": "✓", "dry_run": "~", "mock": "~", "failed": "✗", "aborted": "✗"}
    icon = icons.get(result.outcome, "?")

    print("\n" + "━" * width)
    print(f"  IBM Bob Assistant — Agent Import Summary")
    print(f"  Run at      : {result.run_at}")
    print(f"  Environment : {result.environment}")
    print(f"  Agent file  : {result.agent_file}")
    print("━" * width)
    print(f"\n  {icon}  Outcome  : {result.outcome.upper()}")

    if result.agent_already_existed:
        reimport = "YES (confirmed)" if result.reimport_confirmed else "NO (skipped)"
        print(f"     Pre-existing : agent was already on platform")
        print(f"     Re-import    : {reimport}")

    if result.dry_run:
        print("     Dry-run mode — no platform changes were made")
    if result.mock:
        print("     Mock mode — CLI was not executed")
    if result.error_message:
        print(f"\n  ✗  Error: {result.error_message}")

    print(f"\n  Elapsed: {result.elapsed_seconds:.1f}s")

    if result.warnings:
        print("\n  Warnings:")
        for w in result.warnings:
            print(f"    ⚠  {w}")

    print("━" * width)

    if result.outcome == "success":
        print("\n  Test the agent:")
        print("    orchestrate chat ask --agent-name ibm_bob_assistant")
    elif result.outcome in ("dry_run", "mock"):
        print("\n  To execute for real, run without --dry-run / --mock.")

    print()


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run(
    *,
    agent_file: Path = DEFAULT_AGENT_YAML,
    env_file: Path = DEFAULT_ENV_FILE,
    dry_run: bool = False,
    force: bool = False,
    mock: bool = False,
    verbose: bool = False,
    no_log_file: bool = False,
    no_report: bool = False,
) -> ImportResult:
    """Execute the agent import pipeline and return a completed ImportResult.

    This is the primary entry-point for programmatic use.  ``main()`` calls
    this function with arguments parsed from ``sys.argv``.

    Pipeline:
      1. Load .env and inject missing credentials
      2. Validate agent YAML (exists, readable, required keys)
      3. Check CLI binary and active environment
      4. Detect if agent already exists on the platform
      5. Prompt for re-import confirmation (skipped when --force)
      6. Execute import (or simulate it in dry-run / mock mode)
      7. Write JSON report

    Args:
        agent_file:  Path to the agent YAML to import.
        env_file:    Path to the .env credentials file.
        dry_run:     Validate all prerequisites but make no platform changes.
        force:       Skip confirmation prompt when agent already exists.
        mock:        Simulate a successful import without calling the CLI.
        verbose:     Enable DEBUG-level logging.
        no_log_file: Skip the file log handler.
        no_report:   Skip writing the JSON report to output/.

    Returns:
        A fully populated :class:`ImportResult`.
    """
    logger = _configure_logging(verbose=verbose, no_log_file=no_log_file)
    run_start = time.monotonic()

    result = ImportResult(
        run_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        agent_file=_rel(agent_file),
        dry_run=dry_run,
        mock=mock,
    )

    # ── Step 1: Load credentials ──────────────────────────────────────────────
    logger.info("━━━ Step 1 — Loading credentials")
    env_vars = _load_env(env_file, logger)
    _apply_env(env_vars)

    missing_creds = _check_credentials(logger)
    if missing_creds:
        msg = (
            f"Missing required credentials: {', '.join(missing_creds)}. "
            f"Set them in {_rel(env_file)} or export them in your shell."
        )
        logger.error(msg)
        result.outcome = "failed"
        result.error_message = msg
        result.elapsed_seconds = time.monotonic() - run_start
        if not no_report:
            _write_report(result, logger)
        _print_summary(result)
        return result

    logger.info("Credentials OK")

    # ── Step 2: Validate agent YAML ───────────────────────────────────────────
    logger.info("━━━ Step 2 — Validating agent YAML: %s", _rel(agent_file))
    validation_errors = _validate_agent_yaml(agent_file, logger)
    if validation_errors:
        for err in validation_errors:
            logger.error("  ✗ %s", err)
        result.outcome = "failed"
        result.error_message = "; ".join(validation_errors)
        result.elapsed_seconds = time.monotonic() - run_start
        if not no_report:
            _write_report(result, logger)
        _print_summary(result)
        sys.exit(2)

    logger.info("  ✓ Agent YAML valid: %s", agent_file.name)

    # ── Step 3: Verify CLI ────────────────────────────────────────────────────
    logger.info("━━━ Step 3 — Verifying orchestrate CLI")
    if not mock:
        _check_cli(logger)

    result.environment = _get_active_environment(logger) if not mock else "mock"
    if result.environment == "<unknown>" and not mock:
        result.warnings.append(
            "No active wxO environment detected. "
            "Run: orchestrate env activate <name> --api-key $IBM_CLOUD_API_KEY"
        )
        logger.warning(result.warnings[-1])
    else:
        logger.info("  Active environment: %s", result.environment)

    # ── Step 4: Check if agent already exists ─────────────────────────────────
    logger.info("━━━ Step 4 — Checking platform for existing agent")
    if mock:
        result.agent_already_existed = False
        logger.info("  [MOCK] Skipping platform check")
    else:
        result.agent_already_existed = _agent_exists_on_platform(AGENT_NAME, logger)

    if result.agent_already_existed:
        logger.info("  Agent '%s' already exists on the platform", AGENT_NAME)
    else:
        logger.info("  Agent '%s' not found — will import fresh", AGENT_NAME)

    # ── Step 5: Confirm re-import (if needed) ─────────────────────────────────
    if result.agent_already_existed and not dry_run:
        if force:
            result.reimport_confirmed = True
            logger.info("  --force: skipping confirmation, proceeding with re-import")
        else:
            try:
                answer = input(
                    f"\n  Agent '{AGENT_NAME}' already exists. "
                    "Re-import now? [y/N] "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()  # clean newline after ^C
                result.outcome = "aborted"
                result.error_message = "User interrupted at re-import confirmation."
                result.elapsed_seconds = time.monotonic() - run_start
                if not no_report:
                    _write_report(result, logger)
                _print_summary(result)
                sys.exit(130)

            if answer in ("y", "yes"):
                result.reimport_confirmed = True
                logger.info("  User confirmed re-import")
            else:
                logger.info("  Re-import declined by user — nothing changed")
                result.outcome = "aborted"
                result.error_message = "Re-import declined by user."
                result.elapsed_seconds = time.monotonic() - run_start
                if not no_report:
                    _write_report(result, logger)
                _print_summary(result)
                sys.exit(0)  # user said no — not an error

    # ── Step 6: Import ────────────────────────────────────────────────────────
    logger.info("━━━ Step 6 — Importing agent")

    if dry_run:
        logger.info(
            "[DRY-RUN] Would run: orchestrate agents import -f %s",
            _rel(agent_file),
        )
        result.outcome = "dry_run"
    else:
        _do_import(agent_file, result, logger, mock=mock)

    # ── Step 7: Report ────────────────────────────────────────────────────────
    result.elapsed_seconds = time.monotonic() - run_start

    if not no_report:
        _write_report(result, logger)

    _print_summary(result)
    return result


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    """Construct and return the CLI argument parser.

    Returns:
        Configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="import_agent.py",
        description=(
            "Import the IBM Bob Assistant agent into the active "
            "watsonx Orchestrate environment."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-f", "--agent-file",
        metavar="FILE",
        type=Path,
        default=DEFAULT_AGENT_YAML,
        help=(
            f"Path to the agent YAML file to import "
            f"(default: {_rel(DEFAULT_AGENT_YAML)})"
        ),
    )
    parser.add_argument(
        "--env",
        metavar="FILE",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"Path to .env credentials file (default: {_rel(DEFAULT_ENV_FILE)})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate prerequisites and print the import command without executing it.",
    )
    parser.add_argument(
        "-F", "--force",
        action="store_true",
        default=False,
        help="Skip the re-import confirmation prompt when the agent already exists.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help=(
            "Simulate a successful import without executing the CLI. "
            "Useful for unit tests and CI dry-runs."
        ),
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=False,
        help="Enable DEBUG logging (shows every CLI command and its output).",
    )
    parser.add_argument(
        "--no-log-file",
        action="store_true",
        default=False,
        help="Suppress writing to logs/import_agent.log.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        default=False,
        help="Suppress writing the JSON report to output/.",
    )
    return parser


def main() -> None:
    """Parse CLI arguments, run the import pipeline, and exit.

    Exit codes:
        0    Success, dry-run, or user declined re-import.
        1    Runtime/execution error.
        2    Configuration/validation error.
        130  User interrupted (Ctrl+C).
    """
    parser = _build_arg_parser()
    args = parser.parse_args()

    try:
        result = run(
            agent_file=args.agent_file,
            env_file=args.env,
            dry_run=args.dry_run,
            force=args.force,
            mock=args.mock,
            verbose=args.verbose,
            no_log_file=args.no_log_file,
            no_report=args.no_report,
        )
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)

    if result.outcome in ("success", "dry_run", "mock", "aborted"):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
