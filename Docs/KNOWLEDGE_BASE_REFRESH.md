# Knowledge Base Refresh & Continuous Synchronization Guide

## 1. Overview

Keeping agent knowledge synchronized with upstream IBM documentation is vital for preventing hallucinations and maintaining accuracy. This document outlines the procedures, schedules, and automation workflows for refreshing the vector knowledge base used by `ibm_doc_assistant` and `ibm_bob_assistant`.

---

## 2. Synchronization Pipeline Workflow

```mermaid
flowchart LR
    A[Upstream Docs / Local Text Files] -->|1. Fetch & Normalize| B[Scraper Engine]
    B -->|2. Semantic Chunking| C[Chunker (500w / 50w overlap)]
    C -->|3. Index Vectors| D[TF-IDF Vector Store]
    D -->|4. Save to Disk| E[(ibm_doc_store.json)]
    E -->|5. Update Embedded Corpus| F[src/agents/ibm_doc_agent/tools.py]
    F -->|6. Deploy to Cloud| G[wxO Instance aam-wxo-be]
```

### Key Execution Scripts
1. [`scripts/sync_and_deploy_docs.py`](../scripts/sync_and_deploy_docs.py): Master Python pipeline executing sync, validation, indexing, and deployment.
2. [`scripts/ingest_docs.py`](../scripts/ingest_docs.py): Standalone CLI for local file and URL ingestion.
3. [`scripts/automate.sh refresh`](../scripts/automate.sh): Bash automation command wrapping the end-to-end sync workflow.

---

## 3. Manual Refresh Execution

### Option A: Using the Master Automation Script (Recommended)
```bash
./scripts/automate.sh refresh
```

### Option B: Using Python Directly
```bash
# Ingest local files and rebuild knowledge store
./venv/bin/python scripts/ingest_docs.py --docs-dir knowledge-bases/docs/ --output knowledge-bases/ibm_doc_store.json

# Run end-to-end sync with cloud deployment
./venv/bin/python scripts/sync_and_deploy_docs.py --deploy
```

### Option C: Ingesting Custom Web URLs or Additional Markdown Files
```bash
./venv/bin/python scripts/ingest_docs.py \
  --urls "https://raw.githubusercontent.com/IBM/docs/main/README.md" \
  --docs-dir ./custom_docs/ \
  --output knowledge-bases/ibm_doc_store.json
```

---

## 4. Automated Scheduled Ingestion (Cron / CI/CD)

### 4.1 GitHub Actions Workflow
The repository includes a ready-to-run GitHub Actions workflow located at [`.github/workflows/sync_docs_deploy.yml`](../.github/workflows/sync_docs_deploy.yml).

- **Schedule**: Executes daily at 02:00 UTC (`cron: '0 2 * * *'`).
- **Manual Trigger**: Can be dispatched on-demand via the GitHub Actions UI (`workflow_dispatch`).
- **Required Secrets**:
  - `WO_BEARER_TOKEN`: wxO Cloud IAM or service bearer token.
  - `WO_INSTANCE_ID`: `75c2cabb-2b02-4d65-8127-a9cc65d1ee46`
  - `WO_ENVIRONMENT`: `https://api.eu-de.watson-orchestrate.cloud.ibm.com`
  - `WO_AGENT_ID`: `273c6294-f254-46c5-a9b0-d5be86dd4ec3`

### 4.2 Local Linux / macOS Cron Job Setup
To schedule daily re-indexing on a local or dedicated server:

```bash
# Edit crontab
crontab -e

# Add entry to run daily at 03:00 AM local time
0 3 * * * cd /path/to/wxO-IBM && ./scripts/automate.sh refresh >> /path/to/wxO-IBM/logs/cron_refresh.log 2>&1
```

---

## 5. Verification & Health Checks

After performing a knowledge base refresh, verify integrity using the following checks:

### 1. Vector Store Inspection
```bash
# Check chunk count and summary
./scripts/automate.sh status
```

### 2. Run Interactive Test Queries
```bash
./scripts/automate.sh chat
```
Test queries to evaluate:
- *"How do I configure MCP servers in Bob?"*
- *"What are the available modes in IBM Bob?"*
- *"What keyboard shortcuts are supported in Bob?"*

### 3. Automated Test Suite Validation
```bash
./scripts/automate.sh test
```
All unit tests in [`tests/test_ibm_doc_agent.py`](../tests/test_ibm_doc_agent.py) and [`tests/test_sync_and_deploy_docs.py`](../tests/test_sync_and_deploy_docs.py) should pass with 100% success rate.
