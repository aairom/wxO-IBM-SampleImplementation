#!/usr/bin/env python3
"""
import_tools.py — Production-ready tool import and orchestration manager for the
IBM Bob Documentation Assistant on watsonx Orchestrate (wxO).

===============================================================================
PURPOSE
===============================================================================
This script is the single authoritative entry-point for registering Python tools
with a live wxO environment and verifying that the agent is wired to them
correctly.  It is called by scripts/start.sh (Step 5b) and can also be run
standalone for incremental updates or troubleshooting.

===============================================================================
WHAT IT DOES  (end-to-end pipeline, fully idempotent)
===============================================================================
  1.  Load .env and validate required credentials
  2.  Detect the active wxO environment via `orchestrate env list`
  3.  For every tool file in TOOL_FILES:
        a. Parse the file with the Python AST to discover @tool-decorated functions
        b. Check whether each named tool already exists on the platform
        c. Import the file if any tool is missing  (or --force-reimport is set)
        d. Re-verify that all expected tools are now present
  4.  Confirm the target agent YAML lists all expected tool names
  5.  Redeploy the agent YAML so the platform picks up any changes
  6.  Print a structured summary with timing and pass/fail status per tool
  7.  Write a machine-readable JSON report to output/tool_import_report_<ts>.json

===============================================================================
USAGE
===============================================================================
  # Normal (idempotent — only imports tools that are missing)
  python scripts/import_tools.py

  # Force re-import of all tools even if already present
  python scripts/import_tools.py --force-reimport

  # Dry-run: plan what would be imported, make no changes
  python scripts/import_tools.py --dry-run

  # Skip agent redeploy (tools only)
  python scripts/import_tools.py --skip-agent-deploy

  # Verbose logging (includes every CLI command and its output)
  python scripts/import_tools.py --verbose

  # Point to a non-default .env file
  python scripts/import_tools.py --env /path/to/.env

===============================================================================
DEPENDENCIES
===============================================================================
  Runtime:
    Python >= 3.10
    requests >= 2.32.0                  (already in requirements.txt)
    ibm-watsonx-orchestrate >= 2.18.1   (installed in venv/)

  The `orchestrate` CLI binary is expected at:
    <project_root>/venv/bin/orchestrate

===============================================================================
INTEGRATION WITH scripts/start.sh
===============================================================================
  start.sh Step 5b calls this script as:
    python scripts/import_tools.py [--force-reimport]

  Exit codes:
    0  All tools imported and verified successfully
    1  One or more tools failed to import or verify
    2  Configuration error (missing credentials, missing files, etc.)

===============================================================================
MAINTAINING AND UPDATING TOOL IMPORTS
===============================================================================
  Adding a new tool file:
    1.  Create the .py file in tools/  with @tool-decorated functions
    2.  Add an entry to TOOL_FILES at the bottom of this file
    3.  Update agents/ibm_bob_assistant.agent.yaml to list the new tool names
    4.  Run: python scripts/import_tools.py
    5.  Verify with: orchestrate tools list

  Updating an existing tool:
    1.  Edit the .py file in tools/
    2.  Run: python scripts/import_tools.py   (re-import is triggered automatically
        when the platform does not know the tool, or use --force-reimport)

  Removing a tool:
    1.  Remove the tool name from the agent YAML
    2.  Run: python scripts/import_tools.py --skip-agent-deploy
        then manually: orchestrate tools delete -n <tool_name>

===============================================================================
EXAMPLES — invoking the orchestrated tools after deployment
===============================================================================
  # Interactive chat via CLI (requires active wxO session)
  orchestrate chat ask --agent-name ibm_bob_assistant

  # Single query (non-interactive, for scripting)
  orchestrate chat ask --agent-name ibm_bob_assistant \
      --message "What are IBM Bob enterprise plan features?"

  # Direct tool invocation (bypasses agent reasoning, useful for debug)
  orchestrate tools run -n search_bob_documentation \
      --input '{"query": "Bob Shell slash commands"}'

  orchestrate tools run -n get_bob_doc_section \
      --input '{"section_name": "bob_shell"}'
"""

