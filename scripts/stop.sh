#!/usr/bin/env bash
# ==============================================================================
# stop.sh — Gracefully undeploy the IBM Bob Documentation Assistant
#
# Usage:
#   ./scripts/stop.sh [--keep-kb] [--keep-agent]
#
# What it does:
#   1. Loads .env and authenticates the orchestrate CLI
#   2. Stops the JWT signing server (if running)
#   3. Deletes the agent from watsonx Orchestrate
#   4. Deletes the knowledge base from watsonx Orchestrate
#   5. De-activates the orchestrate CLI session (removes credentials cache)
#
# Options:
#   --keep-kb      Keep the knowledge base (skip KB deletion)
#   --keep-agent   Keep the agent (skip agent deletion)
#
# Note: this does NOT delete local files. Run scripts/cleanup.sh to remove
#       the Python virtual environment and generated artefacts.
# ==============================================================================
set -euo pipefail

# ── Constants ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"
VENV_ORCHESTRATE="$PROJECT_ROOT/venv/bin/orchestrate"
KB_NAME="ibm_bob_docs"
AGENT_NAME="ibm_bob_assistant"

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
KEEP_KB=false
KEEP_AGENT=false
for arg in "$@"; do
  case "$arg" in
    --keep-kb)    KEEP_KB=true ;;
    --keep-agent) KEEP_AGENT=true ;;
    *) die "Unknown argument: $arg (valid: --keep-kb, --keep-agent)" ;;
  esac
done

# ── Step 1: Load .env ──────────────────────────────────────────────────────────
section "Step 1 — Loading environment variables"

[[ -f "$ENV_FILE" ]] || die ".env not found at $ENV_FILE"

set -a
while IFS='=' read -r key value; do
  [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
  key="${key%%[[:space:]]*}"
  value="${value%%[[:space:]]*}"
  [[ -n "$key" ]] && export "$key"="$value"
done < "$ENV_FILE"
set +a

[[ -n "${ORCHESTRATE_URL:-}" ]]    || die "ORCHESTRATE_URL is empty in .env"
[[ -n "${IBM_CLOUD_API_KEY:-}" ]]  || die "IBM_CLOUD_API_KEY is empty in .env"

ENV_NAME="${ORCHESTRATE_ENV_NAME:-wxo-ibm-bob}"
ok "Environment: $ENV_NAME"

[[ -x "$VENV_ORCHESTRATE" ]] || die "orchestrate CLI not found at $VENV_ORCHESTRATE"
ORC="$VENV_ORCHESTRATE"

# ── Step 2: Authenticate ───────────────────────────────────────────────────────
section "Step 2 — Authenticating"

if "$ORC" env list 2>/dev/null | cat | grep -q "$ENV_NAME"; then
  info "Activating environment '$ENV_NAME'…"
  "$ORC" env activate "$ENV_NAME" --api-key "$IBM_CLOUD_API_KEY" \
    || die "Authentication failed — check credentials in .env"
  ok "Authenticated"
else
  warn "Environment '$ENV_NAME' not registered — nothing to deactivate"
  exit 0
fi

# ── Step 2b: Stop JWT signing server (if running) ─────────────────────────────
section "Step 2b — Stopping JWT signing server"

JWT_PORT="${JWT_SERVER_PORT:-3001}"
JWT_PIDS=$(lsof -ti tcp:"$JWT_PORT" 2>/dev/null || true)
if [[ -n "$JWT_PIDS" ]]; then
  info "Stopping JWT server on port $JWT_PORT (PID(s): $JWT_PIDS)…"
  # shellcheck disable=SC2086
  kill $JWT_PIDS 2>/dev/null || true
  sleep 1
  # Confirm it's gone
  REMAINING=$(lsof -ti tcp:"$JWT_PORT" 2>/dev/null || true)
  if [[ -z "$REMAINING" ]]; then
    ok "JWT server stopped"
  else
    warn "JWT server may still be running on port $JWT_PORT — check manually"
  fi
else
  info "No JWT server found on port $JWT_PORT — nothing to stop"
fi

# ── Step 3: Delete agent ───────────────────────────────────────────────────────
section "Step 3 — Removing agent"

if [[ "$KEEP_AGENT" == "true" ]]; then
  info "--keep-agent: skipping agent deletion"
else
  if "$ORC" agents list 2>/dev/null | cat | grep -q "$AGENT_NAME"; then
    info "Deleting agent '$AGENT_NAME'…"
    "$ORC" agents delete -n "$AGENT_NAME" \
      || warn "Agent deletion returned a non-zero exit code — it may already be gone"
    ok "Agent '$AGENT_NAME' removed"
  else
    info "Agent '$AGENT_NAME' not found — nothing to remove"
  fi
fi

# ── Step 4: Delete knowledge base ──────────────────────────────────────────────
section "Step 4 — Removing knowledge base"

if [[ "$KEEP_KB" == "true" ]]; then
  info "--keep-kb: skipping KB deletion"
else
  if "$ORC" knowledge-bases list 2>/dev/null | cat | grep -q "$KB_NAME"; then
    info "Deleting knowledge base '$KB_NAME'…"
    "$ORC" knowledge-bases delete -n "$KB_NAME" \
      || warn "KB deletion returned a non-zero exit code — it may already be gone"
    ok "Knowledge base '$KB_NAME' removed"
  else
    info "Knowledge base '$KB_NAME' not found — nothing to remove"
  fi
fi

# ── Step 5: Deactivate session ─────────────────────────────────────────────────
section "Step 5 — Deactivating CLI session"

CREDS_FILE="$HOME/.cache/orchestrate/credentials.yaml"
if [[ -f "$CREDS_FILE" ]]; then
  rm -f "$CREDS_FILE"
  ok "Removed credentials cache ($CREDS_FILE)"
else
  info "No credentials cache found — already clean"
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗"
echo -e "║  IBM Bob Documentation Assistant — stopped successfully      ║"
echo -e "╚══════════════════════════════════════════════════════════════╝${RESET}"
echo ""
[[ "$KEEP_AGENT" == "false" ]] && echo -e "  • Agent '$AGENT_NAME'         ${RED}removed${RESET}"   || echo -e "  • Agent '$AGENT_NAME'         ${YELLOW}kept${RESET}"
[[ "$KEEP_KB"    == "false" ]] && echo -e "  • Knowledge base '$KB_NAME'   ${RED}removed${RESET}" || echo -e "  • Knowledge base '$KB_NAME'   ${YELLOW}kept${RESET}"
echo -e "  • CLI session                  ${GREEN}deactivated${RESET}"
echo ""
echo -e "  To redeploy: ${CYAN}./scripts/start.sh${RESET}"
echo ""
