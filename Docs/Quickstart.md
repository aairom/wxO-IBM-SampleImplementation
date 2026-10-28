# Quickstart — IBM Bob Documentation Assistant

`ibm_bob_assistant` is a **watsonx Orchestrate native agent** that answers
questions about IBM Bob features and capabilities, grounded in real IBM Bob
documentation stored in a Milvus knowledge base.

> For the full reference — all flags, troubleshooting, and issue log — see
> [`Docs/Deployment.md`](./Deployment.md).

---

## Prerequisites

| Requirement | Check |
|-------------|-------|
| Python 3.10+ | `python3 --version` |
| `uv` | [Install](https://docs.astral.sh/uv/) |
| IBM Cloud API key | [Generate](https://cloud.ibm.com/iam/apikeys) |
| watsonx Orchestrate instance URL | SaaS or Developer Edition |

---

## 5-minute deploy

```bash
# 1. Install dependencies
uv venv venv && source venv/bin/activate
uv pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Edit .env — set ORCHESTRATE_URL and IBM_CLOUD_API_KEY

# 3. Deploy
./scripts/start.sh
```

That's it. The script authenticates, imports the knowledge base, waits for
indexing, and imports the agent. On success it prints:

```
╔══════════════════════════════════════════════════════════════╗
║  IBM Bob Documentation Assistant — deployed successfully     ║
╚══════════════════════════════════════════════════════════════╝
```

---

## Test the agent

> `orchestrate chat ask` requires an **interactive TTY** — run it directly in
> a terminal, not piped.

```bash
venv/bin/orchestrate chat ask --agent-name ibm_bob_assistant
```

| Query | Expected behaviour |
|-------|-------------------|
| `What is IBM Bob?` | Overview + source citation |

---

## IBM Documentation Assistant (`IBM_Doc_Assistant`)

For the live documentation scraping and vector indexing agent:

```bash
# 1. Ingest live documentation
python3 scripts/ingest_docs.py

# 2. Deploy agent and tools
python3 scripts/deploy_orchestrate_agent.py

# 3. Test agent query
venv/bin/orchestrate chat ask --agent-name ibm_doc_assistant
```

See [`Docs/New_Agent_Documentation.md`](./New_Agent_Documentation.md) for full details.
| `What can Bob Shell do?` | Terminal capabilities |
| `How do Bobcoins work?` | Budget tiers, monthly reset |
| `What are Enterprise plan features?` | Admin dashboard, Bobalytics |
| `How do I create a custom skill?` | SKILL.md format + folder structure |
| `What is MCP in Bob?` | Model Context Protocol, security guidelines |
| `How do I disable telemetry?` | Settings steps; Enterprise caveat |
| `What modes does Bob have?` | Built-in + custom modes |
| `What is the weather in Paris?` | Out-of-scope — agent refuses |

---

## Embed Web Chat

The agent ships with a web chat widget and an HTML slide deck.
Use `scripts/serve.sh` to launch either server:

```bash
./scripts/serve.sh --web       # http://localhost:8080  — main demo + chat widget
./scripts/serve.sh --deck      # http://localhost:8085  — HTML slide deck
./scripts/serve.sh --help      # usage / flag reference
```

| URL | Purpose |
|-----|---------|
| `http://localhost:8080` | Main demo (unsecured live chat) |
| `http://localhost:8080/embed-docs.html` | Documentation hub |
| `http://localhost:8080/demo-unsecured.html` | Unsecured embed demo |
| `http://localhost:8080/demo-secured.html` | Secured embed demo + JWT inspector |
| `http://localhost:8085` | HTML slide deck index |

### Fix "Authentication Error / Agent fetching failed"

IBM wxO embed security is **ON by default**. Pick one path:

**Option A — Disable security (easiest, for non-sensitive agents)**
```
Administration → Settings → Embed Security → Security: OFF → Save
```

**Option B — Enable JWT signing (production-ready)**
```bash
# 1. Generate RSA key pair
bash scripts/generate_rsa_keys.sh

# 2. Upload keys/wxo_embed_public.pem to:
#    Administration → Settings → Embed Security → Security: ON → paste key → Save

# 3. Start JWT server (RS256, port 3001)
source venv/bin/activate
python scripts/jwt_server.py

# 4. Serve pages and open the secured demo
./scripts/serve.sh --web
# → http://localhost:8080/demo-secured.html
```

---

## Common operations

```bash
# Re-deploy (idempotent, KB already ready)
./scripts/start.sh --skip-kb-check

# Force a full re-import of KB + agent
./scripts/start.sh --force-reimport

# Remove agent and KB from the platform
./scripts/stop.sh

# Keep KB but remove agent (saves ~10 min re-indexing on next deploy)
./scripts/stop.sh --keep-kb

# Remove local venv and caches
./scripts/cleanup.sh

# Full local wipe including .env
./scripts/cleanup.sh --all
```

---

## Troubleshooting quick reference

| Symptom | Fix |
|---------|-----|
| `start.sh` exits silently after Step 2 | See [Issue 1](./Deployment.md#issue-1) — `pipefail` + `orchestrate --version` |
| Commands return empty output when piped | See [Issue 2](./Deployment.md#issue-2) — pipe through `cat` |
| KB poll loop never exits | See [Issue 3](./Deployment.md#issue-3) — grep pattern for table output |
| `AGENT_YAML…: unbound variable` | See [Issue 4](./Deployment.md#issue-4) — UTF-8 ellipsis in variable name |
| Agent returns out-of-scope for everything | KB not ready — run `orchestrate knowledge-bases status -n ibm_bob_docs` |
| `No active environment found` | Session expired — run `./scripts/start.sh` to re-authenticate |
| Auth type `[WARNING]` on env activate | Cosmetic only — `ibm_iam` is correct for IBM Cloud SaaS |

---

## Refreshing KB content

The `.txt` files in `knowledge-bases/docs/` are pre-populated. Regenerate
them only when the IBM Bob documentation changes:

```bash
export BOB_SEARCH_API_URL=<internal-bob-search-endpoint>
export BOB_SEARCH_API_TOKEN=<your-token>
python3 scripts/fetch_ibm_bob_docs.py
./scripts/start.sh --force-reimport
```