from __future__ import annotations

import argparse
import ast
import datetime
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


def _rel(path: Path, base: Path = None) -> str:
    """Return path relative to base if possible, otherwise return the full path.

    Using walk_up=True handles paths outside the project root (e.g. tmp dirs
    used during testing).  Falls back to the absolute path string on any error.

    Args:
        path: The path to make relative.
        base: The base directory (defaults to _PROJECT_ROOT).

    Returns:
        A relative path string, or the absolute path string as a fallback.
    """
    try:
        return str(path.relative_to(base or _PROJECT_ROOT, walk_up=True))
    except (ValueError, TypeError):
        return str(path)

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
# Use a named logger so callers can silence us without touching root logging.
log = logging.getLogger("import_tools")
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(
    logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%H:%M:%S")
)
log.addHandler(_handler)
log.setLevel(logging.INFO)  # elevated to DEBUG when --verbose is passed


# ---------------------------------------------------------------------------
# Project layout constants
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _SCRIPT_DIR.parent.resolve()

#: Default .env location (overridable via --env CLI flag)
DEFAULT_ENV_FILE = _PROJECT_ROOT / ".env"

#: Path to the orchestrate CLI inside the project venv
ORC_BIN = _PROJECT_ROOT / "venv" / "bin" / "orchestrate"

#: Default agent YAML to redeploy after tools are imported
AGENT_YAML = _PROJECT_ROOT / "agents" / "ibm_bob_assistant.agent.yaml"

