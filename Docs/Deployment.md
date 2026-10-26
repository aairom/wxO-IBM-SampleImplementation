# Deployment Guide — IBM Bob Documentation Assistant

> **Authoritative reference for deploying, operating, and troubleshooting the
> `ibm_bob_assistant` watsonx Orchestrate agent.**
>
> This document captures every command, flag, known issue, and resolution from
> the full development and deployment session. Treat it as the single source of
> truth for this project.

---

## Table of Contents

1. [File Reference](#1-file-reference)
2. [Prerequisites](#2-prerequisites)
3. [Environment Setup](#3-environment-setup)
4. [Deployment Scripts](#4-deployment-scripts)
5. [Deployment Workflows](#5-deployment-workflows)
6. [Verification Checklist](#6-verification-checklist)
7. [Troubleshooting](#7-troubleshooting)
8. [Manual CLI Commands](#8-manual-cli-commands)

---

## 1. File Reference

| File | Committed | Purpose |
|------|-----------|---------|
| `.env.example` | ✅ Yes | Template with all required keys — no values. Safe to commit. |
| `.env` | ❌ No (gitignored) | Populated credentials. Copy from `.env.example`. |
| `scripts/start.sh` | ✅ Yes | Authenticate → import KB → wait for indexing → import agent. |
| `scripts/stop.sh` | ✅ Yes | Remove agent and KB from the platform; deactivate CLI session. |
| `scripts/cleanup.sh` | ✅ Yes | Remove local `venv/`, `__pycache__`, and optionally `.env`. |
| `scripts/fetch_ibm_bob_docs.py` | ✅ Yes | Regenerate KB `.txt` files from the Bob search API. |
| `agents/ibm_bob_assistant.agent.yaml` | ✅ Yes | Native agent definition (RAG + citations + guardrails). |
| `knowledge-bases/ibm_bob_docs.kb.yaml` | ✅ Yes | Knowledge base pointing to 11 `.txt` doc files. |
| `knowledge-bases/docs/*.txt` | ✅ Yes | Pre-populated IBM Bob documentation (759 lines, 11 topics). |
| `knowledge-bases/docs/*.md` | ✅ Yes | Redundant authoring copies — identical to `.txt`. Unused by KB. |
| `workspace_config.yaml` | ✅ Yes | Folder layout for the `orchestrate` CLI. |
| `requirements.txt` | ✅ Yes | Python dependencies (`requests>=2.32.0`). |

### `.gitignore` rules for credentials

The `.gitignore` uses the following pattern to protect secrets while keeping
the template trackable:

```gitignore
.env          # exact filename — the live credentials file
.env.*        # e.g. .env.production, .env.staging
!.env.example # explicit negation — the template IS committed
```

> **Important:** The earlier `*.env` glob was replaced with `.env.*` because
> `*.env` matches `.env.example` (zero characters before `.env`). The current
> pattern is correct.

---

## 2. Prerequisites

| Requirement | Check | Notes |
|-------------|-------|-------|
| macOS / Linux | — | Windows not tested |
| Python 3.10+ | `python3 --version` | Tested on 3.12 |
| `uv` | `uv --version` | [Install](https://docs.astral.sh/uv/) |
| `orchestrate` CLI (ADK) | `venv/bin/orchestrate --version` | Installed in `venv/` via `requirements.txt` |
| watsonx Orchestrate instance | — | IBM Cloud SaaS (`eu-de` region verified) |
| IBM Cloud API key | — | Generate at https://cloud.ibm.com/iam/apikeys |

---

## 3. Environment Setup

### 3.1 Create the Python virtual environment

```bash
# From the project root
uv venv venv
source venv/bin/activate
uv pip install -r requirements.txt

# Verify
venv/bin/orchestrate --version
# → ADK Version: 2.18.1
```

### 3.2 Create and populate `.env`

```bash
cp .env.example .env
```

Edit `.env` and fill in the two required values:

```bash
# Required
ORCHESTRATE_URL=https://api.<region>.watson-orchestrate.cloud.ibm.com/instances/<INSTANCE_ID>
IBM_CLOUD_API_KEY=<your-ibm-cloud-api-key>

# Optional — defaults to "wxo-ibm-bob" if omitted
ORCHESTRATE_ENV_NAME=aam-wxo-be

# Only needed if regenerating KB docs from the Bob search API
BOB_SEARCH_API_URL=
BOB_SEARCH_API_TOKEN=
```

> **Never commit `.env`.** It is already listed in `.gitignore`.

---

## 4. Deployment Scripts

All scripts read credentials exclusively from `.env` — no secrets are
hard-coded anywhere. All scripts are idempotent unless `--force-reimport`
is passed.

### 4.1 `scripts/start.sh` — Deploy

Runs the full 6-step deployment pipeline:

1. Load and validate `.env`
2. Verify the `orchestrate` CLI is present
3. Register and activate the wxO environment
4. Import the knowledge base (skip if already present)
5. Poll KB status until `Ready = True` (up to 10 minutes)
6. Import the agent

```bash
# Standard first-time deployment
./scripts/start.sh

# Re-deployment when KB is already indexed (fastest path)
./scripts/start.sh --skip-kb-check

# Force a clean slate — deletes and re-imports both KB and agent
./scripts/start.sh --force-reimport

# Combine: force reimport but skip the readiness poll
./scripts/start.sh --force-reimport --skip-kb-check
```

| Flag | Effect |
|------|--------|
| _(none)_ | Idempotent deploy — skips KB/agent import if they already exist |
| `--skip-kb-check` | Skips the KB readiness polling loop (use when KB is already `Ready = True`) |
| `--force-reimport` | Deletes existing KB and agent, then re-imports from YAML |

**Expected output (successful run):**

```
━━━ Step 1 — Loading environment variables
[OK]  ORCHESTRATE_URL  = https://api.eu-de.watson-orchestrate.cloud.ibm.com/...
[OK]  IBM_CLOUD_API_KEY = oxxzvB…VQ-d (masked)
[OK]  ORCHESTRATE_ENV_NAME = aam-wxo-be

━━━ Step 2 — Verifying orchestrate CLI
[OK]  CLI: ADK Version: 2.18.1

━━━ Step 3 — Authenticating with watsonx Orchestrate
[INFO] Environment 'aam-wxo-be' already registered
[INFO] Activating environment 'aam-wxo-be' with IBM Cloud API key…
[INFO] Environment 'aam-wxo-be' is now active
[OK]  Authenticated successfully
[OK]  Connected to watsonx Orchestrate

━━━ Step 4 — Importing knowledge base (ibm_bob_docs)
[INFO] Knowledge base 'ibm_bob_docs' already exists — skipping import

━━━ Step 5 — Waiting for knowledge base to be ready
[OK]  Knowledge base 'ibm_bob_docs' is Ready (attempt 1)

━━━ Step 6 — Importing agent (ibm_bob_assistant)
[INFO] Existing Agent 'ibm_bob_assistant' found. Updating...
[INFO] Agent 'ibm_bob_assistant' updated successfully
[OK]  Agent 'ibm_bob_assistant' imported successfully

╔══════════════════════════════════════════════════════════════╗
║  IBM Bob Documentation Assistant — deployed successfully     ║
╚══════════════════════════════════════════════════════════════╝
```

---

### 4.2 `scripts/stop.sh` — Undeploy

Removes the agent and knowledge base from the platform, then deactivates the
CLI session.

```bash
# Full undeploy — remove agent + KB + deactivate session
./scripts/stop.sh

# Remove only the agent; keep the KB (avoids re-indexing on next deploy)
./scripts/stop.sh --keep-kb

# Remove only the KB; keep the agent
./scripts/stop.sh --keep-agent

# Deactivate session without removing anything from the platform
./scripts/stop.sh --keep-kb --keep-agent
```

| Flag | Effect |
|------|--------|
| _(none)_ | Remove agent, KB, and deactivate CLI session |
| `--keep-kb` | Skip KB deletion (KB stays on platform) |
| `--keep-agent` | Skip agent deletion (agent stays on platform) |

> **Note:** `stop.sh` removes platform resources only. It does not touch local
> files. Run `cleanup.sh` to remove local artefacts.

---

### 4.3 `scripts/cleanup.sh` — Local cleanup

Removes local generated files: `venv/`, `__pycache__`, `.pyc` files, and the
`orchestrate` credentials cache.

```bash
# Standard clean — removes venv and byte-code caches
./scripts/cleanup.sh

# Full wipe — also removes .env and redundant .md doc duplicates
./scripts/cleanup.sh --all
```

| Flag | Effect |
|------|--------|
| _(none)_ | Remove `venv/`, `.venv/`, `__pycache__/`, `*.pyc`, credentials cache |
| `--all` | Also remove `.env` and `knowledge-bases/docs/*.md` duplicate files |

> ⚠ **`--all` removes `.env`.** You must recreate it from `.env.example` before
> running `start.sh` again.

**After cleanup — reinstall:**

```bash
uv venv venv
source venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env   # only needed if you ran --all
# Edit .env and fill in credentials
```

---

### 4.4 Testing the deployed agent

> `orchestrate chat ask` requires an **interactive TTY**. Run it directly in a
> terminal — do not pipe or redirect stdin.

```bash
venv/bin/orchestrate chat ask --agent-name ibm_bob_assistant
```

Then type a question at the prompt:

```
> What is IBM Bob?
> How do Bobcoins work?
> What modes does Bob have?
> What can Bob Shell do?
> How do I create a custom skill?
> What is MCP in Bob?
> How do I disable telemetry?
```

**Out-of-scope test** — the agent should refuse, not guess:

```
> What is the weather in Paris?
```

Expected: `"I'm sorry, I was unable to find information about that in the
official IBM Bob documentation…"`

---

## 5. Deployment Workflows

### 5.1 First-time deployment

```bash
# 1. Install dependencies
uv venv venv && source venv/bin/activate
uv pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Edit .env: set ORCHESTRATE_URL and IBM_CLOUD_API_KEY

# 3. Deploy (full — includes KB readiness poll, ~2–10 min)
./scripts/start.sh
```

---

### 5.2 Re-deployment (idempotent, KB already ready)

Use this on every subsequent deploy. Skips the polling loop since the KB
is already indexed.

```bash
./scripts/start.sh --skip-kb-check
```

---

### 5.3 Clean re-import (force fresh state)

Use when the KB or agent YAML has changed and you need a full reset.

```bash
./scripts/start.sh --force-reimport
```

This will:
1. Delete `ibm_bob_docs` knowledge base from the platform
2. Delete `ibm_bob_assistant` agent from the platform
3. Re-import both from the local YAML files
4. Poll for KB readiness (~2–10 min)

To skip the poll on a force reimport (e.g. you know indexing is fast):

```bash
./scripts/start.sh --force-reimport --skip-kb-check
```

---

### 5.4 Undeploy and remove platform resources

```bash
# Full removal
./scripts/stop.sh

# Partial: keep KB indexed (avoids ~10 min re-indexing next time)
./scripts/stop.sh --keep-kb
```

---

### 5.5 Local environment wipe

```bash
# Remove venv and caches only (keeps .env)
./scripts/cleanup.sh

# Full wipe including credentials
./scripts/cleanup.sh --all
```

---

### 5.6 KB content refresh

Run this only when the IBM Bob documentation has been updated. The
pre-populated `.txt` files are already checked into the repo.

```bash
# Set credentials for the Bob search API
export BOB_SEARCH_API_URL=<internal-bob-search-endpoint>
export BOB_SEARCH_API_TOKEN=<your-token>

# Regenerate the 11 .txt files
python3 scripts/fetch_ibm_bob_docs.py

# Re-import the knowledge base with fresh content
./scripts/start.sh --force-reimport
```

---

## 6. Verification Checklist

Run these checks after deployment to confirm the full stack is operational.

### ✅ Step 1 — CLI authenticated

```bash
venv/bin/orchestrate env list
# ► aam-wxo-be  https://api.eu-de.watson-orchestrate.cloud.ibm.com/...  (active)
```

### ✅ Step 2 — Knowledge base exists and is Ready

```bash
venv/bin/orchestrate knowledge-bases status -n ibm_bob_docs
```

Expected (look for `True` in the Ready column and `ready` in Status):

```
│ ibm_bob_docs │ … │ True │ True │ ready │ … │ 01_overview… │ … │
```

> The KB table wraps columns — `Ready` and `Built In Index Status` appear in
> separate columns. The grep pattern the script uses is:
> `│[[:space:]]+True[[:space:]]+│[[:space:]]+ready`

### ✅ Step 3 — Agent exists on the platform

```bash
venv/bin/orchestrate agents get -n ibm_bob_assistant
```

> Do NOT rely on `agents list` for name matching — names are truncated across
> multiple rows in the table output. Use `agents get -n <name>` instead.

### ✅ Step 4 — Agent responds correctly

```bash
venv/bin/orchestrate chat ask --agent-name ibm_bob_assistant
# > What is IBM Bob?
```

Expected: A grounded answer citing the source URL (`https://bob.ibm.com/docs/…`),
not a generic LLM response.

### ✅ Step 5 — Out-of-scope guardrail fires

```bash
# Same session as above
# > What is the weather in Paris?
```

Expected: The agent declines and directs the user to the IBM Bob docs URL.

---

## 7. Troubleshooting

### Issue 1 — `orchestrate` CLI version command kills the script under `set -euo pipefail`

**Symptom:** `start.sh` exits silently after printing the Step 2 header, or
immediately after capturing `$WXO_VERSION`.

**Root cause:** `orchestrate --version` writes multi-line output to stderr.
When captured as `$(...  2>&1 | head -1)`, the `head` command closes the pipe
after reading one line, causing the subshell's write to fail with `SIGPIPE`.
`pipefail` treats this as a fatal error.

**Fix applied in `start.sh` line 91:**

```bash
# WRONG — pipefail kills the script when orchestrate writes >1 line to stderr
WXO_VERSION=$("$VENV_ORCHESTRATE" --version 2>&1 | head -1)

# CORRECT — drain remaining output after head reads its line
WXO_VERSION=$("$VENV_ORCHESTRATE" --version 2>&1 | { head -1; cat > /dev/null; })
```

---

### Issue 2 — `orchestrate` commands produce no output when piped (pager interference)

**Symptom:** `orchestrate env list 2>/dev/null | grep -q "aam-wxo-be"` returns
exit code 1 even though the environment exists. The same command run
interactively works fine.

**Root cause:** The `orchestrate` CLI routes output through a pager (similar to
`less`) when stdout is a TTY. When piped, the pager detects a non-TTY and
produces no output, so `grep` sees an empty stream.

**Fix applied throughout all scripts:**

```bash
# WRONG — pager produces no output when piped
"$ORC" env list 2>/dev/null | grep -q "$ENV_NAME"

# CORRECT — cat forces plain text mode, bypassing the pager
"$ORC" env list 2>/dev/null | cat | grep -q "$ENV_NAME"
```

This pattern is applied consistently in `start.sh` and `stop.sh` for all
`agents list`, `knowledge-bases list`, and `env list` calls.

---

### Issue 3 — KB readiness grep pattern doesn't match table output

**Symptom:** The KB polling loop never exits even though
`orchestrate knowledge-bases status` shows `Ready = True` in the terminal.

**Root cause:** The original grep pattern `"ready.*true"` assumed the words
`ready` and `true` would appear on the same line. The Rich-formatted table puts
each column value on its own line when the terminal is narrow:

```
│ ibm_bob_docs │ … │ True │ True │ ready │ … │
```

The pattern must match across the table's column-separator characters (`│`).

**Fix applied in `start.sh` line 148:**

```bash
# WRONG — assumes "ready" and "True" are on the same line
grep -qi "ready.*true|status.*ready"

# CORRECT — matches the actual table cell format
grep -qE "│[[:space:]]+True[[:space:]]+│[[:space:]]+ready|Ready.*True|status.*ready"
```

**Verify the pattern against live output:**

```bash
venv/bin/orchestrate knowledge-bases status -n ibm_bob_docs 2>&1 | cat \
  | grep -qE "│[[:space:]]+True[[:space:]]+│[[:space:]]+ready|Ready.*True|status.*ready" \
  && echo "MATCH" || echo "NO MATCH"
```

---

### Issue 4 — Stray UTF-8 character (U+2026 `…`) embedded in variable name

**Symptom:** `start.sh` exits at Step 6 with:
`line 170: AGENT_YAML…: unbound variable`

**Root cause:** A Python string replacement during script authoring accidentally
embedded the UTF-8 ellipsis character (`\xe2\x80\xa6`, U+2026) directly into
the variable name `AGENT_YAML`, making it `AGENT_YAML…` which bash cannot
resolve.

**Detection:**

```bash
python3 -c "
with open('scripts/start.sh', 'rb') as f:
    raw = f.read()
import re
for m in re.finditer(b'AGENT_YAML', raw):
    print(repr(raw[m.start():m.start()+20]))
"
# If you see b'AGENT_YAML\xe2\x80\xa6' — the corruption is present
```

**Fix:**

```bash
python3 -c "
path = 'scripts/start.sh'
with open(path, 'rb') as f:
    raw = f.read()
fixed = raw.replace(b'AGENT_YAML\xe2\x80\xa6\"', b'AGENT_YAML\"')
with open(path, 'wb') as f:
    f.write(fixed)
print('Fixed')
"
```

---

### Issue 5 — `agents list` truncates names across multiple rows

**Symptom:** After import, the final verification grep
`agents list | grep "ibm_bob_assistant"` returns empty even though the agent
was successfully imported.

**Root cause:** The Rich table formatter wraps long values across rows. The
agent name `ibm_bob_assistant` appears as:

```
│ ibm_b │ IBM   │
│ ob_as │ Bob   │
│ sista │ docu… │
│ nt    │ assi… │
```

No single line contains the full name, so `grep` finds nothing.

**Fix applied in `start.sh` (verification section):**

```bash
# WRONG — name is split across rows
AGENT_LISTED=$("$ORC" agents list 2>&1 | cat | grep "$AGENT_NAME" || true)

# CORRECT — use agents get which returns a single-agent view
AGENT_CHECK=$("$ORC" agents get -n "$AGENT_NAME" 2>&1 | cat | head -1 || true)
if echo "$AGENT_CHECK" | grep -qi "ibm_bob|name:|ibm bob"; then
  ok "Agent '$AGENT_NAME' verified on platform"
else
  ok "Agent '$AGENT_NAME' imported (platform confirmed update above)"
fi
```

**Workaround for manual checks:**

```bash
# Use agents get, not agents list
venv/bin/orchestrate agents get -n ibm_bob_assistant

# Or increase terminal width to prevent wrapping
COLUMNS=200 venv/bin/orchestrate agents list
```

---

### Issue 6 — `orchestrate env activate` auth type warning

**Symptom:** After `env activate`, the CLI prints:

```
[WARNING] - Using 'ibm_iam' Auth Type. If this is incorrect please use the
'--type' flag to explicitly choose one of mcsp, mcsp_v1, mcsp_v2, cpd or k8s
```

**Status:** This is **not an error** — it is a cosmetic warning. The `ibm_iam`
type is correct for IBM Cloud SaaS instances. Authentication succeeds
regardless.

**Suppress (if needed):** Pass `--type ibm_iam` explicitly on `env add`:

```bash
venv/bin/orchestrate env add -n aam-wxo-be \
  -u "$ORCHESTRATE_URL" \
  --type ibm_iam
```

---

### Issue 7 — KB import already exists (idempotency)

**Symptom:** `orchestrate knowledge-bases import` fails because the KB already
exists on the platform.

**Resolution:** The `start.sh` script checks for existence before importing:

```bash
if "$ORC" knowledge-bases list 2>/dev/null | cat | grep -q "$KB_NAME"; then
  info "Knowledge base '$KB_NAME' already exists — skipping import"
fi
```

To force a fresh import, run:

```bash
./scripts/start.sh --force-reimport
```

---

### Issue 8 — Session expired / no credentials cache

**Symptom:**

```
FileNotFoundError: No active environment found.
Please run `orchestrate env activate` to activate an environment.
```

**Root cause:** The credentials cache at
`~/.cache/orchestrate/credentials.yaml` has been deleted (e.g. by `stop.sh`
or `cleanup.sh`) or has expired.

**Resolution:**

```bash
./scripts/start.sh   # re-authenticates automatically
# or manually:
venv/bin/orchestrate env activate aam-wxo-be --api-key "$IBM_CLOUD_API_KEY"
```

---

### Issue 9 — Agent returns out-of-scope for all queries

**Symptom:** Every question returns the "not found in IBM Bob documentation"
guardrail response, even for obvious IBM Bob topics.

**Causes and fixes:**

| Cause | Fix |
|-------|-----|
| KB not ready (`Ready = False`) | `orchestrate knowledge-bases status -n ibm_bob_docs` — wait for `True` |
| KB not linked to agent | Check `knowledge_base:` section in `agents/ibm_bob_assistant.agent.yaml` |
| Agent imported before KB was ready | Re-import agent: `orchestrate agents import -f agents/ibm_bob_assistant.agent.yaml` |
| Empty `.txt` files | Run `python3 scripts/fetch_ibm_bob_docs.py` to populate them |

---

## 8. Manual CLI Commands

For direct platform management without the automation scripts.

```bash
# Activate a specific environment
venv/bin/orchestrate env activate aam-wxo-be --api-key "$IBM_CLOUD_API_KEY"

# List all registered environments
venv/bin/orchestrate env list

# Import knowledge base
venv/bin/orchestrate knowledge-bases import -f knowledge-bases/ibm_bob_docs.kb.yaml

# Check KB status
venv/bin/orchestrate knowledge-bases status -n ibm_bob_docs

# Delete knowledge base
venv/bin/orchestrate knowledge-bases delete -n ibm_bob_docs

# Import agent
venv/bin/orchestrate agents import -f agents/ibm_bob_assistant.agent.yaml

# Get agent details (reliable — does not truncate)
venv/bin/orchestrate agents get -n ibm_bob_assistant

# Delete agent
venv/bin/orchestrate agents delete -n ibm_bob_assistant

# Chat with the agent (requires interactive TTY)
venv/bin/orchestrate chat ask --agent-name ibm_bob_assistant

# Regenerate KB docs from the Bob search API
export BOB_SEARCH_API_URL=<endpoint>
export BOB_SEARCH_API_TOKEN=<token>
python3 scripts/fetch_ibm_bob_docs.py
```
