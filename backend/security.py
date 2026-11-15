"""Phase 7 — local single-user API token authentication.

Design
  * One random token per installation: ``secrets.token_urlsafe(32)`` (256 bits).
  * Token source, in order:
      1. ``RAG_API_TOKEN`` environment variable (must be >= 32 characters), else
      2. a token file outside the repository:
           Windows : %LOCALAPPDATA%\\rag-project\\api_token
           other   : ~/.config/rag-project/api_token   (dir 0700, file 0600)
         (override the path with ``RAG_API_TOKEN_FILE``). It is created on first
         start, never inside the project directory (so it cannot be committed).
  * The server keeps only the SHA-256 DIGEST in memory; requests are checked
    with ``hmac.compare_digest`` on digests (constant time).
  * Clients send ``Authorization: Bearer <token>``. Missing and invalid tokens
    get the same 401 response. The token is never logged, returned or echoed.
  * Rotation: ``run_api.py --rotate-token`` writes a new token file (server
    restart required; old token stops working).
  * Fail closed: if no token can be loaded/created the server refuses to start,
    and if the digest is somehow absent every protected request gets 503.

Plaintext-on-disk tradeoff: the token file is readable by the local user
account (like an SSH key). An OS credential store (e.g. ``keyring``) is not
installed and was not added; see the Phase 7 document.
"""

import hashlib
import hmac
import os
import secrets
import sys

from fastapi import Request

from backend.errors import ApiError

MIN_TOKEN_LENGTH = 32


def default_token_path() -> str:
    override = os.environ.get("RAG_API_TOKEN_FILE")
    if override:
        return os.path.abspath(override)
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, "rag-project", "api_token")
    return os.path.join(os.path.expanduser("~"), ".config", "rag-project", "api_token")


def _write_token_file(path: str, token: str) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    if not sys.platform.startswith("win"):
        os.chmod(directory, 0o700)
    tmp = path + ".tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(tmp, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token + "\n")
    os.replace(tmp, path)
    if not sys.platform.startswith("win"):
        os.chmod(path, 0o600)


def rotate_token(path: str | None = None) -> str:
    """Create a NEW token file; returns the file path (never the token)."""
    path = path or default_token_path()
    _write_token_file(path, secrets.token_urlsafe(32))
    return path


def load_token_digest() -> tuple[bytes, str]:
    """Return (sha256 digest of the active token, description of its source).

    Creates the token file on first use. Raises RuntimeError if no valid token
    can be obtained (fail closed)."""
    env_token = os.environ.get("RAG_API_TOKEN")
    if env_token is not None:
        env_token = env_token.strip()
        if len(env_token) < MIN_TOKEN_LENGTH:
            raise RuntimeError("RAG_API_TOKEN is set but shorter than 32 characters")
        return hashlib.sha256(env_token.encode("utf-8")).digest(), "environment variable RAG_API_TOKEN"

    path = default_token_path()
    if not os.path.exists(path):
        _write_token_file(path, secrets.token_urlsafe(32))
    with open(path, encoding="utf-8") as fh:
        token = fh.read().strip()
    if len(token) < MIN_TOKEN_LENGTH:
        raise RuntimeError("API token file is empty or too short; rotate it with run_api.py --rotate-token")
    return hashlib.sha256(token.encode("utf-8")).digest(), "token file in the user profile"


def require_token(request: Request) -> None:
    """FastAPI dependency protecting every non-liveness endpoint."""
    expected = getattr(request.app.state, "token_digest", None)
    if not expected:
        raise ApiError(503, "auth_unavailable", "authentication is not initialized")

    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    presented = presented.strip()
    if scheme.lower() != "bearer" or not presented or len(presented) > 512:
        raise ApiError(401, "unauthorized", "missing or invalid API token")

    digest = hashlib.sha256(presented.encode("utf-8")).digest()
    if not hmac.compare_digest(digest, expected):
        raise ApiError(401, "unauthorized", "missing or invalid API token")