#: Output directory for JSON reports
OUTPUT_DIR = _PROJECT_ROOT / "output"

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------
# Each entry maps a tool *file* to the tool *names* it exposes.
# When you add a new tool file, append an entry here.
#
# Format:
#   {
#       "file":  Path relative to _PROJECT_ROOT,
#       "tools": [list of @tool function names declared in that file],
#   }
#
TOOL_FILES: list[dict] = [
    {
        "file": Path("tools/live_bob_search.py"),
        "tools": ["search_bob_documentation", "get_bob_doc_section"],
    },
    # ── Add future tool files below ──────────────────────────────────────────
    # {
    #     "file":  Path("tools/kb_refresh.py"),
    #     "tools": ["refresh_knowledge_base"],
    # },
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ToolImportResult:
    """Outcome of importing a single tool file."""

    #: Relative path of the tool file that was processed
    file: str
    #: Tool names declared in the file
    expected_tools: list[str]
    #: Tool names that were already on the platform before this run
    already_present: list[str] = field(default_factory=list)
    #: Tool names that were freshly imported this run
    imported: list[str] = field(default_factory=list)
    #: Tool names that are confirmed present after this run
    verified: list[str] = field(default_factory=list)
    #: Tool names that could NOT be confirmed on the platform
    failed: list[str] = field(default_factory=list)
    #: Whether the import step was actually attempted (False in dry-run or skip)
    import_attempted: bool = False
    #: Wall-clock seconds spent on this file
    elapsed_seconds: float = 0.0
    #: Human-readable status
    status: str = "pending"


@dataclass
class OrchestrationReport:
    """Top-level report written to output/ as JSON."""

    run_at: str = ""
    environment: str = ""
    dry_run: bool = False
    agent_yaml: str = ""
    agent_redeployed: bool = False
    tool_results: list[ToolImportResult] = field(default_factory=list)
    overall_status: str = "pending"
    total_elapsed_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def load_env(env_file: Path) -> dict[str, str]:
    """Parse a .env file and return a {key: value} mapping.

    Lines starting with ``#`` and blank lines are ignored.  Inline comments
    (``KEY=value  # comment``) are NOT stripped — values are taken verbatim
    after the first ``=`` to avoid breaking URLs that contain ``#``.

    Args:
        env_file: Path to the .env file to load.

    Returns:
        A dict of all key=value pairs found in the file.

    Raises:
        SystemExit(2): If the file does not exist.
    """
    if not env_file.exists():
        log.error(
            ".env file not found at %s — copy .env.example and fill in values", env_file
        )
        sys.exit(2)

    env: dict[str, str] = {}
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes (single or double) if present
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            env[key] = value

    log.debug("Loaded %d variables from %s", len(env), env_file)
    return env


def apply_env(env: dict[str, str]) -> None:
    """Merge env dict into os.environ (does not overwrite existing values).

    Args:
        env: Dict of environment variables to set.
    """
    for key, value in env.items():
        os.environ.setdefault(key, value)


def validate_required_vars(required: list[str]) -> None:
    """Assert that every variable in *required* is set and non-empty.

    Args:
        required: List of environment variable names that must be present.

    Raises:
        SystemExit(2): If any required variable is missing or empty.
    """
    missing = [v for v in required if not os.environ.get(v, "").strip()]
    if missing:
        log.error(
            "The following required environment variables are missing or empty: %s",
            ", ".join(missing),
        )
        log.error("Set them in .env (see .env.example for reference).")
        sys.exit(2)


# ---------------------------------------------------------------------------
# CLI wrapper
# ---------------------------------------------------------------------------

def run_orc(
    args: list[str],
    *,
    capture: bool = True,
    check: bool = False,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """Run the ``orchestrate`` CLI with the given arguments.

    Always pipes stdout + stderr through ``cat`` to prevent the CLI pager from
    blocking when stdout is a TTY (a known ADK behaviour — see project notes).

    Args:
        args:    Argument list appended after the binary, e.g. ["tools", "list"].
        capture: When True, capture stdout+stderr and return them as strings.
        check:   When True, raise CalledProcessError on non-zero exit.
        timeout: Maximum seconds to wait for the process.

    Returns:
        A ``subprocess.CompletedProcess`` with ``.stdout`` and ``.returncode``.
    """
    cmd = [str(ORC_BIN)] + args
    log.debug("CMD: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
        check=check,
    )

    if capture:
        log.debug("STDOUT: %s", result.stdout[:500] if result.stdout else "<empty>")
        if result.stderr:
            log.debug("STDERR: %s", result.stderr[:300])

    return result


def check_cli_available() -> str:
    """Verify the orchestrate CLI binary exists and return its version string.

    Returns:
        Version string from ``orchestrate --version`` (first line only).

    Raises:
        SystemExit(2): If the binary is not executable.
    """
    if not ORC_BIN.is_file() or not os.access(ORC_BIN, os.X_OK):
        log.error(
            "orchestrate CLI not found at %s\n"
            "Run:  source venv/bin/activate && pip install ibm-watsonx-orchestrate",
            ORC_BIN,
        )
        sys.exit(2)

    result = run_orc(["--version"])
    # --version writes to stderr in some ADK versions
    version_text = (result.stdout or result.stderr or "").strip().splitlines()
    version = version_text[0] if version_text else "unknown"
    log.info("orchestrate CLI: %s", version)
    return version


def get_active_environment() -> str:
    """Return the name of the currently active wxO environment.

    Parses ``orchestrate env list`` output to find the ``(active)`` line.

    Returns:
        The active environment name, or ``"<unknown>"`` if not determinable.
    """
    result = run_orc(["env", "list"])
    for line in (result.stdout or "").splitlines():
        if "(active)" in line:
            # Line format: " name   https://...  (active)"
            return line.strip().split()[0]
    return "<unknown>"


# ---------------------------------------------------------------------------
# AST-based tool discovery
# ---------------------------------------------------------------------------

def discover_tools_in_file(tool_file: Path) -> list[str]:
    """Parse a Python source file and return names of @tool-decorated functions.

    Uses the Python AST — no module import, no side effects.  This means it
    works even when ``ibm-watsonx-orchestrate`` is not installed locally.

    Args:
        tool_file: Path to the Python source file to analyse.

    Returns:
        Ordered list of function names decorated with ``@tool(...)``.

    Raises:
        SystemExit(2): If the file cannot be parsed (syntax error).
    """
    if not tool_file.exists():
        log.warning("Tool file not found: %s — skipping AST discovery", tool_file)
        return []

    source = tool_file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(tool_file))
    except SyntaxError as exc:
        log.error("Syntax error in %s: %s", tool_file, exc)
        sys.exit(2)

    tool_names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            # Accept both @tool and @tool(...)
            is_tool = (
                isinstance(decorator, ast.Name) and decorator.id == "tool"
            ) or (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Name)
                and decorator.func.id == "tool"
            )
            if is_tool:
                tool_names.append(node.name)
                break

    log.debug("AST discovered %d tool(s) in %s: %s", len(tool_names), tool_file.name, tool_names)
    return tool_names


