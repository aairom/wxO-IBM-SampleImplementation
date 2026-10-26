# IBM Bob Assistant — Integration & Operations Guide

**Agent:** `ibm_bob_assistant`  
**Region:** eu-de (`https://eu-de.watson-orchestrate.cloud.ibm.com`)  
**ADK version:** ibm-watsonx-orchestrate ≥ 2.18.1  
**Status at time of writing:** Deployed (Live) ✅

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Prerequisites & Environment Setup](#2-prerequisites--environment-setup)
3. [Inspecting the Agent Configuration](#3-inspecting-the-agent-configuration)
4. [Publishing the Agent (Draft → Live)](#4-publishing-the-agent-draft--live)
5. [Accessing the Agent](#5-accessing-the-agent)
6. [Embedding into watsonx Assistant](#6-embedding-into-watsonx-assistant)
7. [End-to-End Testing](#7-end-to-end-testing)
8. [Troubleshooting](#8-troubleshooting)
9. [CLI Quick Reference](#9-cli-quick-reference)

---

## 1. System Architecture

### 1.1 Component map

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    watsonx Orchestrate  (eu-de region)                   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │              ibm_bob_assistant  (native agent)                  │    │
│  │                                                                  │    │
│  │  LLM:   groq/openai/gpt-oss-120b                                │    │
│  │  Style: react_core   Memory: enabled   Reasoning: hidden        │    │
│  │                                                                  │    │
│  │  ┌──────────────┐   ┌──────────────────────────────────────┐   │    │
│  │  │  System      │   │  Knowledge Base: ibm_bob_docs         │   │    │
│  │  │  Prompt      │   │  (Milvus vector index, eu-de)         │   │    │
│  │  │  (grounded   │   │                                        │   │    │
│  │  │   RAG rules) │   │  11 indexed .txt files:               │   │    │
│  │  └──────────────┘   │  01_overview       07_security        │   │    │
│  │                      │  02_bob_shell      08_telemetry       │   │    │
│  │  Tools (Coded):      │  03_enterprise     09_modes           │   │    │
│  │  ┌────────────────┐  │  04_premium_pkg    10_bobcoins        │   │    │
│  │  │search_bob_docs │  │  05_skills         11_bobalytics      │   │    │
│  │  │ (semantic API) │  │  06_mcp                               │   │    │
│  │  └────────────────┘  └──────────────────────────────────────┘   │    │
│  │  ┌────────────────┐                                              │    │
│  │  │get_bob_section │                                              │    │
│  │  │ (file reader)  │                                              │    │
│  │  └────────────────┘                                              │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                  watsonx LLM Backend                             │   │
│  │  groq/openai/gpt-oss-120b  —  react_core inference engine       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
         ▲                              ▲
         │ chat / REST API              │ SSRF-guarded POST
         │                              │
  ┌──────┴──────┐                ┌──────┴──────────────────┐
  │  End user   │                │  Bob Search API          │
  │  (UI / CLI  │                │  internal.bob.ibm.com    │
  │  / wxa)     │                │  (credential-protected)  │
  └─────────────┘                └──────────────────────────┘
```

### 1.2 Data flow for a user query

```
User question
    │
    ▼
ibm_bob_assistant receives message
    │
    ├─► react_core reasoning loop starts
    │       │
    │       ├─► tool call: search_bob_documentation(query)
    │       │       └─► POST to Bob Search API → returns passages + source URLs
    │       │
    │       └─► tool call: get_bob_doc_section(section_name)   [if needed]
    │               └─► reads local .txt file from knowledge-bases/docs/
    │
    ├─► Milvus vector search on ibm_bob_docs KB
    │       └─► returns semantically similar documentation chunks
    │
    └─► LLM synthesises answer from retrieved content
            └─► response with source citation → User
```

### 1.3 Component inventory

| Component | Kind | State | Notes |
|---|---|---|---|
| `ibm_bob_assistant` | Native agent | **Live** | react_core, memory enabled |
| `ibm_bob_docs` | Knowledge Base | **Ready** (Milvus) | 11 docs, `Ready = True` |
| `search_bob_documentation` | Coded tool | Deployed | READ_ONLY, semantic API |
| `get_bob_doc_section` | Coded tool | Deployed | READ_ONLY, file reader |
| `groq/openai/gpt-oss-120b` | LLM | Platform-managed | react_core style |

---

## 2. Prerequisites & Environment Setup

### 2.1 Local toolchain requirements

| Requirement | Version | Check command |
|---|---|---|
| Python | 3.10+ | `python3 --version` |
| uv | any | `uv --version` |
| ibm-watsonx-orchestrate | ≥ 2.18.1 | `orchestrate --version 2>&1 \| head -1` |
| git | any | `git --version` |

### 2.2 Project setup (first time)

```bash
# Clone and enter project
git clone <repo-url> wxO-IBM
cd wxO-IBM

# Create and activate virtual environment
uv venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows

# Install dependencies (includes ibm-watsonx-orchestrate)
uv pip install -r requirements.txt

# Verify ADK CLI
orchestrate --version 2>&1 | head -1
# Expected output: ibm-watsonx-orchestrate, version X.Y.Z
```

### 2.3 Credentials — `.env` file

Copy the template and fill in all five values:

```bash
cp .env.example .env
```

Required keys in `.env`:

```bash
ORCHESTRATE_URL=https://api.eu-de.watson-orchestrate.cloud.ibm.com
ORCHESTRATE_INSTANCE_ID=<your-instance-id>
ORCHESTRATE_IAM_URL=https://iam.cloud.ibm.com
ORCHESTRATE_API_KEY=<your-ibm-cloud-api-key>
ORCHESTRATE_TOKEN=<short-lived-iam-bearer-token>
```

> ⚠️ `ORCHESTRATE_TOKEN` expires in ~60 minutes. Refresh it with:
> ```bash
> ibmcloud login --apikey $ORCHESTRATE_API_KEY
> ibmcloud iam oauth-tokens
> # Copy the "IAM token" value (without "Bearer ") into ORCHESTRATE_TOKEN
> ```

### 2.4 Register and activate the wxO environment

```bash
source venv/bin/activate

# Register the eu-de environment (one-time)
orchestrate env add \
  --name aam-wxo-be \
  --url https://api.eu-de.watson-orchestrate.cloud.ibm.com \
  --auth-token $ORCHESTRATE_TOKEN

# Activate it
orchestrate env activate aam-wxo-be

# Verify
orchestrate env list | cat
# Expected:  aam-wxo-be  https://api.eu-de...  (active)
```

### 2.5 Validation checkpoint ✅

```bash
orchestrate agents list | cat | grep ibm_bob
# Expected: row containing "ibm_bob_assistant"

orchestrate knowledge-bases status -n ibm_bob_docs | cat | grep -E "Ready|ready"
# Expected: True  ready
```

---

## 3. Inspecting the Agent Configuration

### 3.1 List all agents

```bash
orchestrate agents list | cat
```

Expected output (truncated for readability):

```
┃ Name        ┃ LLM                    ┃ Style    ┃ Tools                              ┃ Knowledge Base ┃
│ ibm_bob_... │ groq/openai/gpt-oss-.. │ react_.. │ search_bob_doc.. / get_bob_doc_... │ ibm_bob_docs   │
│ AskOrche... │ groq/openai/gpt-oss-.. │ react_.. │                                    │                │
```

### 3.2 Inspect the agent YAML directly

The full agent definition lives at:

```
agents/ibm_bob_assistant.agent.yaml
```

Key sections explained:

```yaml
spec_version: v1           # ADK schema version
kind: native               # native = managed wxO agent (not external/assistant)
name: ibm_bob_assistant    # unique identifier on the platform
llm: groq/openai/gpt-oss-120b  # LLM routing string
style: react_core          # ReAct reasoning loop (plan → act → observe → answer)
hide_reasoning: true       # hides chain-of-thought from end users
memory_enabled: true       # maintains context across turns in a session

description: >             # shown in the agent picker / catalogue
  IBM Bob documentation assistant ...

instructions: |            # system prompt injected at every conversation start
  You are the IBM Bob Documentation Assistant ...

knowledge_base:
  - ibm_bob_docs           # vector KB attached — queried automatically by react_core

tools:
  - search_bob_documentation   # semantic search via Bob API
  - get_bob_doc_section        # full section retrieval from local .txt files

restrictions: editable     # allows UI editing after import
```

### 3.3 Inspect the Knowledge Base

```bash
# List all KBs
orchestrate knowledge-bases list | cat

# Status of ibm_bob_docs
orchestrate knowledge-bases status -n ibm_bob_docs | cat
```

Expected `status` output key fields:

| Field | Expected value | Meaning |
|---|---|---|
| `Ready` | `True` | KB is fully indexed and queryable |
| `Built In Index Status` | `ready` | Milvus index is built |
| `Documents (11)` | all 11 filenames | All docs indexed |

### 3.4 Inspect the tools

```bash
orchestrate tools list | cat | grep bob
# Expected:
# search_bob_documentation   Coded   ...
# get_bob_doc_section        Coded   ...
```

Tool source file: [`tools/live_bob_search.py`](../tools/live_bob_search.py)

| Tool | Permission | Input | Output |
|---|---|---|---|
| `search_bob_documentation` | READ_ONLY | `query: str` | Formatted passages + source URLs |
| `get_bob_doc_section` | READ_ONLY | `section_name: str` | Full section text (≤ 4,000 chars) |

Valid `section_name` values: `overview`, `bob_shell`, `enterprise`,
`premium_packages`, `skills`, `mcp`, `security`, `telemetry`, `modes`,
`bobcoins`, `bobalytics`.

---

## 4. Publishing the Agent (Draft → Live)

Agents imported via `orchestrate agents import` land in **Draft** state. They
must be **deployed** to become **Live** (visible with a green badge in the UI
and available to end users).

### 4.1 Deploy command

```bash
source venv/bin/activate
orchestrate agents deploy -n ibm_bob_assistant
```

Expected output:

```
[INFO] - Successfully deployed agent ibm_bob_assistant
```

### 4.2 Verify deployment

**CLI:**

```bash
# The agents list does not currently expose a status column,
# but a successful deploy + no error = Live state.
orchestrate agents list | cat | grep ibm_bob
```

**Web UI:**

1. Open `https://eu-de.watson-orchestrate.cloud.ibm.com`
2. Navigate to **Build agents and tools** → **All agents**
3. Confirm `ibm_bob_assistant` shows a green **Live** badge

### 4.3 Undeploy (revert to Draft)

```bash
orchestrate agents undeploy -n ibm_bob_assistant
# Reverts to Draft; agent still exists but is no longer Live
```

### 4.4 Re-import after YAML changes

If you edit `agents/ibm_bob_assistant.agent.yaml`:

```bash
# Re-import (replaces the existing Draft definition)
python scripts/import_agent.py --force

# Re-deploy to make changes Live
orchestrate agents deploy -n ibm_bob_assistant
```

Or use the full pipeline script (KB + tools + agent + deploy):

```bash
bash scripts/start.sh
```

---

## 5. Accessing the Agent

### 5.1 Web UI chat (recommended)

1. Open: `https://eu-de.watson-orchestrate.cloud.ibm.com`
2. Click **Ask in chat** (top-right of the agent catalogue), or
3. Open the main chat interface → click the **agent selector** icon →
   choose **`ibm_bob_assistant`**
4. Type your question. Example: `What is IBM Bob?`

### 5.2 CLI chat

```bash
source venv/bin/activate
orchestrate chat ask --agent-name ibm_bob_assistant
```

> ⚠️ Requires a real interactive TTY. Do not pipe `stdin`.

### 5.3 REST API (programmatic access)

The wxO platform exposes a chat completions endpoint compatible with the
OpenAI chat format:

```bash
BASE=https://api.eu-de.watson-orchestrate.cloud.ibm.com

curl -X POST "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $ORCHESTRATE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ibm_bob_assistant",
    "messages": [
      {"role": "user", "content": "What is IBM Bob?"}
    ]
  }'
```

---

## 6. Embedding into watsonx Assistant

This section covers how to surface `ibm_bob_assistant` from inside a
**watsonx Assistant** instance so end users interact through the Assistant
chat widget.

### 6.1 Architecture when embedded

```
End user (browser / Teams / Slack)
    │
    ▼
watsonx Assistant  (wxa instance)
    │
    └─► Calls ibm_bob_assistant via wxO Agent Skill
              │
              ▼
         ibm_bob_assistant  (wxO native agent)
              │  ├─ KB search (ibm_bob_docs)
              └─ Tool calls (search_bob_documentation, get_bob_doc_section)
```

### 6.2 Prerequisites for embedding

- A provisioned **watsonx Assistant** instance (IBM Cloud, same region)
- The `ibm_bob_assistant` agent must be **Live** (§4.1 above)
- Your IBM Cloud account needs **Manager** or **Editor** role on both the
  wxO instance and the wxa instance

### 6.3 Step-by-step embedding via the wxO UI

**Step 1 — Open the wxO UI**

```
https://eu-de.watson-orchestrate.cloud.ibm.com
```

**Step 2 — Navigate to the agent**

1. Click **Build agents and tools**
2. Click **ibm_bob_assistant** → opens the agent detail panel
3. Confirm the green **Live** badge is visible

**Step 3 — Open Agent Connections**

1. In the agent detail panel, click the **⋮** (three-dot menu) on the
   `ibm_bob_assistant` card
2. Select **Connect to Assistant** (or **Integrations** depending on UI version)

**Step 4 — Select the target watsonx Assistant instance**

1. Choose your IBM Cloud region: **eu-de**
2. Select your **watsonx Assistant** instance from the dropdown
3. Select the **Assistant** (a single wxa instance can have multiple assistants)
4. Click **Connect**

**Step 5 — Verify in watsonx Assistant**

1. Open your watsonx Assistant instance:
   `https://eu-de.assistant.watson.cloud.ibm.com`
2. Open the target Assistant → **Actions** tab
3. The `ibm_bob_assistant` should appear as an available **Agent Skill**
4. Add it to an action or set it as the default handler for unrecognised intents

### 6.4 Credential binding

The `ibm_bob_assistant` tools read credentials from environment variables
(`BOB_SEARCH_API_URL`, `BOB_SEARCH_API_TOKEN`). On the platform these are
injected via a **wxO Connection**:

```bash
# Check if the bob_search_api connection exists
orchestrate connections list | cat | grep bob_search

# If it does not exist, create it:
orchestrate connections create \
  --name bob_search_api \
  --type api_key_auth \
  --key BOB_SEARCH_API_TOKEN \
  --value "<your-token>"
```

Then bind it to the tool file at import time by adding `expected_credentials`
in the `@tool` decorator (already present in `tools/live_bob_search.py`).

---

## 7. End-to-End Testing

### 7.1 Validation test matrix

Run these queries in order to exercise every component:

| # | Query | What it exercises | Expected behaviour |
|---|---|---|---|
| 1 | `What is IBM Bob?` | KB vector search + LLM synthesis | Overview answer with source citation |
| 2 | `What slash commands does Bob Shell support?` | `search_bob_documentation` tool | List of `/` commands from `02_bob_shell.txt` |
| 3 | `Give me the full enterprise documentation` | `get_bob_doc_section("enterprise")` | Up to 4,000 chars from `03_enterprise.txt` |
| 4 | `How do Bobcoins work?` | KB + tool | Budget tiers, monthly reset explanation |
| 5 | `How do I create a custom skill?` | KB + tool | SKILL.md format, folder structure |
| 6 | `What is the weather in Paris?` | Out-of-scope guard | Polite refusal citing docs URL |
| 7 | `Tell me more` (follow-up to #1) | Memory / session continuity | Coherent follow-up without re-stating context |

### 7.2 CLI test session

```bash
source venv/bin/activate
orchestrate chat ask --agent-name ibm_bob_assistant
```

Then type each query from the table above and verify the expected behaviour.

### 7.3 Automated unit tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
# Expected: 141 passed
```

Test coverage:
- `tests/test_live_bob_search.py` — 31 tests (tool logic)
- `tests/test_import_tools.py` — 56 tests (import pipeline)
- `tests/test_import_agent.py` — 54 tests (agent import script)

---

## 8. Troubleshooting

### 8.1 Agent not appearing in `agents list`

| Symptom | Cause | Fix |
|---|---|---|
| Agent missing from list | Wrong active environment | `orchestrate env activate aam-wxo-be` |
| Agent missing after import | Import failed silently | Check `output/import_agent_report_*.json` |
| Permission error during list | Expired token | Refresh `ORCHESTRATE_TOKEN` (see §2.3) |

```bash
# Check which environment is active
orchestrate env list | cat | grep active

# Re-run import with verbose output
python scripts/import_agent.py --verbose
```

### 8.2 Failed deployment (agent stays in Draft)

```bash
orchestrate agents deploy -n ibm_bob_assistant 2>&1
```

| Error message | Cause | Fix |
|---|---|---|
| `Authentication token expired` | Stale `ORCHESTRATE_TOKEN` | Refresh token (§2.3) |
| `No active environment` | No env activated | `orchestrate env activate aam-wxo-be` |
| `agent not found` | Agent not imported | `python scripts/import_agent.py` first |
| `Permission denied` | Insufficient IAM role | Request Agent Editor role on the instance |

### 8.3 Knowledge base retrieval failures

```bash
# Check KB status
orchestrate knowledge-bases status -n ibm_bob_docs | cat
```

| `Ready` field | `Index Status` | Action |
|---|---|---|
| `True` | `ready` | ✅ KB is healthy |
| `False` | `indexing` | Wait 2–5 minutes and re-check |
| `False` | `failed` | Re-import: `orchestrate knowledge-bases import -f knowledge-bases/ibm_bob_docs.kb.yaml` |
| `False` | `pending` | KB import never completed — re-run import |

If the KB is healthy but retrieval still fails in chat, confirm the agent YAML
still lists `ibm_bob_docs`:

```bash
grep knowledge_base agents/ibm_bob_assistant.agent.yaml
# Expected:  - ibm_bob_docs
```

### 8.4 Tool execution errors

**Symptom:** Agent says it cannot find Bob documentation even though KB is healthy.

The `search_bob_documentation` tool calls an external API
(`BOB_SEARCH_API_URL`). If credentials are absent, it silently returns an
empty list and falls back to the KB. To confirm tool health:

```bash
source venv/bin/activate
python3 - <<'EOF'
import os, sys
sys.path.insert(0, "tools")
os.environ["BOB_SEARCH_API_URL"] = os.getenv("BOB_SEARCH_API_URL", "")
os.environ["BOB_SEARCH_API_TOKEN"] = os.getenv("BOB_SEARCH_API_TOKEN", "")
# stub the ADK import
import types
m = types.ModuleType("ibm_watsonx_orchestrate.agent_builder.tools")
m.tool = lambda **kw: (lambda f: f)
m.ToolPermission = type("TP", (), {"READ_ONLY": "read_only"})()
import sys
sys.modules["ibm_watsonx_orchestrate"] = types.ModuleType("ibm_watsonx_orchestrate")
sys.modules["ibm_watsonx_orchestrate.agent_builder"] = types.ModuleType("ibm_watsonx_orchestrate.agent_builder")
sys.modules["ibm_watsonx_orchestrate.agent_builder.tools"] = m
import importlib
lbs = importlib.import_module("live_bob_search")
print(lbs.get_bob_doc_section("overview")[:200])
EOF
```

Expected: first 200 characters of `01_overview.txt`.

**Symptom:** `Unknown section` error.

The agent passed an invalid `section_name`. Valid values are exactly:
`overview`, `bob_shell`, `enterprise`, `premium_packages`, `skills`, `mcp`,
`security`, `telemetry`, `modes`, `bobcoins`, `bobalytics`.

### 8.5 Memory not persisting across turns

Confirm `memory_enabled: true` is in the YAML and re-import if it was
changed:

```bash
grep memory_enabled agents/ibm_bob_assistant.agent.yaml
# Expected: memory_enabled: true

python scripts/import_agent.py --force
orchestrate agents deploy -n ibm_bob_assistant
```

### 8.6 Agent not visible in watsonx Assistant

1. Confirm the agent is **Live** (§4.1) — Draft agents cannot be connected to wxa
2. Confirm both the wxO and wxa instances are in **the same IBM Cloud region** (eu-de)
3. Confirm your IAM account has **Manager** role on both instances
4. Re-try the Connect flow from §6.3

---

## 9. CLI Quick Reference

### Agent commands

```bash
# List all agents
orchestrate agents list | cat

# Import agent from YAML (creates or replaces)
orchestrate agents import -f agents/ibm_bob_assistant.agent.yaml

# Deploy (Draft → Live)
orchestrate agents deploy -n ibm_bob_assistant

# Undeploy (Live → Draft)
orchestrate agents undeploy -n ibm_bob_assistant

# Remove agent entirely
orchestrate agents remove -n ibm_bob_assistant

# Export agent definition
orchestrate agents export -n ibm_bob_assistant -o agents/export/

# Chat with agent (requires TTY)
orchestrate chat ask --agent-name ibm_bob_assistant
```

### Knowledge base commands

```bash
# List all KBs
orchestrate knowledge-bases list | cat

# Import KB
orchestrate knowledge-bases import -f knowledge-bases/ibm_bob_docs.kb.yaml

# Status (Ready, index state, document list)
orchestrate knowledge-bases status -n ibm_bob_docs | cat

# Remove KB
orchestrate knowledge-bases remove -n ibm_bob_docs
```

### Tool commands

```bash
# List all tools
orchestrate tools list | cat

# Import Python tools
orchestrate tools import -k python -f tools/live_bob_search.py

# Remove a tool
orchestrate tools remove -n search_bob_documentation
orchestrate tools remove -n get_bob_doc_section
```

### Environment commands

```bash
# List environments (shows active)
orchestrate env list | cat

# Activate an environment
orchestrate env activate aam-wxo-be

# Add a new environment
orchestrate env add --name <name> --url <url> --auth-token <token>
```

### Project automation scripts

```bash
# Full deploy pipeline (KB + tools + agent + deploy)
bash scripts/start.sh

# Undeploy everything
bash scripts/stop.sh

# Import agent only (with validation + JSON report)
python scripts/import_agent.py

# Force re-import without prompt
python scripts/import_agent.py --force

# Dry-run validation only
python scripts/import_agent.py --dry-run

# Run all unit tests
python -m pytest tests/ -v    # Expected: 141 passed
```

### API endpoints (eu-de region)

| Service | Base URL |
|---|---|
| wxO Web UI | `https://eu-de.watson-orchestrate.cloud.ibm.com` |
| wxO REST API | `https://api.eu-de.watson-orchestrate.cloud.ibm.com` |
| Chat completions | `https://api.eu-de.watson-orchestrate.cloud.ibm.com/v1/chat/completions` |
| IAM token refresh | `https://iam.cloud.ibm.com/identity/token` |
| watsonx Assistant UI | `https://eu-de.assistant.watson.cloud.ibm.com` |
