#!/usr/bin/env python3
"""
jwt_server.py — JWT signing server for secured IBM wxO embedded chat

Serves two endpoints:
  GET  /                   → health check
  POST /api/token          → issue a signed JWT for a given user/session
  GET  /api/token          → issue anonymous JWT (no user context)

The browser-side secured embed calls /api/token to get a fresh JWT on each
page load and passes it to the wxO chat widget via the identityToken callback.
The JWT is signed with the RSA-2048 private key; wxO verifies it with the
matching public key you uploaded in Administration → Settings → Embed Security.

Usage:
  source venv/bin/activate
  python scripts/jwt_server.py

  # Or with custom port / key path:
  JWT_SERVER_PORT=3001 \
  EMBED_PRIVATE_KEY_FILE=keys/wxo_embed_private.pem \
  python scripts/jwt_server.py

Required environment variables (read from .env or shell):
  EMBED_PRIVATE_KEY_FILE   Path to RSA-2048 PEM private key
  IBM_CLOUD_API_KEY        IBM Cloud API key (for JWT subject claim, optional)

Optional:
  JWT_SERVER_PORT          HTTP port to listen on (default: 3001)
  JWT_EXPIRY_SECONDS       Token lifetime in seconds (default: 3600, max: 7100)
  JWT_AUDIENCE             audience claim (default: watsonx-orchestrate)
  ALLOWED_ORIGINS          Comma-separated CORS origins (default: http://localhost:8080)

Security notes:
  - This server MUST NOT run in a browser.  It is a backend service.
  - The private key is NEVER sent to the browser.
  - Tokens are short-lived (1 hour default) and signed per-request.
  - In production, add rate-limiting and user authentication before /api/token.
"""

from __future__ import annotations

import http.server
import json
import logging
import os
import pathlib
import sys
import time
import uuid
from urllib.parse import parse_qs, urlparse

# ── Dependency check ───────────────────────────────────────────────────────────
try:
    import jwt as pyjwt
except ImportError:
    print("ERROR: PyJWT not installed.  Run:  pip install PyJWT cryptography")
    sys.exit(1)

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
except ImportError:
    print("ERROR: cryptography not installed.  Run:  pip install cryptography")
    sys.exit(1)

# ── Load .env if present ───────────────────────────────────────────────────────
def _load_dotenv() -> None:
    env_path = pathlib.Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip()
            if k and k not in os.environ:
                os.environ[k] = v

_load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────
PORT            = int(os.environ.get("JWT_SERVER_PORT", "3001"))
EXPIRY_SECONDS  = min(int(os.environ.get("JWT_EXPIRY_SECONDS", "3600")), 7100)
AUDIENCE        = os.environ.get("JWT_AUDIENCE", "watsonx-orchestrate")
KEY_FILE        = os.environ.get("EMBED_PRIVATE_KEY_FILE", "keys/wxo_embed_private.pem")
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080"
).split(",") if o.strip()]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jwt_server")


# ── Key loader ─────────────────────────────────────────────────────────────────
def _load_private_key():
    """Load the RSA private key from disk.  Returns the PEM bytes."""
    key_path = pathlib.Path(KEY_FILE)
    if not key_path.is_absolute():
        key_path = pathlib.Path(__file__).parent.parent / key_path

    if not key_path.exists():
        log.error(
            "Private key not found at %s\n"
            "  Run:  bash scripts/generate_rsa_keys.sh\n"
            "  Then set EMBED_PRIVATE_KEY_FILE in .env",
            key_path,
        )
        sys.exit(1)

    pem = key_path.read_bytes()

    # Validate the key parses correctly
    try:
        serialization.load_pem_private_key(pem, password=None, backend=default_backend())
    except Exception as exc:
        log.error("Failed to parse private key %s: %s", key_path, exc)
        sys.exit(1)

    log.info("Loaded private key: %s", key_path)
    return pem


PRIVATE_KEY_PEM = _load_private_key()


