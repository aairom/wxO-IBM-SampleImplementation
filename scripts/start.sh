#!/usr/bin/env bash
# ==============================================================================
# start.sh — Deploy the IBM Bob Documentation Assistant to watsonx Orchestrate
#
# Usage:
#   ./scripts/start.sh [--force-reimport] [--skip-kb-check] [--start-jwt-server]
#
# What it does (idempotent — safe to run multiple times):
#   1. Validates required environment variables from .env
#   2. Authenticates the orchestrate CLI against the target wxO instance
#   3. Imports the knowledge base (11 IBM Bob doc .txt files)
#   4. Waits for KB indexing to complete (polls until Ready = True)
#   5. Imports the Python tools (search_bob_documentation, get_bob_doc_section)
#   6. Imports the agent (references tools + KB)
#   7. Deploys the agent to Live environment
#   8. Regenerates web/webchat-config.js with fresh embed IDs
#   9. (Optional) Starts the JWT signing server for secured embed
#
# Options:
#   --force-reimport    Remove and re-import KB + agent (forces a clean slate)
#   --skip-kb-check     Skip the KB readiness poll (use when KB is already ready)
#   --start-jwt-server  Auto-generate RSA keys (if missing) and launch jwt_server.py
#
# Dependencies:
#   - Python venv at ./venv with `orchestrate` CLI installed
#   - .env file at the project root (copy .env.example and fill in values)
# ==============================================================================
set -euo pipefail

# ── Constants ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"
VENV_ORCHESTRATE="$PROJECT_ROOT/venv/bin/orchestrate"
KB_YAML="$PROJECT_ROOT/knowledge-bases/ibm_bob_docs.kb.yaml"
AGENT_YAML="$PROJECT_ROOT/agents/ibm_bob_assistant.agent.yaml"
TOOLS_FILE="$PROJECT_ROOT/tools/live_bob_search.py"
KB_NAME="ibm_bob_docs"
AGENT_NAME="ibm_bob_assistant"
KB_POLL_INTERVAL=10   # seconds between status polls
KB_POLL_MAX=60        # maximum polling attempts (~10 minutes)

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
die()     { error "$*"; exit 1; }
section() { echo -e "\n${BOLD}━━━ $* ${RESET}"; }

# ── Parse arguments ────────────────────────────────────────────────────────────
FORCE_REIMPORT=false
SKIP_KB_CHECK=false
START_JWT_SERVER=false
for arg in "$@"; do
  case "$arg" in
    --force-reimport)   FORCE_REIMPORT=true ;;
    --skip-kb-check)    SKIP_KB_CHECK=true ;;
    --start-jwt-server) START_JWT_SERVER=true ;;
    *) die "Unknown argument: $arg (valid: --force-reimport, --skip-kb-check, --start-jwt-server)" ;;
  esac
done

# ── Step 1: Load and validate .env ─────────────────────────────────────────────
section "Step 1 — Loading environment variables"

[[ -f "$ENV_FILE" ]] || die ".env not found at $ENV_FILE — run: cp .env.example .env"

