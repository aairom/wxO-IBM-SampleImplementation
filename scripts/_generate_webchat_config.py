#!/usr/bin/env python3
"""
_generate_webchat_config.py

Python helper called by get_webchat_embed.sh.

Runs `orchestrate channels webchat embed` via subprocess (with stdin=DEVNULL
so it never hangs on a TTY prompt), parses the returned snippet, and writes
the real values into web/webchat-config.js by substituting %%PLACEHOLDER%%
tokens in web/webchat-config.js.template.

Usage (called by get_webchat_embed.sh):
    python3 scripts/_generate_webchat_config.py \\
        --project-root /path/to/wxO-IBM \\
        --agent-name ibm_bob_assistant \\
        --env live

Exit codes:
    0  success
    1  embed command failed or could not parse required values
    2  template file not found
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CYAN  = "\033[0;36m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED   = "\033[0;31m"
RESET = "\033[0m"

def info(msg: str)    -> None: print(f"{CYAN}[INFO]{RESET}  {msg}")
def ok(msg: str)      -> None: print(f"{GREEN}[OK]{RESET}    {msg}")
def warn(msg: str)    -> None: print(f"{YELLOW}[WARN]{RESET}  {msg}")
def error(msg: str)   -> None: print(f"{RED}[ERROR]{RESET} {msg}", file=sys.stderr)


def extract_value(key: str, text: str) -> str:
    """
    Extract a JSON string value from the ADK CLI embed snippet.

    The CLI produces two wrapping patterns:

    Pattern A — key/value on separate lines:
        orchestrationID: \\n
    "e65910fa61ce9072d64902d03f3d4774_75c2cabb-..."

    Pattern B — value split mid-string across two lines (e.g. crn):
        crn: \\n
    "crn:v1:bluemix:public:...:a/e65910fa61ce9072d64902d03f3d4\\n
    774:75c2cabb-..."

    Strategy:
      1. Normalise the raw text so every "key": "value" pair is on one line:
         a. Remove newlines that appear AFTER a colon (key/value split).
         b. Remove newlines that appear INSIDE a quoted string (value split).
      2. Match with a standard single-line regex.
    """
    # (a) Join lines where the key ends with ': \n' and value starts on next line.
    # Matches:  ': \n"'  →  ': "'
    normalised = re.sub(r':\s*\n\s*"', ': "', text)

    # (b) Join lines where a quoted value is split mid-string.
    # The split produces a line ending WITHOUT a closing quote, then the next
    # line continues the value.  We detect this by: non-" char at EOL, then
    # next line starts with non-" non-space content before the closing quote.
    # Apply twice to handle back-to-back splits.
    for _ in range(3):
        normalised = re.sub(r'([^"\n])\n([^"\n{}\[\]])', r'\1\2', normalised)

    # (c) Collapse remaining whitespace for safety
    collapsed = re.sub(r"\s+", " ", normalised)

    # (d) Extract  key : "value"  — the CLI uses bare (unquoted) key names,
    # e.g.  orchestrationID: "..."  not  "orchestrationID": "..."
    m = re.search(rf'{re.escape(key)}\s*:\s*"([^"]+)"', collapsed)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_orc(cmd: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    """Run an orchestrate CLI command with stdin closed (no pager/prompt hang)."""
    return subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=timeout, stdin=subprocess.DEVNULL,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate webchat-config.js from live platform")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--agent-name",   required=True)
    parser.add_argument("--env",          default="live")
    parser.add_argument("--api-key",      default="",
                        help="IBM Cloud API key (falls back to IBM_CLOUD_API_KEY env var)")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    template_path = project_root / "web" / "webchat-config.js.template"
    output_path   = project_root / "web" / "webchat-config.js"

    # ------------------------------------------------------------------
    # 1. Check template exists
    # ------------------------------------------------------------------
    if not template_path.exists():
        error(f"Template not found: {template_path}")
        return 2

    # ------------------------------------------------------------------
    # 1b. Read .env values: API key, env name, and ORCHESTRATE_URL (instanceUrl).
    #     Reading directly from .env avoids bash subshell export failures.
    # ------------------------------------------------------------------
    api_key      = args.api_key or os.environ.get("IBM_CLOUD_API_KEY", "") or os.environ.get("ORCHESTRATE_API_KEY", "")
    env_name     = os.environ.get("ORCHESTRATE_ENV_NAME", "aam-wxo-be")
    instance_url = os.environ.get("ORCHESTRATE_URL", "")

    dotenv_path = project_root / ".env"
    if dotenv_path.exists():
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k in ("IBM_CLOUD_API_KEY", "ORCHESTRATE_API_KEY") and not api_key:
                api_key = v
            elif k == "ORCHESTRATE_ENV_NAME" and (not env_name or env_name == "aam-wxo-be"):
                env_name = v
            elif k == "ORCHESTRATE_URL" and not instance_url:
                instance_url = v

    if api_key:
        info(f"Re-activating wxO environment '{env_name}' before embed call...")
        activate = subprocess.run(
            ["orchestrate", "env", "activate", env_name],
            input=api_key + "\n",
            capture_output=True, text=True, timeout=30,
        )
        if "is now active" in activate.stdout or "is now active" in activate.stderr:
            ok(f"Environment '{env_name}' activated")
        else:
            warn("env activate output did not confirm success — proceeding anyway")

    # ------------------------------------------------------------------
    # 2. Run orchestrate channels webchat embed
    # ------------------------------------------------------------------
    info(f"Running: orchestrate channels webchat embed --agent-name {args.agent_name} --env {args.env}")

    try:
        result = run_orc([
            "orchestrate", "channels", "webchat", "embed",
            "--agent-name", args.agent_name,
            "--env", args.env,
        ], timeout=30)
    except subprocess.TimeoutExpired:
        error("orchestrate channels webchat embed timed out after 30s")
        return 1
    except FileNotFoundError:
        error("'orchestrate' binary not found — is the venv activated?")
        return 1

    if result.returncode != 0 or not result.stdout.strip():
        if result.returncode != 0:
            error(f"orchestrate channels webchat embed exited {result.returncode}")
            if result.stderr:
                error(result.stderr.strip())
        else:
            warn("orchestrate channels webchat embed returned empty output — retrying once...")
            # Retry once: token may not have been flushed to disk after activate
            import time
            time.sleep(2)
            result = subprocess.run(
                ["orchestrate", "channels", "webchat", "embed",
                 "--agent-name", args.agent_name, "--env", args.env],
                capture_output=True, text=True, timeout=30,
                stdin=subprocess.DEVNULL,
            )
        if not result.stdout.strip():
            warn("Still empty. Falling back to placeholder values.")
            raw = ""
        else:
            raw = result.stdout
    else:
        raw = result.stdout

    # ------------------------------------------------------------------
    # 3. Parse values from CLI output
    # ------------------------------------------------------------------
    if raw:
        orchestration_id  = extract_value("orchestrationID",    raw)
        host_url          = extract_value("hostURL",             raw)
        crn               = extract_value("crn",                 raw)
        agent_id          = extract_value("agentId",             raw)
        agent_env_id      = extract_value("agentEnvironmentId",  raw)
    else:
        orchestration_id = host_url = crn = agent_id = agent_env_id = ""

    # Default missing values to named placeholders
    orchestration_id = orchestration_id or "PLACEHOLDER_ORCHESTRATION_ID"
    crn              = crn              or "PLACEHOLDER_CRN"
    agent_id         = agent_id         or "PLACEHOLDER_AGENT_ID"
    agent_env_id     = agent_env_id     or "PLACEHOLDER_AGENT_ENV_ID"

    # hostURL: the ADK CLI always emits the portal URL — keep it.
    # api.eu-de.* returns HTTP 400 for wxoLoader.js; portal URL returns HTTP 200.
    PORTAL_URL = "https://eu-de.watson-orchestrate.cloud.ibm.com"
    if not host_url or "api.eu-de." in host_url:
        host_url = PORTAL_URL

    # instanceUrl: the API backend for auth + chat — MUST be set or the widget
    # falls back to deriving the backend from hostURL (portal) → Authentication Error.
    # Read from ORCHESTRATE_URL in .env; format is:
    #   https://api.<region>.watson-orchestrate.cloud.ibm.com/instances/<instanceId>
    instance_url = instance_url or "PLACEHOLDER_INSTANCE_URL"

    info(f"  orchestrationID    = {orchestration_id}")
    info(f"  hostURL            = {host_url}")
    info(f"  instanceUrl        = {instance_url}")
    info(f"  crn                = {crn[:40]}…" if len(crn) > 40 else f"  crn                = {crn}")
    info(f"  agentId            = {agent_id}")
    info(f"  agentEnvironmentId = {agent_env_id}")

    # ------------------------------------------------------------------
    # 4. Inject values into the template
    # ------------------------------------------------------------------
    output_path.parent.mkdir(parents=True, exist_ok=True)
    template_text = template_path.read_text(encoding="utf-8")

    filled = (
        template_text
        .replace("%%ORCHESTRATION_ID%%", orchestration_id)
        .replace("%%HOST_URL%%",         host_url)
        .replace("%%INSTANCE_URL%%",     instance_url)
        .replace("%%CRN%%",              crn)
        .replace("%%AGENT_ID%%",         agent_id)
        .replace("%%AGENT_ENV_ID%%",     agent_env_id)
    )

    output_path.write_text(filled, encoding="utf-8")
    ok(f"webchat-config.js written → {output_path.relative_to(project_root)}")

    # Warn if any placeholders remain
    if "PLACEHOLDER_" in filled:
        warn("Some values are still placeholders.")
        warn("See Docs/WebChat_Integration_Guide.md §3 for manual steps.")
        return 0  # non-fatal — page will load with placeholders visible

    ok("All values populated — ready to serve web/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
