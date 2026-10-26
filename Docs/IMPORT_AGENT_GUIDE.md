# `import_agent.py` — Developer & Operations Guide

`scripts/import_agent.py` is a standalone Python script that imports (or
re-imports) the `ibm_bob_assistant` native agent into a watsonx Orchestrate
environment.  It wraps the `orchestrate agents import` CLI command with
pre-flight validation, structured JSON reporting, idempotency checks, and
human-readable terminal output.

---

## Table of Contents

1. [When to use `import_agent.py` vs `start.sh`](#1-when-to-use-import_agentpy-vs-startsh)
2. [Prerequisites](#2-prerequisites)
3. [Quick-start](#3-quick-start)
4. [CLI Reference](#4-cli-reference)
5. [Exit Code Reference](#5-exit-code-reference)
6. [JSON Report Schema](#6-json-report-schema)
7. [Troubleshooting](#7-troubleshooting)
8. [CI/CD Integration](#8-cicd-integration)
9. [Extending the Script](#9-extending-the-script)

---

## 1. When to use `import_agent.py` vs `start.sh`

| Scenario | Recommended tool |
|---|---|
| First-time full deployment (KB + tools + agent) | `scripts/start.sh` |
| Re-deploy **only** the agent YAML after editing it | `import_agent.py` |
| CI/CD pipeline that imports the agent | `import_agent.py` |
| Scripted dry-run to validate the YAML without deploying | `import_agent.py --dry-run` |
| Automated pipeline that must never prompt for input | `import_agent.py --force` |
| Debug import failures with verbose logs | `import_agent.py --verbose` |

`start.sh` calls `import_agent.py` internally as its final step.
Running the script directly lets you skip the KB and tool steps when only
the agent definition changed.

---

## 2. Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | Already satisfied if the project `venv/` was created |
| `orchestrate` CLI | Installed inside `venv/` via `ibm-watsonx-orchestrate` |
| Active wxO environment | `orchestrate env activate <name>` must have been run |
| `.env` file | Copy `.env.example` → `.env` and fill in all five keys |

### Required `.env` keys

```
ORCHESTRATE_URL=https://<your-region>.ml.cloud.ibm.com
ORCHESTRATE_INSTANCE_ID=<instance-id>
ORCHESTRATE_IAM_URL=https://iam.cloud.ibm.com
ORCHESTRATE_API_KEY=<your-ibm-cloud-api-key>
ORCHESTRATE_TOKEN=<short-lived-iam-bearer-token>
```

> **Note:** `ORCHESTRATE_TOKEN` is a short-lived bearer token (≈ 60 minutes).
> If it expires you will see an `Authentication token expired` error.
> See [Troubleshooting §7.1](#71-authentication--token-errors) for the refresh command.

---

## 3. Quick-start

```bash
# Activate the project virtual environment
source venv/bin/activate

# Standard import — idempotent, prompts before re-importing if agent exists
python scripts/import_agent.py

# Force re-import without prompt (useful after YAML edits)
python scripts/import_agent.py --force

# Dry-run — validate YAML and credentials only, do not touch the platform
python scripts/import_agent.py --dry-run

# Point at a custom YAML file
python scripts/import_agent.py --agent-file path/to/my_agent.yaml

# Verbose output + no log file (useful in CI where logs are captured by the runner)
python scripts/import_agent.py --verbose --no-log-file
```

---

## 4. CLI Reference

```
usage: import_agent.py [-h] [-f AGENT_FILE] [-e ENV_FILE]
                       [--force] [--dry-run] [--mock]
                       [-v] [--no-log-file] [--no-report]
                       [--timeout TIMEOUT]
```

### Flags

| Flag | Default | Description |
|---|---|---|
| `-f`, `--agent-file` | `agents/ibm_bob_assistant.agent.yaml` | Path to the agent YAML definition |
| `-e`, `--env-file` | `.env` | Path to the environment-variables file |
| `--force` | off | Skip the "agent already exists — re-import?" prompt |
| `--dry-run` | off | Validate credentials and YAML; do not call the CLI |
| `--mock` | off | Skip all platform I/O; return a synthetic `mock` result (for testing pipelines) |
| `-v`, `--verbose` | off | Enable DEBUG-level logging to stdout and the log file |
| `--no-log-file` | off | Suppress writing a log file to `logs/` |
| `--no-report` | off | Suppress writing a JSON report to `output/` |
| `--timeout` | `120` | Seconds before the `orchestrate` CLI call is killed |

### Examples

```bash
# Import using a staging YAML with 5-minute timeout
python scripts/import_agent.py \
  --agent-file agents/staging_agent.yaml \
  --timeout 300

# CI pipeline — no interactive prompts, no log file, fail fast
python scripts/import_agent.py --force --no-log-file --verbose

# Validate only — useful in PR checks
python scripts/import_agent.py --dry-run --no-log-file --no-report
```

---

## 5. Exit Code Reference

| Code | Meaning |
|---|---|
| `0` | Success — agent imported (or already existed and user declined re-import, or dry-run passed) |
| `1` | Import failed — see terminal output or JSON report for the error |
| `2` | YAML validation error — agent file missing or malformed |

---

## 6. JSON Report Schema

Unless `--no-report` is passed, a JSON report is written to
`output/import_agent_report_<YYYYMMDD_HHMMSS>.json`.

### Schema

```jsonc
{
  "run_at":              "<ISO-8601 UTC timestamp>",
  "agent_file":          "<path to YAML relative to project root>",
  "environment":         "<active wxO environment name, or '<unknown>'>",
  "agent_already_existed": true,          // was the agent on the platform before this run?
  "reimport_confirmed":  false,           // did the user (or --force) confirm re-import?
  "dry_run":             false,
  "mock":                false,
  "cli_stdout":          "<raw stdout from orchestrate agents import>",
  "cli_stderr":          "<raw stderr>",
  "cli_exit_code":       0,               // -1 if CLI was not called
  "outcome":             "success",       // "success" | "failed" | "dry_run" | "mock" | "pending"
  "error_message":       "",              // human-readable error; empty on success
  "elapsed_seconds":     3.14,
  "warnings":            []               // list of advisory strings (e.g. unknown environment)
}
```

### `outcome` values

| Value | Meaning |
|---|---|
| `success` | Agent imported successfully |
| `failed` | Import attempt was made but returned a non-zero exit code, timed out, or raised an exception |
| `dry_run` | `--dry-run` was passed; no platform call was made |
| `mock` | `--mock` was passed; no platform call was made |
| `pending` | Script was interrupted before an outcome was determined |

### Reading a report in Python

```python
import json, pathlib

report_dir = pathlib.Path("output")
latest = max(report_dir.glob("import_agent_report_*.json"))
with latest.open() as fh:
    report = json.load(fh)

if report["outcome"] != "success":
    print("Import failed:", report["error_message"])
```

---

## 7. Troubleshooting

### 7.1 Authentication / token errors

| Symptom | Cause | Fix |
|---|---|---|
| `Authentication token expired` | `ORCHESTRATE_TOKEN` in `.env` is older than ~60 min | Refresh: `ibmcloud iam oauth-tokens` and update `ORCHESTRATE_TOKEN=` in `.env` |
| `missing or invalid token` | `ORCHESTRATE_TOKEN` not set | Ensure `.env` is present and contains `ORCHESTRATE_TOKEN=...` |
| `No active environment` | No wxO environment activated | Run `orchestrate env activate <name>` |

### 7.2 YAML validation errors (exit code 2)

```
[ERROR] YAML validation failed:
  - missing required key: spec_version
```

All three keys are mandatory in an agent YAML:

```yaml
spec_version: "v1"
kind: native
name: ibm_bob_assistant
```

Check that `agents/ibm_bob_assistant.agent.yaml` contains all three at the
top level.  The script validates this before touching the platform.

### 7.3 Agent already exists

```
Agent 'ibm_bob_assistant' already exists on the platform.
Re-import? [y/N]:
```

- Press `y` to replace the agent definition.
- Press `Enter` / `n` to abort (exit 0).
- Pass `--force` to automatically re-import without prompting.

### 7.4 CLI binary not found

```
[ERROR] 'orchestrate' CLI binary not found at …/venv/bin/orchestrate
```

The virtual environment was not set up or the `ibm-watsonx-orchestrate`
package was not installed.

```bash
uv venv venv
source venv/bin/activate
uv pip install -r requirements.txt
```

### 7.5 Timeout

```
[ERROR] orchestrate agents import timed out after 120 s
```

The default timeout is 120 seconds.  Increase it:

```bash
python scripts/import_agent.py --timeout 300
```

### 7.6 Unknown active environment warning

```
[WARNING] Could not determine active wxO environment — continuing anyway
```

The script could not parse `orchestrate envs list` output.  This is
non-fatal; the import proceeds.  Check that an environment is active:

```bash
orchestrate envs list | cat
```

If none shows as active, run `orchestrate env activate <name>`.

### 7.7 Permission denied

```
[ERROR] Permission denied — check that this account has the Agent Editor role.
```

The `ORCHESTRATE_API_KEY` belongs to an account without write access to the
wxO instance.  Contact your instance administrator.

---

## 8. CI/CD Integration

### GitHub Actions example

```yaml
# .github/workflows/deploy-agent.yml
name: Deploy IBM Bob Assistant

on:
  push:
    paths:
      - "agents/ibm_bob_assistant.agent.yaml"

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install uv
        run: pip install uv

      - name: Create virtual environment and install dependencies
        run: |
          uv venv venv
          source venv/bin/activate
          uv pip install -r requirements.txt

      - name: Write .env from secrets
        run: |
          cat > .env <<EOF
          ORCHESTRATE_URL=${{ secrets.ORCHESTRATE_URL }}
          ORCHESTRATE_INSTANCE_ID=${{ secrets.ORCHESTRATE_INSTANCE_ID }}
          ORCHESTRATE_IAM_URL=${{ secrets.ORCHESTRATE_IAM_URL }}
          ORCHESTRATE_API_KEY=${{ secrets.ORCHESTRATE_API_KEY }}
          ORCHESTRATE_TOKEN=${{ secrets.ORCHESTRATE_TOKEN }}
          EOF

      - name: Activate wxO environment
        run: |
          source venv/bin/activate
          orchestrate env activate ${{ secrets.ORCHESTRATE_ENV_NAME }}

      - name: Import agent
        run: |
          source venv/bin/activate
          python scripts/import_agent.py \
            --force \
            --verbose \
            --no-log-file \
            --timeout 180

      - name: Upload import report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: import-report
          path: output/import_agent_report_*.json
```

### Dry-run in PR checks

```yaml
  validate:
    runs-on: ubuntu-latest
    steps:
      # … checkout, setup, install …

      - name: Validate agent YAML (dry run)
        run: |
          source venv/bin/activate
          python scripts/import_agent.py \
            --dry-run \
            --no-log-file \
            --no-report
        # exits 0 if YAML is valid; exits 2 if validation fails
```

### Reading the report in a downstream job

```bash
report=$(ls -t output/import_agent_report_*.json | head -1)
outcome=$(python3 -c "import json; d=json.load(open('$report')); print(d['outcome'])")
if [ "$outcome" != "success" ]; then
  echo "Import did not succeed: $(python3 -c "import json; d=json.load(open('$report')); print(d['error_message'])")"
  exit 1
fi
```

---

## 9. Extending the Script

### Adding a new pre-flight check

All pre-flight checks live in `scripts/import_agent.py` inside the `run()`
function, before the `_do_import()` call.  Add your check and append to
`result.warnings` (advisory) or set `result.outcome = "failed"` (blocking):

```python
# Example: refuse to import if the KB is not ready
kb_ready = _check_kb_ready("ibm_bob_docs", log)
if not kb_ready:
    result.outcome = "failed"
    result.error_message = "Knowledge base 'ibm_bob_docs' is not ready."
    return result
```

### Changing the default agent file

Update the module-level constant at the top of `import_agent.py`:

```python
DEFAULT_AGENT_YAML = _PROJECT_ROOT / "agents" / "ibm_bob_assistant.agent.yaml"
```

### Changing report output directory

```python
OUTPUT_DIR = _PROJECT_ROOT / "output"   # change this line
```

Or override at runtime by patching `ia.OUTPUT_DIR` in tests (see
`tests/test_import_agent.py :: TestWriteReport.setUp`).