# ---------------------------------------------------------------------------
# Platform tool checks
# ---------------------------------------------------------------------------

def list_platform_tools() -> list[str]:
    """Return the names of all tools currently registered on the platform.

    Parses ``orchestrate tools list`` table output.  Each row contains the
    tool name in the first ``│``-delimited column.

    Returns:
        List of tool name strings (stripped, no delimiters).
    """
    result = run_orc(["tools", "list"])
    names: list[str] = []
    for line in (result.stdout or "").splitlines():
        # Table rows look like:  │ tool_name  │ description │ ...
        if "│" not in line:
            continue
        parts = [p.strip() for p in line.split("│") if p.strip()]
        if parts and parts[0] not in ("Name", "─", "━", "="):
            names.append(parts[0])
    log.debug("Platform tools: %s", names)
    return names


def tool_exists_on_platform(tool_name: str, platform_tools: list[str]) -> bool:
    """Check whether *tool_name* appears in the cached platform tool list.

    Args:
        tool_name:      The exact tool name to look for.
        platform_tools: List returned by :func:`list_platform_tools`.

    Returns:
        True if the tool is present, False otherwise.
    """
    # ADK table truncates long names — do a prefix match as well as exact
    return any(
        t == tool_name or tool_name.startswith(t[:20])
        for t in platform_tools
    )


# ---------------------------------------------------------------------------
# Import logic
# ---------------------------------------------------------------------------

def import_tool_file(tool_file: Path, *, dry_run: bool = False) -> bool:
    """Import a Python tool file into the active wxO environment.

    Runs ``orchestrate tools import -k python -f <file>``.

    Args:
        tool_file: Absolute path to the .py file to import.
        dry_run:   When True, log the command but do not execute it.

    Returns:
        True if the import succeeded (or was skipped for dry-run), False on error.
    """
    if dry_run:
        log.info("[DRY-RUN] Would import: orchestrate tools import -k python -f %s", tool_file)
        return True

    log.info("Importing tool file: %s", _rel(tool_file))
    result = run_orc(["tools", "import", "-k", "python", "-f", str(tool_file)])

    if result.returncode != 0:
        log.error(
            "Import failed (exit %d).\nSTDOUT: %s\nSTDERR: %s",
            result.returncode,
            result.stdout,
            result.stderr,
        )
        return False

    # Log each "Tool 'X' imported successfully" line from the output
    for line in (result.stdout or "").splitlines():
        if "imported" in line.lower() or "updated" in line.lower():
            log.info("  ✓ %s", line.strip())

    return True


# ---------------------------------------------------------------------------
# Agent redeploy
# ---------------------------------------------------------------------------