# Export variables from .env (skip comments and blank lines)
set -a
# shellcheck disable=SC1090
while IFS='=' read -r key value; do
  [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
  key="${key%%[[:space:]]*}"
  value="${value%%[[:space:]]*}"
  [[ -n "$key" ]] && export "$key"="$value"
done < "$ENV_FILE"
set +a

REQUIRED_VARS=("ORCHESTRATE_URL" "IBM_CLOUD_API_KEY")
for var in "${REQUIRED_VARS[@]}"; do
  [[ -n "${!var:-}" ]] || die "Required variable $var is empty in .env"
done

ENV_NAME="${ORCHESTRATE_ENV_NAME:-wxo-ibm-bob}"
ORCHESTRATE_REGION=$(echo "$ORCHESTRATE_URL" | grep -oE 'api\.[a-z0-9-]+\.' | head -1 | sed 's/api\.\(.*\)\./\1/')

ok "ORCHESTRATE_URL  = $ORCHESTRATE_URL"
ok "IBM_CLOUD_API_KEY = ${IBM_CLOUD_API_KEY:0:6}…${IBM_CLOUD_API_KEY: -4} (masked)"
ok "ORCHESTRATE_ENV_NAME = $ENV_NAME"

# ── Step 2: Verify orchestrate CLI ─────────────────────────────────────────────
section "Step 2 — Verifying orchestrate CLI"

[[ -x "$VENV_ORCHESTRATE" ]] || die "orchestrate CLI not found at $VENV_ORCHESTRATE — run: uv pip install -r requirements.txt"
WXO_VERSION=$("$VENV_ORCHESTRATE" --version 2>&1 | { head -1 ; cat > /dev/null; })
ok "CLI: $WXO_VERSION"

# Alias for readability
ORC="$VENV_ORCHESTRATE"

# ── Step 3: Register and activate environment ──────────────────────────────────
section "Step 3 — Authenticating with watsonx Orchestrate"

# Register the environment if it isn't already known
if "$ORC" env list 2>/dev/null | cat | grep -q "$ENV_NAME"; then
  info "Environment '$ENV_NAME' already registered"
else
  info "Registering environment '$ENV_NAME'…"
  "$ORC" env add -n "$ENV_NAME" -u "$ORCHESTRATE_URL" || die "Failed to register environment"
  ok "Environment registered"
fi

# Activate and authenticate
info "Activating environment '$ENV_NAME' with IBM Cloud API key…"
"$ORC" env activate "$ENV_NAME" --api-key "$IBM_CLOUD_API_KEY" \
  || die "Authentication failed — check ORCHESTRATE_URL and IBM_CLOUD_API_KEY in .env"
ok "Authenticated successfully"

# Sanity check: list agents to confirm connectivity
info "Verifying connectivity…"
"$ORC" agents list 2>&1 | cat > /dev/null || die "Could not reach wxO API — check ORCHESTRATE_URL"
ok "Connected to watsonx Orchestrate"

# ── Step 4: Import knowledge base ──────────────────────────────────────────────
section "Step 4 — Importing knowledge base ($KB_NAME)"

if [[ "$FORCE_REIMPORT" == "true" ]]; then
  info "--force-reimport: removing existing KB if present…"
  "$ORC" knowledge-bases delete -n "$KB_NAME" 2>/dev/null && ok "Removed $KB_NAME" || info "$KB_NAME not found — nothing to remove"
fi

if "$ORC" knowledge-bases list 2>/dev/null | cat | grep -q "$KB_NAME"; then
  info "Knowledge base '$KB_NAME' already exists — skipping import (use --force-reimport to overwrite)"
else
  info "Importing $KB_YAML…"
  "$ORC" knowledge-bases import -f "$KB_YAML" \
    || die "Knowledge base import failed — check $KB_YAML"
  ok "Knowledge base import submitted"
fi

# ── Step 5: Wait for KB indexing ───────────────────────────────────────────────
section "Step 5 — Waiting for knowledge base to be ready"

if [[ "$SKIP_KB_CHECK" == "true" ]]; then
  warn "--skip-kb-check: skipping KB readiness poll"
else
  info "Polling knowledge-bases status (max ${KB_POLL_MAX} attempts, every ${KB_POLL_INTERVAL}s)…"
  attempt=0
  while (( attempt < KB_POLL_MAX )); do
    attempt=$(( attempt + 1 ))
    KB_STATUS=$("$ORC" knowledge-bases status -n "$KB_NAME" 2>&1 | cat || true)
    if echo "$KB_STATUS" | grep -qE "│[[:space:]]+True[[:space:]]+│[[:space:]]+ready|Ready.*True|status.*ready"; then
      ok "Knowledge base '$KB_NAME' is Ready (attempt $attempt)"
      break
    fi
    if (( attempt == KB_POLL_MAX )); then
      warn "KB not ready after $KB_POLL_MAX polls. Continuing anyway — agent may return empty answers until indexing finishes."
      warn "Check manually: $ORC knowledge-bases status -n $KB_NAME"
      break
    fi
    info "  Not ready yet (attempt $attempt/$KB_POLL_MAX)… retrying in ${KB_POLL_INTERVAL}s"
    sleep "$KB_POLL_INTERVAL"
  done
fi

# ── Step 5b: Import Python tools via orchestration manager ────────────────────
section "Step 5b — Importing Python tools (import_tools.py)"

IMPORT_SCRIPT="$PROJECT_ROOT/scripts/import_tools.py"
PYTHON_BIN="$PROJECT_ROOT/venv/bin/python"

if [[ -f "$IMPORT_SCRIPT" ]]; then
  info "Running import_tools.py…"

  # Pass --force-reimport if the outer script was called with that flag
  IMPORT_FLAGS="--skip-agent-deploy"   # agent is deployed in Step 6
  [[ "$FORCE_REIMPORT" == "true" ]] && IMPORT_FLAGS="$IMPORT_FLAGS --force-reimport"

  "$PYTHON_BIN" "$IMPORT_SCRIPT" $IMPORT_FLAGS \
    || die "Tool import failed — see output above or check output/tool_import_report_*.json"
  ok "Python tools imported and verified"
else
  # Fallback: direct CLI import (no orchestration report)
  warn "import_tools.py not found — falling back to direct CLI import"
  if [[ -f "$TOOLS_FILE" ]]; then
    "$ORC" tools import -k python -f "$TOOLS_FILE" \
      || die "Tool import failed — check $TOOLS_FILE"
    ok "Tools imported (direct CLI fallback)"
  else
    warn "Tools file not found at $TOOLS_FILE — skipping tool import"
  fi
fi

# ── Step 6: Import agent ───────────────────────────────────────────────────────
section "Step 6 — Importing agent ($AGENT_NAME)"

if [[ "$FORCE_REIMPORT" == "true" ]]; then
  info "--force-reimport: removing existing agent if present…"
  "$ORC" agents remove -n "$AGENT_NAME" 2>/dev/null && ok "Removed $AGENT_NAME" || info "$AGENT_NAME not found — nothing to remove"
fi

info "Importing $AGENT_YAML"
"$ORC" agents import -f "$AGENT_YAML" \
  || die "Agent import failed — check $AGENT_YAML"
ok "Agent '$AGENT_NAME' imported successfully"

# ── Step 7: Deploy agent to Live environment ───────────────────────────────────
section "Step 7 — Deploying agent to Live environment"

# 'agents deploy' moves the agent from Draft to Live state.
# Without this step the web chat widget returns "Agent fetching failed" /
# "Authentication Error" even though the loader (wxoLoader.js) loads fine.
info "Deploying '$AGENT_NAME' to Live…"
"$ORC" agents deploy --name "$AGENT_NAME" \
  || die "Agent deploy failed — check CLI output above"
ok "Agent '$AGENT_NAME' is now Live"

# ── Step 8: Regenerate webchat-config.js with fresh embed values ──────────────
section "Step 8 — Regenerating web/webchat-config.js"

info "Running get_webchat_embed.sh to refresh embed IDs…"
bash "$SCRIPT_DIR/get_webchat_embed.sh" \
  || warn "Embed snippet generation failed — web/webchat-config.js may be stale"

# ── Step 9 (optional): Start JWT signing server for secured embed ─────────────
section "Step 9 — JWT signing server (optional)"

if [[ "$START_JWT_SERVER" == "true" ]]; then
  JWT_KEY="${EMBED_PRIVATE_KEY_FILE:-keys/wxo_embed_private.pem}"
  if [[ ! -f "$PROJECT_ROOT/$JWT_KEY" ]]; then
    warn "Private key not found at $JWT_KEY — generating one now…"
    bash "$SCRIPT_DIR/generate_rsa_keys.sh" || warn "Key generation failed — run manually"
  fi

  PYTHON_BIN="$PROJECT_ROOT/venv/bin/python"
  JWT_LOG="$PROJECT_ROOT/logs/jwt_server.log"
  mkdir -p "$PROJECT_ROOT/logs"

  info "Starting JWT server on port ${JWT_SERVER_PORT:-3001} (background)…"
  EMBED_PRIVATE_KEY_FILE="$PROJECT_ROOT/$JWT_KEY" \
  JWT_SERVER_PORT="${JWT_SERVER_PORT:-3001}" \
  JWT_EXPIRY_SECONDS="${JWT_EXPIRY_SECONDS:-3600}" \
  ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-http://localhost:8080}" \
  "$PYTHON_BIN" "$SCRIPT_DIR/jwt_server.py" > "$JWT_LOG" 2>&1 &

  JWT_PID=$!
  sleep 1
  if kill -0 "$JWT_PID" 2>/dev/null; then
    ok "JWT server running (PID $JWT_PID) → http://localhost:${JWT_SERVER_PORT:-3001}"
    ok "Logs: $JWT_LOG"
  else
    warn "JWT server failed to start — check $JWT_LOG"
  fi
else
  info "Skipping JWT server (use --start-jwt-server to launch it automatically)"
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗"
echo -e "║  IBM Bob Documentation Assistant — deployed successfully     ║"
echo -e "╚══════════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${BOLD}Environment:${RESET}  $ENV_NAME"
echo -e "  ${BOLD}Instance:${RESET}     $ORCHESTRATE_URL"
echo -e "  ${BOLD}Agent:${RESET}        $AGENT_NAME  [Live ✓]"
echo -e "  ${BOLD}KB:${RESET}           $KB_NAME (11 documents)"
echo ""
echo -e "  ${BOLD}Open the web demos:${RESET}"
echo -e "  ${CYAN}  python3 -m http.server 8080 --directory web${RESET}"
echo -e "  then open:"
echo -e "    ${CYAN}http://localhost:8080${RESET}                    ← Main demo"
echo -e "    ${CYAN}http://localhost:8080/embed-docs.html${RESET}    ← Embed documentation hub"
echo -e "    ${CYAN}http://localhost:8080/demo-unsecured.html${RESET}← Unsecured embed demo"
echo -e "    ${CYAN}http://localhost:8080/demo-secured.html${RESET}  ← Secured embed demo (JWT)"
echo ""
echo -e "  ${BOLD}For secured embed (JWT mode):${RESET}"
echo -e "  ${CYAN}  bash scripts/generate_rsa_keys.sh${RESET}       ← 1. Generate RSA key pair"
echo -e "  ${CYAN}  python scripts/jwt_server.py${RESET}             ← 2. Start JWT signing server"
echo -e "  Or include in one command:"
echo -e "  ${CYAN}  ./scripts/start.sh --start-jwt-server${RESET}"
echo ""
echo -e "  ${BOLD}Test via CLI:${RESET}"
echo -e "  ${CYAN}  $VENV_ORCHESTRATE chat ask --agent-name $AGENT_NAME${RESET}"
echo ""
echo -e "  ${BOLD}Example query:${RESET}  What is IBM Bob?"
echo ""
