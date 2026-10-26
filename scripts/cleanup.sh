#!/usr/bin/env bash
# ==============================================================================
# cleanup.sh — Remove local artefacts for the IBM Bob Documentation Assistant
#
# Usage:
#   ./scripts/cleanup.sh [--all]
#
# What it does:
#   1. Removes the Python virtual environment (venv/)
#   2. Removes Python __pycache__ directories
#   3. Removes *.pyc / *.pyo compiled byte-code files
#   4. (--all) Also removes the generated .env file and knowledge-bases/docs/*.md
#      duplicates (the .txt files used by the KB are kept)
#
# Options:
#   --all   Full clean: also remove .env and redundant .md doc duplicates
#
# WARNING: --all will remove your .env credentials. You will need to re-create it
#          from .env.example before running start.sh again.
# ==============================================================================
set -euo pipefail

# ── Constants ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
section() { echo -e "\n${BOLD}━━━ $* ${RESET}"; }

# ── Parse arguments ────────────────────────────────────────────────────────────
FULL_CLEAN=false
for arg in "$@"; do
  case "$arg" in
    --all) FULL_CLEAN=true ;;
    *) echo -e "${RED}[ERROR]${RESET} Unknown argument: $arg (valid: --all)" >&2; exit 1 ;;
  esac
done

echo ""
echo -e "${BOLD}IBM Bob Documentation Assistant — Cleanup${RESET}"
echo ""

# ── Step 1: Remove virtual environment ────────────────────────────────────────
section "Step 1 — Removing Python virtual environment"

VENV_DIR="$PROJECT_ROOT/venv"
if [[ -d "$VENV_DIR" ]]; then
  rm -rf "$VENV_DIR"
  ok "Removed $VENV_DIR"
else
  info "venv/ not found — already clean"
fi

DOTVENV_DIR="$PROJECT_ROOT/.venv"
if [[ -d "$DOTVENV_DIR" ]]; then
  rm -rf "$DOTVENV_DIR"
  ok "Removed $DOTVENV_DIR"
fi

# ── Step 2: Remove Python byte-code caches ───────────────────────────────────
section "Step 2 — Removing Python byte-code artefacts"

CACHE_COUNT=0
while IFS= read -r -d '' dir; do
  rm -rf "$dir"
  (( CACHE_COUNT++ )) || true
done < <(find "$PROJECT_ROOT" -type d -name "__pycache__" -not -path "*/venv/*" -not -path "*/.venv/*" -print0 2>/dev/null)

PYC_COUNT=0
while IFS= read -r -d '' f; do
  rm -f "$f"
  (( PYC_COUNT++ )) || true
done < <(find "$PROJECT_ROOT" -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.pyd" \) -not -path "*/venv/*" -not -path "*/.venv/*" -print0 2>/dev/null)

if (( CACHE_COUNT + PYC_COUNT > 0 )); then
  ok "Removed $CACHE_COUNT __pycache__ directories and $PYC_COUNT compiled .py* files"
else
  info "No byte-code caches found — already clean"
fi

# ── Step 3: Remove orchestrate credentials cache ──────────────────────────────
section "Step 3 — Removing orchestrate CLI credentials cache"

CREDS_FILE="$HOME/.cache/orchestrate/credentials.yaml"
if [[ -f "$CREDS_FILE" ]]; then
  rm -f "$CREDS_FILE"
  ok "Removed $CREDS_FILE"
else
  info "No credentials cache found — already clean"
fi

# ── Step 4 (--all only): Remove .env and redundant .md doc duplicates ─────────
if [[ "$FULL_CLEAN" == "true" ]]; then
  section "Step 4 — Full clean: removing .env and .md doc duplicates"

  ENV_FILE="$PROJECT_ROOT/.env"
  if [[ -f "$ENV_FILE" ]]; then
    rm -f "$ENV_FILE"
    warn "Removed $ENV_FILE — you will need to recreate it from .env.example before next start"
  else
    info ".env not found — already clean"
  fi

  MD_COUNT=0
  while IFS= read -r -d '' f; do
    rm -f "$f"
    (( MD_COUNT++ )) || true
  done < <(find "$PROJECT_ROOT/knowledge-bases/docs" -type f -name "*.md" -print0 2>/dev/null)

  if (( MD_COUNT > 0 )); then
    ok "Removed $MD_COUNT redundant .md doc files (the .txt files used by the KB are preserved)"
  else
    info "No .md doc duplicates found"
  fi
else
  info "Skipping .env and .md doc cleanup (pass --all to include these)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗"
echo -e "║  IBM Bob Documentation Assistant — cleanup complete          ║"
echo -e "╚══════════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  Cleaned:"
echo -e "    • Python virtual environment (venv/)"
echo -e "    • Python __pycache__ and .pyc files"
echo -e "    • orchestrate CLI credentials cache"
[[ "$FULL_CLEAN" == "true" ]] && {
  echo -e "    • .env (credentials removed)"
  echo -e "    • knowledge-bases/docs/*.md (redundant duplicates)"
}
echo ""
echo -e "  To reinstall dependencies:"
echo -e "  ${CYAN}  uv venv venv && source venv/bin/activate && uv pip install -r requirements.txt${RESET}"
[[ "$FULL_CLEAN" == "true" ]] && echo -e "  Then: ${CYAN}cp .env.example .env${RESET}  (and fill in your credentials)"
echo ""
