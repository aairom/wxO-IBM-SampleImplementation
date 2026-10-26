#!/usr/bin/env bash
# =============================================================================
# serve.sh — Launch local HTTP servers for the wxO-IBM project
# =============================================================================
# Usage:
#   ./scripts/serve.sh --web      Serve main demo pages on port 8080
#   ./scripts/serve.sh --deck     Serve HTML slide deck on port 8085
#   ./scripts/serve.sh -h|--help  Show this help message
#
# Press Ctrl+C to stop the server.
# =============================================================================

set -euo pipefail

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Resolve project root (one level up from this script) ──────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Help ───────────────────────────────────────────────────────────────────────
usage() {
  echo ""
  echo -e "${BOLD}wxO-IBM local server${RESET}"
  echo ""
  echo "  Usage: $(basename "$0") [--web | --deck] [-h | --help]"
  echo ""
  echo "  Options:"
  echo "    --web     Serve the main demo pages (web/) on http://localhost:8080"
  echo "    --deck    Serve the HTML slide deck (web/deck/) on http://localhost:8085"
  echo "    -h, --help  Show this help message"
  echo ""
  echo "  Examples:"
  echo "    ./scripts/serve.sh --web"
  echo "    ./scripts/serve.sh --deck"
  echo ""
}

# ── Argument parsing ───────────────────────────────────────────────────────────
MODE=""
case "${1:-}" in
  --web)    MODE="web" ;;
  --deck)   MODE="deck" ;;
  -h|--help) usage; exit 0 ;;
  *)
    echo -e "${RED}Error:${RESET} Unknown or missing argument '${1:-}'."
    usage
    exit 1
    ;;
esac

# ── Launch ─────────────────────────────────────────────────────────────────────
if [[ "$MODE" == "web" ]]; then
  WEB_DIR="${PROJECT_ROOT}/web"
  PORT=8080
  echo ""
  echo -e "${GREEN}▶ Starting main demo server...${RESET}"
  echo -e "  Directory : ${CYAN}${WEB_DIR}${RESET}"
  echo -e "  URL       : ${CYAN}${BOLD}http://localhost:${PORT}${RESET}"
  echo ""
  echo -e "  Pages available:"
  echo -e "    http://localhost:${PORT}/                    Main demo"
  echo -e "    http://localhost:${PORT}/demo-unsecured.html Unsecured embed"
  echo -e "    http://localhost:${PORT}/demo-secured.html   Secured embed + JWT inspector"
  echo -e "    http://localhost:${PORT}/embed-docs.html     Documentation hub"
  echo ""
  echo -e "  Press ${BOLD}Ctrl+C${RESET} to stop."
  echo ""
  python3 -m http.server "$PORT" --directory "$WEB_DIR"

elif [[ "$MODE" == "deck" ]]; then
  DECK_DIR="${PROJECT_ROOT}/web/deck"
  PORT=8085
  echo ""
  echo -e "${GREEN}▶ Starting HTML slide deck server...${RESET}"
  echo -e "  Directory : ${CYAN}${DECK_DIR}${RESET}"
  echo -e "  URL       : ${CYAN}${BOLD}http://localhost:${PORT}${RESET}"
  echo ""
  echo -e "  Slides available at:"
  echo -e "    http://localhost:${PORT}/                    Deck index"
  echo -e "    http://localhost:${PORT}/slides/slide-01.html  Slide 1"
  echo ""
  echo -e "  Press ${BOLD}Ctrl+C${RESET} to stop."
  echo ""
  python3 -m http.server "$PORT" --bind 0.0.0.0 --directory "$DECK_DIR"
fi