def validate_agent_yaml_tools(
    agent_yaml: Path, expected_tool_names: list[str]
) -> list[str]:
    """Check the agent YAML for any expected tool names that are missing.

    Reads the YAML as plain text and checks for each tool name as a string
    occurrence — avoids a PyYAML dependency.

    Args:
        agent_yaml:          Path to the agent .yaml file.
        expected_tool_names: All tool names that should be listed in the YAML.

    Returns:
        List of tool names that are NOT found in the YAML (empty means all OK).
    """
    if not agent_yaml.exists():
        log.warning("Agent YAML not found at %s — cannot validate tool references", agent_yaml)
        return []

    content = agent_yaml.read_text(encoding="utf-8")
    missing = [name for name in expected_tool_names if name not in content]
    return missing


def redeploy_agent(agent_yaml: Path, *, dry_run: bool = False) -> bool:
    """Re-import the agent YAML to pick up any changes (tools, KB, instructions).

    Runs ``orchestrate agents import -f <yaml>``.  The CLI handles both
    create-new and update-existing idempotently.

    Args:
        agent_yaml: Path to the agent .yaml definition file.
        dry_run:    When True, log the command but do not execute it.

    Returns:
        True on success, False on failure.
    """
    if dry_run:
        log.info("[DRY-RUN] Would redeploy agent: orchestrate agents import -f %s", agent_yaml)
        return True

    log.info("Redeploying agent from %s …", _rel(agent_yaml))
    result = run_orc(["agents", "import", "-f", str(agent_yaml)])

    if result.returncode != 0:
        log.error(
            "Agent redeploy failed (exit %d).\nSTDOUT: %s\nSTDERR: %s",
            result.returncode,
            result.stdout,
            result.stderr,
        )
        return False

    for line in (result.stdout or "").splitlines():
        if any(kw in line.lower() for kw in ("imported", "updated", "success")):
            log.info("  ✓ %s", line.strip())

    return True


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def write_json_report(report: OrchestrationReport) -> Path:
    """Serialise *report* to a timestamped JSON file in output/.

    Args:
        report: The completed :class:`OrchestrationReport` to persist.

    Returns:
        The Path where the report was written.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"tool_import_report_{ts}.json"

    # Convert dataclasses to plain dicts for json serialisation
    payload = asdict(report)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Report written to %s", _rel(out_path))
    return out_path


def print_summary(report: OrchestrationReport) -> None:
    """Print a formatted summary table to stdout.

    Args:
        report: Completed :class:`OrchestrationReport`.
    """
    width = 70
    print("\n" + "━" * width)
    print(f"  IBM Bob Tool Import Summary")
    print(f"  Environment : {report.environment}")
    print(f"  Run at      : {report.run_at}")
    print(f"  Dry-run     : {'YES' if report.dry_run else 'no'}")
    print("━" * width)

    for tr in report.tool_results:
        icon = "✓" if tr.status == "ok" else ("~" if report.dry_run else "✗")
        print(f"\n  {icon}  {tr.file}  ({tr.elapsed_seconds:.1f}s)")
        for t in tr.expected_tools:
            if t in tr.failed:
                state = "FAILED"
            elif t in tr.imported:
                state = "imported"
            elif t in tr.already_present:
                state = "already present"
            else:
                state = "unknown"
            symbol = "✓" if state != "FAILED" else "✗"
            print(f"       {symbol}  {t:<40}  {state}")

    print("\n" + "━" * width)
    print(f"  Agent redeployed : {'YES' if report.agent_redeployed else 'no'}")
    print(f"  Overall status   : {report.overall_status.upper()}")
    print(f"  Total time       : {report.total_elapsed_seconds:.1f}s")
    if report.warnings:
        print("\n  Warnings:")
        for w in report.warnings:
            print(f"    ⚠  {w}")
    print("━" * width + "\n")


# ---------------------------------------------------------------------------
# Main orchestration pipeline
# ---------------------------------------------------------------------------

def run(
    *,
    env_file: Path = DEFAULT_ENV_FILE,
    force_reimport: bool = False,
    dry_run: bool = False,
    skip_agent_deploy: bool = False,
    verbose: bool = False,
) -> OrchestrationReport:
    """Execute the full tool import and orchestration pipeline.

    This is the primary entry-point for programmatic use.  The CLI ``main()``
    wrapper calls this function with arguments parsed from sys.argv.

    Args:
        env_file:           Path to the .env file to load credentials from.
        force_reimport:     Re-import all tool files even when already present.
        dry_run:            Plan and log everything but make no platform changes.
        skip_agent_deploy:  Skip the agent YAML redeploy step.
        verbose:            Enable DEBUG-level logging.

    Returns:
        A completed :class:`OrchestrationReport` describing every step.
    """
    if verbose:
        log.setLevel(logging.DEBUG)

    run_start = time.monotonic()
    report = OrchestrationReport(
        run_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        dry_run=dry_run,
        agent_yaml=_rel(AGENT_YAML),
    )

    # ── Step 1: Load credentials ──────────────────────────────────────────────
    log.info("━━━ Step 1 — Loading environment variables")
    env_vars = load_env(env_file)
    apply_env(env_vars)
    validate_required_vars(["ORCHESTRATE_URL", "IBM_CLOUD_API_KEY"])
    log.info("Credentials loaded from %s", _rel(env_file))

    # ── Step 2: Verify CLI and active environment ─────────────────────────────
    log.info("━━━ Step 2 — Verifying orchestrate CLI")
    check_cli_available()

    report.environment = get_active_environment()
    if report.environment == "<unknown>":
        report.warnings.append(
            "Could not determine active wxO environment. "
            "Run: orchestrate env activate <name> --api-key $IBM_CLOUD_API_KEY"
        )
        log.warning(report.warnings[-1])
    else:
        log.info("Active environment: %s", report.environment)

    # ── Step 3: Import each tool file ─────────────────────────────────────────
    log.info("━━━ Step 3 — Importing tool files")

    # Fetch the current platform tool list once (avoids repeated CLI calls)
    platform_tools = list_platform_tools() if not dry_run else []

    all_expected: list[str] = []

    for entry in TOOL_FILES:
        file_start = time.monotonic()
        tool_file = _PROJECT_ROOT / entry["file"]
        declared_tools: list[str] = entry["tools"]

        # Use AST discovery to cross-check the registry declaration
        discovered = discover_tools_in_file(tool_file)
        if set(discovered) != set(declared_tools):
            diff = set(discovered) ^ set(declared_tools)
            report.warnings.append(
                f"{entry['file']}: registry declares {declared_tools!r} but AST "
                f"found {discovered!r}. Mismatch: {sorted(diff)!r}. "
                f"Update TOOL_FILES in {Path(__file__).name}."
            )
            log.warning(report.warnings[-1])

        tr = ToolImportResult(
            file=str(entry["file"]),
            expected_tools=declared_tools,
        )

        # ── 3a. Check which tools are already on the platform ─────────────────
        for tool_name in declared_tools:
            all_expected.append(tool_name)
            if tool_exists_on_platform(tool_name, platform_tools):
                tr.already_present.append(tool_name)
                log.info("  ✓ %-40s already present", tool_name)

        tools_missing = [t for t in declared_tools if t not in tr.already_present]

        # ── 3b. Import if any tool is missing (or forced) ─────────────────────
        needs_import = bool(tools_missing) or force_reimport
        if needs_import:
            if force_reimport:
                log.info("  --force-reimport: re-importing %s", tool_file.name)
            else:
                log.info(
                    "  Missing tools %s — importing %s",
                    tools_missing,
                    tool_file.name,
                )

            tr.import_attempted = True
            success = import_tool_file(tool_file, dry_run=dry_run)

            if not success:
                tr.failed = declared_tools
                tr.status = "failed"
                report.tool_results.append(tr)
                tr.elapsed_seconds = time.monotonic() - file_start
                continue

            # Refresh platform tool list after import
            if not dry_run:
                platform_tools = list_platform_tools()

        # ── 3c. Verify all expected tools are now on the platform ─────────────
        for tool_name in declared_tools:
            if dry_run or tool_exists_on_platform(tool_name, platform_tools):
                tr.verified.append(tool_name)
                if tool_name not in tr.already_present:
                    tr.imported.append(tool_name)
                    log.info("  ✓ %-40s imported and verified", tool_name)
            else:
                tr.failed.append(tool_name)
                log.error("  ✗ %-40s NOT found on platform after import", tool_name)

        tr.status = "ok" if not tr.failed else "failed"
        tr.elapsed_seconds = time.monotonic() - file_start
        report.tool_results.append(tr)

    # ── Step 4: Validate agent YAML references all tools ─────────────────────
    log.info("━━━ Step 4 — Validating agent YAML tool references")
    missing_in_yaml = validate_agent_yaml_tools(AGENT_YAML, all_expected)
    if missing_in_yaml:
        report.warnings.append(
            f"The following tools are NOT listed in {AGENT_YAML.name}: "
            f"{missing_in_yaml!r}. Add them under the 'tools:' key."
        )
        log.warning(report.warnings[-1])
    else:
        log.info("  ✓ All expected tools are referenced in %s", AGENT_YAML.name)

    # ── Step 5: Redeploy agent ────────────────────────────────────────────────
    if skip_agent_deploy:
        log.info("━━━ Step 5 — Skipping agent redeploy (--skip-agent-deploy)")
    else:
        log.info("━━━ Step 5 — Redeploying agent")
        report.agent_redeployed = redeploy_agent(AGENT_YAML, dry_run=dry_run)
        if not report.agent_redeployed:
            report.warnings.append(
                f"Agent redeploy failed. Re-run manually: "
                f"orchestrate agents import -f {AGENT_YAML.name}"
            )

    # ── Final status ──────────────────────────────────────────────────────────
    all_failed = any(tr.status == "failed" for tr in report.tool_results)
    report.overall_status = "failed" if all_failed else "ok"
    report.total_elapsed_seconds = time.monotonic() - run_start

    return report


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser.

    Returns:
        Configured :class:`argparse.ArgumentParser` instance.
    """
    parser = argparse.ArgumentParser(
        prog="import_tools.py",
        description=(
            "Import and orchestrate watsonx Orchestrate tools for the "
            "IBM Bob Documentation Assistant."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--force-reimport",
        action="store_true",
        default=False,
        help="Re-import all tool files even when already present on the platform.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Plan what would be imported but make no changes to the platform.",
    )
    parser.add_argument(
        "--skip-agent-deploy",
        action="store_true",
        default=False,
        help="Skip the agent YAML redeploy after importing tools.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable DEBUG logging (includes every CLI command and its output).",
    )
    parser.add_argument(
        "--env",
        metavar="FILE",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"Path to .env file (default: {DEFAULT_ENV_FILE.relative_to(_PROJECT_ROOT)})",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        default=False,
        help="Do not write the JSON report to output/.",
    )
    return parser


def main() -> None:
    """Parse CLI arguments, run the pipeline, print summary, and exit.

    Exit codes:
        0  All tools imported and verified.
        1  One or more tool imports failed.
        2  Configuration error (missing files, missing credentials, etc.).
    """
    parser = _build_arg_parser()
    args = parser.parse_args()

    report = run(
        env_file=args.env,
        force_reimport=args.force_reimport,
        dry_run=args.dry_run,
        skip_agent_deploy=args.skip_agent_deploy,
        verbose=args.verbose,
    )

    print_summary(report)

    if not args.no_report:
        write_json_report(report)

    sys.exit(0 if report.overall_status == "ok" else 1)


if __name__ == "__main__":
    main()
