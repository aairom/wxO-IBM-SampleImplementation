#!/usr/bin/env bash
# =============================================================================
# get_webchat_embed.sh
#
# Generate the watsonx Orchestrate web-chat embed snippet for
# ibm_bob_assistant and write it into web/webchat-config.js.
#
# Usage:
#   bash scripts/get_webchat_embed.sh
#
# Prerequisites:
#   - venv/ exists and ibm-watsonx-orchestrate is installed
#   - .env contains IBM_CLOUD_API_KEY
#   - ibm_bob_assistant is deployed (Live state)
#
# How it works:
#   1. Loads .env, activates the wxO environment
#   2. Delegates to a self-contained Python helper that:
#      a. Calls `orchestrate channels webchat embed` via subprocess (no pager hang)
#      b. Parses orchestrationID, agentId, agentEnvironmentId, hostURL, crn
#      c. Writes filled-in values into web/webchat-config.js
#   3. Reports the result
#
# The generated embed snippet structure (from ADK):
#   window.wxOConfiguration = {
#     orchestrationID: "<value>",
#     hostURL: "<value>",
#     rootElementID: "wxo-chat-root",
#     showLauncher: true,
#     crn: "<value>",
#     deploymentPlatform: "ibmcloud",
#     chatOptions: {
#       agentId: "<value>",
#       agentEnvironmentId: "<value>"
#     }
#   };
# =============================================================================

# ---------------------------------------------------------------------------
# Strict mode — but NOT set -e so the Python call can fail gracefully
# ---------------------------------------------------------------------------
set -uo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
VENV_ACTIVATE="${PROJECT_ROOT}/venv/bin/activate"

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
die()     { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Step 0 — pre-flight checks
# ---------------------------------------------------------------------------
info "Checking prerequisites..."

[[ -f "${VENV_ACTIVATE}" ]] || die "venv not found. Run: uv venv venv && uv pip install -r requirements.txt"
[[ -f "${ENV_FILE}" ]] || die ".env file not found. Copy .env.example → .env and fill in credentials."

# shellcheck source=/dev/null
source "${VENV_ACTIVATE}"
command -v orchestrate &>/dev/null || die "'orchestrate' CLI not found in venv."

success "Prerequisites OK"

# ---------------------------------------------------------------------------
# Step 1 — load .env
# ---------------------------------------------------------------------------
info "Loading .env..."
while IFS='=' read -r key value; do
  [[ "${key}" =~ ^[[:space:]]*# ]] && continue
  [[ -z "${key}" ]] && continue
  key="${key// /}"
  value="${value%\"}" ; value="${value#\"}"
  value="${value%\'}" ; value="${value#\'}"
  export "${key}=${value}" 2>/dev/null || true
done < "${ENV_FILE}"

ENV_NAME="${ORCHESTRATE_ENV_NAME:-aam-wxo-be}"
# Support both IBM_CLOUD_API_KEY and legacy ORCHESTRATE_API_KEY names
API_KEY="${IBM_CLOUD_API_KEY:-${ORCHESTRATE_API_KEY:-}}"

# ---------------------------------------------------------------------------
# Step 2 — activate wxO environment
# ---------------------------------------------------------------------------
info "Activating wxO environment '${ENV_NAME}'..."

if [[ -n "${API_KEY}" ]]; then
  echo "${API_KEY}" | orchestrate env activate "${ENV_NAME}" \
    2>&1 | grep -v "Password input\|echoed" || true
  success "Environment activated"
else
  warn "IBM_CLOUD_API_KEY not set in .env — skipping re-activation."
  warn "If the environment is already active this will still work."
fi

ACTIVE=$(orchestrate env list 2>/dev/null | grep "(active)" | awk '{print $1}' || echo "")
[[ -z "${ACTIVE}" ]] && die "No active wxO environment. Set IBM_CLOUD_API_KEY in .env and re-run."
info "Active environment: ${ACTIVE}"

# ---------------------------------------------------------------------------
# Step 3 — delegate ALL remaining work to Python
#   Python subprocess avoids the bash pager-hang issue with `orchestrate | cat`
#   under zsh set -euo pipefail. This is the only reliable approach on macOS.
# ---------------------------------------------------------------------------
info "Generating embed snippet and writing web/webchat-config.js..."

python3 "${SCRIPT_DIR}/_generate_webchat_config.py" \
  --project-root "${PROJECT_ROOT}" \
  --agent-name "ibm_bob_assistant" \
  --env "live" \
  ${API_KEY:+--api-key "${API_KEY}"}

EXIT_CODE=$?

if [[ ${EXIT_CODE} -ne 0 ]]; then
  die "Embed snippet generation failed. See output above."
fi

# ---------------------------------------------------------------------------
# Step 4 — summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}✅  Web-chat embed snippet injected successfully!${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo "  Demo page:   web/index.html"
echo "  Config file: web/webchat-config.js"
echo ""
echo "  To open the demo locally:"
echo -e "  ${CYAN}open web/index.html${RESET}   (macOS)"
echo -e "  ${CYAN}python3 -m http.server 8080 --directory web${RESET}"
echo -e "  then open  ${CYAN}http://localhost:8080${RESET}"
echo ""