# ── Token factory ──────────────────────────────────────────────────────────────
def create_jwt(
    user_id: str | None = None,
    user_name: str | None = None,
    extra_claims: dict | None = None,
) -> str:
    """
    Create and sign a JWT for the wxO embedded chat.

    The token payload follows the IBM watsonx Orchestrate specification:
      - iss: issuer (always "ibm_bob_assistant_demo")
      - sub: subject / user identifier
      - aud: audience (watsonx-orchestrate)
      - iat: issued-at timestamp
      - exp: expiry timestamp
      - jti: unique token ID (prevents replay)

    Additional claims (user_name, etc.) are passed through as context.
    """
    now = int(time.time())
    subject = user_id or f"anonymous-{uuid.uuid4().hex[:8]}"

    payload: dict = {
        "iss": "ibm_bob_assistant_demo",
        "sub": subject,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + EXPIRY_SECONDS,
        "jti": str(uuid.uuid4()),
    }

    if user_name:
        payload["name"] = user_name
    if extra_claims:
        payload.update(extra_claims)

    token = pyjwt.encode(payload, PRIVATE_KEY_PEM, algorithm="RS256")
    return token


# ── HTTP handler ───────────────────────────────────────────────────────────────
class JWTHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP handler exposing the /api/token endpoint."""

    def log_message(self, fmt, *args):  # suppress default access log
        pass

    # ── CORS helper ────────────────────────────────────────────────────────────
    def _set_cors_headers(self):
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS or "*" in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin or "*")
        else:
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGINS[0])
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Vary", "Origin")

    # ── OPTIONS (preflight) ────────────────────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ── GET ────────────────────────────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            self._health()
        elif path == "/api/token":
            # Anonymous token (no user context from query params)
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            user_id = (qs.get("userId") or [None])[0]
            user_name = (qs.get("name") or [None])[0]
            self._issue_token(user_id=user_id, user_name=user_name)
        else:
            self._not_found()

    # ── POST ───────────────────────────────────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/token":
            length = int(self.headers.get("Content-Length", "0"))
            body: dict = {}
            if length > 0:
                try:
                    body = json.loads(self.rfile.read(length))
                except (json.JSONDecodeError, ValueError):
                    body = {}

            self._issue_token(
                user_id=body.get("userId"),
                user_name=body.get("name"),
                extra_claims=body.get("claims"),
            )
        else:
            self._not_found()

    # ── Response helpers ───────────────────────────────────────────────────────
    def _json(self, status: int, data: dict):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _health(self):
        self._json(200, {
            "status": "ok",
            "service": "wxo-jwt-server",
            "expiry_seconds": EXPIRY_SECONDS,
            "allowed_origins": ALLOWED_ORIGINS,
        })
        log.info("GET /  → 200 health OK")

    def _issue_token(
        self,
        user_id: str | None = None,
        user_name: str | None = None,
        extra_claims: dict | None = None,
    ):
        try:
            token = create_jwt(user_id=user_id, user_name=user_name, extra_claims=extra_claims)
            self._json(200, {
                "token": token,
                "expires_in": EXPIRY_SECONDS,
                "token_type": "Bearer",
            })
            log.info(
                "%s /api/token → 200  sub=%s",
                self.command,
                user_id or "(anonymous)",
            )
        except Exception as exc:
            log.exception("Failed to sign JWT: %s", exc)
            self._json(500, {"error": "token_signing_failed", "detail": str(exc)})

    def _not_found(self):
        self._json(404, {"error": "not_found", "path": self.path})


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("wxO JWT signing server starting on http://localhost:%d", PORT)
    log.info("Allowed CORS origins: %s", ALLOWED_ORIGINS)
    log.info("Token expiry: %d seconds", EXPIRY_SECONDS)
    log.info("")
    log.info("Endpoints:")
    log.info("  GET  http://localhost:%d/           → health check", PORT)
    log.info("  GET  http://localhost:%d/api/token  → issue anonymous JWT", PORT)
    log.info("  POST http://localhost:%d/api/token  → issue JWT with user context", PORT)
    log.info("")
    log.info("Press Ctrl+C to stop")

    server = http.server.HTTPServer(("0.0.0.0", PORT), JWTHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down JWT server")
        server.server_close()
