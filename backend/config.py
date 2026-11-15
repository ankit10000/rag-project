"""Backend settings (local, single-user). Only cheap imports here."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

API_PREFIX = "/api/v1"
DEFAULT_HOST = "127.0.0.1"          # loopback only by default
DEFAULT_PORT = 8765
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Uploaded PDFs are written here (created on first upload, never elsewhere).
UPLOAD_DIR = os.path.join(ROOT, "data", "uploads")
MAX_FILENAME_LENGTH = 120

# Bounded listing sizes
MAX_HISTORY_MESSAGES = 200
MAX_MEMORIES_LISTED = 200
MAX_CONVERSATIONS_LISTED = 200

# --- Phase 7 request security --------------------------------------------------
# Host header allow-list (DNS-rebinding protection). Extra names only by explicit
# opt-in, e.g. RAG_API_ALLOWED_HOSTS="mypc.local" together with --allow-non-loopback.
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "::1", "[::1]"] + [
    h.strip() for h in os.environ.get("RAG_API_ALLOWED_HOSTS", "").split(",") if h.strip()
]

# CORS: no cross-origin access unless origins are listed explicitly, e.g.
# RAG_API_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173".
# "*" and "null" are rejected. Credentials (cookies) are never allowed: auth is a bearer token.
CORS_ORIGINS = [o.strip() for o in os.environ.get("RAG_API_CORS_ORIGINS", "").split(",") if o.strip()]
CORS_METHODS = ["GET", "POST"]
CORS_HEADERS = ["Authorization", "Content-Type", "X-Request-ID"]

# Request body limits (bytes). Uploads: the PDF limit plus multipart overhead.
MAX_JSON_BODY_BYTES = 1 * 1024 * 1024
MULTIPART_OVERHEAD_BYTES = 1 * 1024 * 1024

# Interactive OpenAPI docs (schema only, no data). Disable with RAG_API_DOCS=0.
DOCS_ENABLED = os.environ.get("RAG_API_DOCS", "1").strip().lower() not in ("0", "false", "no", "off")
