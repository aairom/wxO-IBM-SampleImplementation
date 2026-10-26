# Knowledge Source Diagnostic — IBM Bob Documentation Assistant

> **Purpose:** Definitively answer "where does the agent's knowledge come from?",
> document the current configuration with evidence, and explain how to verify or
> change the knowledge source.

---

## Table of Contents

1. [Executive Answer](#1-executive-answer)
2. [Current Knowledge Source Status](#2-current-knowledge-source-status)
3. [Architecture: How the Knowledge Pipeline Works](#3-architecture-how-the-knowledge-pipeline-works)
4. [Knowledge Base Configuration Details](#4-knowledge-base-configuration-details)
5. [Verification Instructions](#5-verification-instructions)
6. [Switching Knowledge Sources](#6-switching-knowledge-sources)
7. [Troubleshooting Knowledge Source Issues](#7-troubleshooting-knowledge-source-issues)

---

## 1. Executive Answer

> **The agent's knowledge comes from real IBM Bob documentation content.**

The content is sourced from `https://bob.ibm.com/docs/` — it is not fabricated,
not from generic AI training data, and not from sample placeholder files. The
text was extracted from the live IBM Bob documentation site using the
`search_ibm_docs` MCP tool (Bob's internal documentation search API) and stored
as local `.txt` files that watsonx Orchestrate indexes into a Milvus vector
store.

**The full chain:**

```
IBM Bob documentation site (bob.ibm.com/docs)
    ↓  [extracted via Bob MCP search_ibm_docs API]
knowledge-bases/docs/*.txt  (11 local text files, 32 KB total)
    ↓  [imported via orchestrate knowledge-bases import]
ibm_bob_docs knowledge base  (Milvus vector index on wxO platform)
    ↓  [retrieved at query time via RAG]
ibm_bob_assistant agent  (answers grounded in retrieved passages)
    ↓
User
```

There is **no direct live crawl** of bob.ibm.com at query time. The pipeline
is "extract once, index once, query from index." The docs site is the upstream
origin; the local `.txt` files are the indexed copy.

---

## 2. Current Knowledge Source Status

### 2.1 What is indexed

| File | Source URL | Size | Lines |
|------|-----------|------|-------|
| `docs/01_overview.txt` | `https://bob.ibm.com/docs/` | 3,278 B | 67 |
| `docs/02_bob_shell.txt` | `https://bob.ibm.com/docs/shell/` | 4,126 B | 84 |
| `docs/03_enterprise.txt` | `https://bob.ibm.com/docs/ide/enterprise/` | 3,210 B | 72 |
| `docs/04_premium_packages.txt` | `https://bob.ibm.com/docs/ide/premium-packages/` | 1,558 B | 43 |
| `docs/05_skills.txt` | `https://bob.ibm.com/docs/ide/features/skills` | 3,164 B | 97 |
| `docs/06_mcp.txt` | `https://bob.ibm.com/docs/ide/configuration/mcp/` | 3,329 B | 67 |
| `docs/07_security.txt` | `https://bob.ibm.com/docs/ide/security/bob-security-guidance` | 3,008 B | 65 |
| `docs/08_telemetry.txt` | `https://bob.ibm.com/docs/ide/configuration/telemetry-data` | 2,333 B | 69 |
| `docs/09_modes.txt` | `https://bob.ibm.com/docs/ide/features/modes` | 3,266 B | 77 |
| `docs/10_bobcoins.txt` | `https://bob.ibm.com/docs/ide/account/bobcoins` | 3,144 B | 61 |
| `docs/11_bobalytics.txt` | `https://bob.ibm.com/docs/ide/features/bobalytics` | 2,326 B | 57 |
| **Total** | | **32,742 B** | **759** |

### 2.2 Evidence from the files themselves

Every `.txt` file opens with an explicit source attribution on line 3:

```
# IBM Bob — Overview and General FAQ

Source: https://bob.ibm.com/docs/
```

```
# IBM Bob MCP — Model Context Protocol

Source: https://bob.ibm.com/docs/ide/configuration/mcp/
```

The text that follows is verbatim IBM Bob documentation content: product names,
URLs such as `https://bob.ibm.com/docs/ide/getting-started/install`, and
feature-specific terminology (`Bobcoins`, `Bobalytics`, `SKILL.md`,
`bob.ibm.com`) that could only have come from the real documentation.

### 2.3 What the files are NOT

| Misconception | Reality |
|---|---|
| Placeholder / lorem ipsum sample files | ❌ No — real IBM Bob documentation text |
| Synthetically generated content | ❌ No — extracted from the live docs site |
| Generic AI training data | ❌ No — specific, versioned IBM product documentation |
| Direct live web scrape at query time | ❌ No — pre-extracted and stored locally |
| Auto-fetched from bob.ibm.com on each agent call | ❌ No — indexed into Milvus once at import time |

### 2.4 When the content was captured

The `.txt` files carry a filesystem creation timestamp of **2026-10-14** (the
project creation date). The content reflects the IBM Bob documentation as it
existed on that date. There is no auto-sync with the live website.

---

## 3. Architecture: How the Knowledge Pipeline Works

### 3.1 Component diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         IBM Bob Docs Site                           │
│                    https://bob.ibm.com/docs/                        │
│                (JavaScript SPA — not directly crawlable)            │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                  Bob MCP search_ibm_docs API
                  (internal IBM search endpoint)
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              scripts/fetch_ibm_bob_docs.py                          │
│  • Sends 28 search queries across 11 topics                         │
│  • Deduplicates chunks by chunk ID                                  │
│  • Writes one .txt file per topic                                   │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              knowledge-bases/docs/*.txt  (11 files)                 │
│              Local static copies of the documentation               │
│              Committed to the Git repository                        │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
              orchestrate knowledge-bases import
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│   ibm_bob_docs knowledge base  (on watsonx Orchestrate platform)    │
│   • Milvus vector index                                             │
│   • Text chunked and embedded on import                             │
│   • query_source: Agent  (agent formulates retrieval queries)       │
│   • generation.enabled: false  (raw passages returned to agent)     │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
           Vector similarity search at query time
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│   ibm_bob_assistant agent                                           │
│   • Receives top-k retrieved passages as context                    │
│   • LLM generates a grounded answer                                 │
│   • Adds source citation from passage metadata                      │
│   • Refuses if no relevant passages are found                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Key design decisions that affect knowledge sourcing

#### `query_source: Agent`
The agent itself formulates the KB query (rather than passing the raw user
message). This improves retrieval precision — the agent can rephrase a
conversational question into a more documentation-friendly search query.

```yaml
# knowledge-bases/ibm_bob_docs.kb.yaml
conversational_search_tool:
  query_source: Agent    # ← agent formulates the retrieval query
  generation:
    enabled: false       # ← KB returns raw passages; agent generates the answer
```

#### `generation.enabled: false`
The knowledge base returns raw retrieved passage text to the agent. The agent's
LLM is responsible for synthesising, formatting, and citing the answer. This
gives the agent full control over the out-of-scope guardrail and citation style.

#### Why local `.txt` files instead of live crawling

The IBM Bob documentation site (`bob.ibm.com`) is a **JavaScript Single Page
Application (SPA)**. A simple `requests.get()` HTTP call returns an empty HTML
shell with no content — the real text is rendered client-side by JavaScript.
This makes direct URL crawling impractical without a headless browser.

The extraction approach used here (Bob's internal `search_ibm_docs` MCP tool)
returns the actual documentation text as pre-indexed chunks from the IBM
internal search index — bypassing the SPA rendering problem entirely.

### 3.3 What "knowledge source" means in this context

| Term | Definition in this project |
|------|---------------------------|
| **Upstream source** | `https://bob.ibm.com/docs/` — the live IBM Bob docs site |
| **Local copy** | `knowledge-bases/docs/*.txt` — static text extracted from upstream |
| **Knowledge base** | `ibm_bob_docs` on the wxO platform — Milvus vector index of the local copy |
| **Knowledge source (at query time)** | The Milvus KB — the agent never hits bob.ibm.com directly |

---

## 4. Knowledge Base Configuration Details

### 4.1 KB definition (`knowledge-bases/ibm_bob_docs.kb.yaml`)

```yaml
spec_version: v1
kind: knowledge_base
name: ibm_bob_docs
description: >
  Official IBM Bob documentation sourced from https://bob.ibm.com/docs/.
  Covers all IBM Bob capabilities including IDE features, Bob Shell, enterprise
  plans, premium packages, skills, MCP servers, configuration, Bobcoins,
  Bobalytics analytics, security, telemetry, and modes.
  Content is extracted from the live IBM Bob documentation via the Bob search API.
documents:
  - path: docs/01_overview.txt
  - path: docs/02_bob_shell.txt
  - path: docs/03_enterprise.txt
  - path: docs/04_premium_packages.txt
  - path: docs/05_skills.txt
  - path: docs/06_mcp.txt
  - path: docs/07_security.txt
  - path: docs/08_telemetry.txt
  - path: docs/09_modes.txt
  - path: docs/10_bobcoins.txt
  - path: docs/11_bobalytics.txt
conversational_search_tool:
  query_source: Agent
  generation:
    enabled: false
```

### 4.2 Agent KB linkage (`agents/ibm_bob_assistant.agent.yaml`)

```yaml
knowledge_base:
  - ibm_bob_docs    # ← the only knowledge base linked to this agent
```

The agent has exactly one knowledge base. There are no secondary or fallback
knowledge bases. When the agent cannot find relevant passages in `ibm_bob_docs`,
it triggers the out-of-scope guardrail defined in its `instructions`.

### 4.3 The extraction script (`scripts/fetch_ibm_bob_docs.py`)

The script queries the Bob internal search API with 28 targeted queries across
11 topic areas:

| File | Queries sent |
|------|-------------|
| `01_overview.txt` | 3 queries: overview, FAQ, getting started |
| `02_bob_shell.txt` | 3 queries: terminal, capabilities, slash commands |
| `03_enterprise.txt` | 3 queries: admin, management, subscription |
| `04_premium_packages.txt` | 2 queries: packages, user assignment |
| `05_skills.txt` | 3 queries: creation, workflow, approval |
| `06_mcp.txt` | 4 queries: configuration, transports, shell, security |
| `07_security.txt` | 3 queries: guidelines, auto-approve, MCP security |
| `08_telemetry.txt` | 2 queries: data collection, opt-in |
| `09_modes.txt` | 3 queries: built-in, custom, shell |
| `10_bobcoins.txt` | 3 queries: usage, tiers, enterprise pool |
| `11_bobalytics.txt` | 3 queries: dashboard, KPIs, navigation |

Each query fetches `top_k=8` result chunks. Duplicate chunks (same `id`) are
discarded before writing. The API is called at `POST $BOB_SEARCH_API_URL` with
`library_name: "bob"` in the payload.

---

## 5. Verification Instructions

### 5.1 Verify the KB documents on the platform

```bash
# Show full KB status — documents, readiness, index status
venv/bin/orchestrate knowledge-bases status -n ibm_bob_docs
```

Expected output (documents column shows the 11 files):

```
┃ Name         ┃ Ready ┃ Built In Index Status ┃ Documents (11)        ┃
│ ibm_bob_docs │ True  │ ready                 │ 01_overview.txt       │
│              │       │                       │ 02_bob_shell.txt      │
│              │       │                       │ 03_enterprise.txt     │
│              │       │                       │ 04_premium_packages…  │
│              │       │                       │ 05_skills.txt         │
│              │       │                       │ 06_mcp.txt            │
│              │       │                       │ 07_security.txt       │
│              │       │                       │ 08_telemetry.txt      │
│              │       │                       │ 09_modes.txt          │
│              │       │                       │ 10_bobcoins.txt       │
│              │       │                       │ 11_bobalytics.txt     │
```

### 5.2 Inspect the raw content of a local doc file

```bash
# Read the source attribution line from each file
grep "^Source:" knowledge-bases/docs/*.txt
```

Expected output — every file cites a real bob.ibm.com URL:

```
knowledge-bases/docs/01_overview.txt:Source: https://bob.ibm.com/docs/
knowledge-bases/docs/02_bob_shell.txt:Source: https://bob.ibm.com/docs/shell/
knowledge-bases/docs/03_enterprise.txt:Source: https://bob.ibm.com/docs/ide/enterprise/
knowledge-bases/docs/04_premium_packages.txt:Source: https://bob.ibm.com/docs/ide/premium-packages/
knowledge-bases/docs/05_skills.txt:Source: https://bob.ibm.com/docs/ide/features/skills
knowledge-bases/docs/06_mcp.txt:Source: https://bob.ibm.com/docs/ide/configuration/mcp/
knowledge-bases/docs/07_security.txt:Source: https://bob.ibm.com/docs/ide/security/bob-security-guidance
knowledge-bases/docs/08_telemetry.txt:Source: https://bob.ibm.com/docs/ide/configuration/telemetry-data
knowledge-bases/docs/09_modes.txt:Source: https://bob.ibm.com/docs/ide/features/modes
knowledge-bases/docs/10_bobcoins.txt:Source: https://bob.ibm.com/docs/ide/account/bobcoins
knowledge-bases/docs/11_bobalytics.txt:Source: https://bob.ibm.com/docs/ide/features/bobalytics
```

### 5.3 Verify the agent is linked to the correct KB

```bash
venv/bin/orchestrate agents get -n ibm_bob_assistant
```

Confirm the `knowledge_base:` field includes `ibm_bob_docs` and nothing else.

### 5.4 Verify content freshness by checking file timestamps

```bash
ls -la knowledge-bases/docs/*.txt
# All files should share the same creation/modification date
# reflecting when the docs were last fetched
```

### 5.5 Confirm the agent retrieves from the KB during a chat

Ask the agent a question that is specific enough to require retrieval:

```bash
venv/bin/orchestrate chat ask --agent-name ibm_bob_assistant
> What is the Bobcoin monthly reset policy?
```

The response must include a `Source:` citation with a `bob.ibm.com` URL.
A response without a citation, or a generic AI response with no IBM-specific
detail, indicates the KB retrieval is not working.

### 5.6 Confirm the content matches the upstream source

Cross-check a specific answer against the live documentation:

1. Ask the agent: `What data types should not be processed with Bob?`
2. Open the live docs: `https://bob.ibm.com/docs/ide/getting-started/`
3. Compare the lists — they should match exactly (as of the extraction date).

---

## 6. Switching Knowledge Sources

There are two scenarios: **refreshing** the existing source (updating the local
copies from bob.ibm.com) and **replacing** the source with a different origin
(e.g. a custom internal documentation site).

---

### 6.1 Scenario A — Refresh from the IBM Bob documentation site

Use this when the IBM Bob docs have been updated and you want the agent to
reflect those changes.

**Prerequisites:** You must have access to the Bob internal search API
credentials (`BOB_SEARCH_API_URL` and `BOB_SEARCH_API_TOKEN`). These are IBM
internal credentials — if you do not have them, contact the IBM Bob team.

```bash
# Step 1: Set credentials in .env
# Edit .env and populate:
#   BOB_SEARCH_API_URL=<internal-bob-search-endpoint>
#   BOB_SEARCH_API_TOKEN=<your-token>

# Step 2: Load credentials and re-fetch all 11 doc files
export $(grep -v '^#' .env | xargs)
python3 scripts/fetch_ibm_bob_docs.py
```

Expected output:

```
Writing documentation text files to knowledge-bases/docs/
  Fetching 01_overview.txt ... OK (3,278 chars)
  Fetching 02_bob_shell.txt ... OK (4,126 chars)
  ...
  Fetching 11_bobalytics.txt ... OK (2,326 chars)

Done. Re-import the knowledge base with:
  orchestrate knowledge-bases import -f knowledge-bases/ibm_bob_docs.kb.yaml
```

```bash
# Step 3: Force re-import KB and agent with fresh content
./scripts/start.sh --force-reimport
```

---

### 6.2 Scenario B — Replace with a different documentation source

Use this to point the agent at a different documentation set entirely (e.g.
your own internal IBM Bob customisation guide, or a different product's docs).

#### Step 1 — Prepare your replacement `.txt` files

Create plain `.txt` files (not `.md` — watsonx Orchestrate rejects markdown
files at KB ingestion) in `knowledge-bases/docs/`:

```bash
mkdir -p knowledge-bases/docs/custom
# Write or copy your .txt files into this directory
# Example: knowledge-bases/docs/custom/my_topic.txt
```

#### Step 2 — Update `knowledge-bases/ibm_bob_docs.kb.yaml`

Replace or add entries in the `documents:` list:

```yaml
# Option A: Replace all documents (point at new files only)
documents:
  - path: docs/custom/my_topic_01.txt
  - path: docs/custom/my_topic_02.txt

# Option B: Add new documents alongside the existing ones
documents:
  - path: docs/01_overview.txt
  # ... existing files ...
  - path: docs/custom/my_topic.txt   # ← new addition
```

#### Step 3 — Re-import the KB

```bash
./scripts/start.sh --force-reimport
```

This deletes the old Milvus index and creates a new one from your updated
document list.

#### Step 4 — Update agent instructions (optional)

If your new content is from a different domain, update the source URL in the
agent's `instructions` field so citations point to the right place:

```yaml
# agents/ibm_bob_assistant.agent.yaml
instructions: |
  ...
  2. **Always cite your source.**
     When you provide an answer, include a reference such as:
     > Source: My Documentation — https://my-docs.example.com/<section>
  ...
```

Then re-import the agent:

```bash
venv/bin/orchestrate agents import -f agents/ibm_bob_assistant.agent.yaml
```

---

### 6.3 Scenario C — Add a second knowledge base (multi-KB routing)

The `knowledge_base:` field in the agent YAML accepts a list. You can add a
second KB for a different topic area, and the agent will route queries between
them based on each KB's `description`.

```yaml
# agents/ibm_bob_assistant.agent.yaml
knowledge_base:
  - ibm_bob_docs          # existing KB — general IBM Bob docs
  - ibm_bob_enterprise    # new KB — enterprise admin guide only
```

```yaml
# knowledge-bases/ibm_bob_enterprise.kb.yaml
spec_version: v1
kind: knowledge_base
name: ibm_bob_enterprise
description: >
  IBM Bob Enterprise plan administration. Covers admin dashboard, Bobcoin
  shared pools, Bobalytics analytics, user management, and Enterprise support.
  Use this KB for questions about Enterprise plan administration, not general
  Bob features.
documents:
  - path: docs/enterprise/admin-guide.txt
  - path: docs/enterprise/bobalytics.txt
conversational_search_tool:
  query_source: Agent
  generation:
    enabled: false
```

> **Routing note:** Each KB is exposed as its own retrieval tool, named after
> the KB. The agent routes between them based on the KB `description`. Write
> the `description` as a routing trigger (what types of questions land here),
> not a summary.

---

### 6.4 Configuration change summary

| Goal | Files to change | Command |
|------|----------------|---------|
| Refresh content from bob.ibm.com | `knowledge-bases/docs/*.txt` (via script) | `python3 scripts/fetch_ibm_bob_docs.py` → `./scripts/start.sh --force-reimport` |
| Replace with custom `.txt` files | `knowledge-bases/docs/*.txt` + `ibm_bob_docs.kb.yaml` | `./scripts/start.sh --force-reimport` |
| Add a new topic to the existing KB | Add `.txt` file + add entry to `ibm_bob_docs.kb.yaml` | `./scripts/start.sh --force-reimport` |
| Add a second separate KB | New `*.kb.yaml` + new `.txt` files + update agent YAML | `orchestrate knowledge-bases import -f ...` → `./scripts/start.sh --skip-kb-check` |
| Remove a topic from the KB | Remove from `ibm_bob_docs.kb.yaml` documents list | `./scripts/start.sh --force-reimport` |
| Change the agent's citation URL | Edit `instructions:` in agent YAML | `orchestrate agents import -f agents/ibm_bob_assistant.agent.yaml` |

---

## 7. Troubleshooting Knowledge Source Issues

### Issue 1 — Agent cites the wrong URL

**Symptom:** Agent responds correctly but cites `https://bob.ibm.com/fr/docs/`
instead of `https://bob.ibm.com/docs/`.

**Root cause:** The agent YAML `instructions` field has a French locale prefix
(`/fr/`) in the hardcoded citation URL. The KB files cite the canonical
`/docs/` path (no locale).

**Location:** [`agents/ibm_bob_assistant.agent.yaml`](../agents/ibm_bob_assistant.agent.yaml) lines 17, 28, 35.

**Fix:** Update the citation URL in `instructions`:

```yaml
instructions: |
  ...
  2. **Always cite your source.**
     When you provide an answer, include a reference such as:
     > Source: IBM Bob Docs — https://bob.ibm.com/docs/<section>
  ...
```

Then re-import:

```bash
venv/bin/orchestrate agents import -f agents/ibm_bob_assistant.agent.yaml
```

---

### Issue 2 — Agent returns out-of-scope for IBM Bob questions

**Symptom:** Asking `What is IBM Bob?` triggers the refusal message instead of
an answer.

**Possible causes, in order of likelihood:**

| Cause | Check | Fix |
|-------|-------|-----|
| KB not ready (still indexing) | `orchestrate knowledge-bases status -n ibm_bob_docs` — look for `Ready = True` | Wait and re-test |
| KB imported but agent imported before KB was ready | Check agent import timestamp vs. KB ready timestamp | `orchestrate agents import -f agents/ibm_bob_assistant.agent.yaml` |
| `.txt` files are empty (credentials not set during fetch) | `wc -c knowledge-bases/docs/*.txt` — all should be > 1,000 bytes | Set `BOB_SEARCH_API_URL` + `BOB_SEARCH_API_TOKEN` and re-run `fetch_ibm_bob_docs.py` |
| Agent is not linked to the KB | `orchestrate agents get -n ibm_bob_assistant` — confirm `knowledge_base: ibm_bob_docs` | Re-import agent YAML |
| KB was deleted and not re-imported | `orchestrate knowledge-bases list` | `orchestrate knowledge-bases import -f knowledge-bases/ibm_bob_docs.kb.yaml` |

---

### Issue 3 — Agent answers from stale content (old doc version)

**Symptom:** Agent gives an answer that contradicts what the current live
bob.ibm.com documentation says.

**Root cause:** The `.txt` files were extracted on **2026-10-14**. Any
documentation changes after that date are not reflected.

**Check content age:**

```bash
ls -la knowledge-bases/docs/*.txt | awk '{print $6, $7, $8, $9}'
```

**Fix:**

```bash
export BOB_SEARCH_API_URL=<endpoint>
export BOB_SEARCH_API_TOKEN=<token>
python3 scripts/fetch_ibm_bob_docs.py
./scripts/start.sh --force-reimport
```

---

### Issue 4 — Multiple knowledge bases causing routing confusion

**Symptom:** After adding a second KB, the agent sometimes answers from the
wrong one, or misses information that exists in one of them.

**Root cause:** The routing between multiple KBs is driven entirely by each
KB's `description` field. If descriptions overlap or are too vague, the agent
picks arbitrarily.

**Fix:** Make KB descriptions mutually exclusive and specific:

```yaml
# Good — routing-trigger style, mutually exclusive
# KB 1 description:
description: >
  General IBM Bob features: IDE extension, code generation, Bob Shell,
  skills, MCP servers, configuration. For questions about what Bob can do.

# KB 2 description:
description: >
  IBM Bob Enterprise plan ONLY: admin dashboard, Bobcoin shared pools,
  Bobalytics analytics, user management. For Enterprise administrators only.
```

Also add routing guidance to the agent's `instructions`:

```yaml
instructions: |
  ...
  When a question is about Enterprise administration (admin dashboard, shared
  Bobcoin pools, Bobalytics), always query the ibm_bob_enterprise knowledge
  base. For all other IBM Bob questions, use ibm_bob_docs.
  ...
```

---

### Issue 5 — Content exists in `.txt` files but agent cannot find it

**Symptom:** You can `grep` for a term in the `.txt` files, but the agent
returns out-of-scope for a question about that term.

**Possible causes:**

| Cause | Check | Fix |
|-------|-------|-----|
| Term is in `.md` files (which are not indexed) | `grep "term" knowledge-bases/docs/*.md` | Move content to corresponding `.txt` file |
| Content was added to `.txt` after last KB import | Check file timestamps vs. KB import date | Re-import KB: `./scripts/start.sh --force-reimport` |
| Content chunk is too small for the vector search to score highly | Check if the section is < 50 words | Expand or merge small sections |
| Query phrasing doesn't match the indexed text | Try different phrasings in the chat | Content is present but retrieval needs rephrasing |

**Verify the KB was imported with the current `.txt` content:**

```bash
# Get the KB ID from the status command
venv/bin/orchestrate knowledge-bases status -n ibm_bob_docs

# The Documents column lists exactly the files that were indexed
# Compare against ls knowledge-bases/docs/*.txt
```

If the document list on the platform does not match your local files,
run `./scripts/start.sh --force-reimport`.

---

### Issue 6 — `.md` files visible in `knowledge-bases/docs/` but not indexed

**Symptom:** There are both `01_overview.md` and `01_overview.txt` in
`knowledge-bases/docs/`. The KB only indexes the `.txt` files. The `.md` files
are completely ignored.

**Explanation:** The KB YAML (`ibm_bob_docs.kb.yaml`) lists only `.txt` paths.
Additionally, watsonx Orchestrate KB ingestion rejects `.md` files with:

```
Unsupported file type text/markdown
```

The `.md` files are **redundant authoring artefacts** from the project creation
phase. They are identical in content to the `.txt` files. They are committed to
the repo but have no effect on agent behaviour.

**Safe to remove (optional):**

```bash
./scripts/cleanup.sh --all
# The --all flag removes knowledge-bases/docs/*.md while preserving *.txt
```
