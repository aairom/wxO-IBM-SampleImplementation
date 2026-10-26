#!/usr/bin/env bash
# ==============================================================================
# generate_rsa_keys.sh — Generate RSA key pair for wxO secured embed chat
#
# Usage:
#   ./scripts/generate_rsa_keys.sh [--output-dir <dir>]
#
# Outputs (written to keys/ by default, gitignored):
#   keys/wxo_embed_private.pem  — Private key: kept on your server ONLY
#   keys/wxo_embed_public.pem   — Public key:  upload to wxO tenant UI
#
# What to do after running this:
#   1. Open: https://eu-de.watson-orchestrate.cloud.ibm.com
#   2. Go to: Administration → Settings → Embed Security
#   3. Toggle Security: ON
#   4. Paste the contents of keys/wxo_embed_public.pem into the Public key field
#   5. Click Save
#   6. Set EMBED_PRIVATE_KEY_FILE=keys/wxo_embed_private.pem in your .env
#
# Security notes:
#   - NEVER commit keys/ to git (already in .gitignore)
#   - NEVER expose the private key in client-side code
#   - The JWT server (scripts/jwt_server.py) reads the private key server-side
#     and signs tokens; the browser only ever receives a short-lived JWT
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_ROOT/keys"

# ── Parse arguments ────────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --output-dir=*) OUTPUT_DIR="${arg#*=}" ;;
    --output-dir)   shift; OUTPUT_DIR="${1:-$OUTPUT_DIR}" ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}[OK]${RESET}    $*"; }
info() { echo -e "${CYAN}[INFO]${RESET}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${RESET}  $*"; }

# ── Pre-flight checks ──────────────────────────────────────────────────────────
if ! command -v openssl &>/dev/null; then
  echo "ERROR: openssl not found. Install it with:"
  echo "  macOS:  brew install openssl"
  echo "  Ubuntu: sudo apt-get install openssl"
  exit 1
fi

# ── Create output directory ────────────────────────────────────────────────────
mkdir -p "$OUTPUT_DIR"

PRIVATE_KEY="$OUTPUT_DIR/wxo_embed_private.pem"
PUBLIC_KEY="$OUTPUT_DIR/wxo_embed_public.pem"

# ── Check for existing keys ────────────────────────────────────────────────────
# When stdin is not a terminal (e.g. called from start.sh) skip the prompt and
# keep the existing keys to avoid hanging the parent script.
if [[ -f "$PRIVATE_KEY" || -f "$PUBLIC_KEY" ]]; then
  warn "Key files already exist:"
  [[ -f "$PRIVATE_KEY" ]] && warn "  $PRIVATE_KEY"
  [[ -f "$PUBLIC_KEY" ]]  && warn "  $PUBLIC_KEY"
  if [[ ! -t 0 ]]; then
    info "Non-interactive mode — keeping existing keys."
    exit 0
  fi
  echo ""
  read -r -p "Overwrite? This will invalidate your existing wxO tenant configuration. [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
fi

# ── Generate RSA-2048 private key ──────────────────────────────────────────────
info "Generating RSA-2048 private key…"
openssl genrsa -out "$PRIVATE_KEY" 2048 2>/dev/null
chmod 600 "$PRIVATE_KEY"
ok "Private key → $PRIVATE_KEY"

# ── Extract public key ─────────────────────────────────────────────────────────
info "Extracting public key…"
openssl rsa -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY" 2>/dev/null
chmod 644 "$PUBLIC_KEY"
ok "Public key  → $PUBLIC_KEY"

# ── Verify the pair ────────────────────────────────────────────────────────────
info "Verifying key pair…"
MODULUS_PRIV=$(openssl rsa -in "$PRIVATE_KEY" -noout -modulus 2>/dev/null | md5)
MODULUS_PUB=$(openssl rsa -in "$PUBLIC_KEY" -pubin -noout -modulus 2>/dev/null | md5)
if [[ "$MODULUS_PRIV" == "$MODULUS_PUB" ]]; then
  ok "Key pair verified — moduli match"
else
  echo "ERROR: Key pair verification failed — moduli do not match!"
  exit 1
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗"
echo -e "║  RSA key pair generated successfully                         ║"
echo -e "╚══════════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${BOLD}Private key:${RESET} $PRIVATE_KEY"
echo -e "  ${BOLD}Public key: ${RESET} $PUBLIC_KEY"
echo ""
echo -e "  ${BOLD}Next steps:${RESET}"
echo -e "  1. ${CYAN}Add to .env:${RESET}"
echo -e "       EMBED_PRIVATE_KEY_FILE=keys/wxo_embed_private.pem"
echo ""
echo -e "  2. ${CYAN}Upload public key to wxO portal:${RESET}"
echo -e "       https://eu-de.watson-orchestrate.cloud.ibm.com"
echo -e "       → Administration → Settings → Embed Security"
echo -e "       → Toggle Security: ON"
echo -e "       → Paste contents of keys/wxo_embed_public.pem"
echo ""
echo -e "  3. ${CYAN}Start the JWT signing server:${RESET}"
echo -e "       source venv/bin/activate"
echo -e "       python scripts/jwt_server.py"
echo ""
echo -e "  ${YELLOW}⚠  Never commit keys/ to git — it is already in .gitignore${RESET}"
echo ""

# ── Print the public key for easy copy-paste ──────────────────────────────────
echo -e "${BOLD}Public key (copy-paste into wxO UI):${RESET}"
echo "──────────────────────────────────────────────────────────────"
cat "$PUBLIC_KEY"
echo "──────────────────────────────────────────────────────────────"
