"""Backend settings (local, single-user). Only cheap imports here.

Batch 1: the project .env is loaded HERE, before any setting below is read, so
RAG_API_* values in .env take effect. Real process environment variables still
win (override=False), the same precedence the services use.

Environment variable classes (see .env.example):
  required          DATABASE_URL (every data endpoint and the CLI)
  provider-specific GEMINI_API_KEY (chat / LLM calls only), GEMINI_MODEL,
                    GEMINI_FALLBACK_MODELS
  optional          RAG_API_* (this module, backend/security.py), retrieval and
                    ingestion knobs (services/retrieval_config.py), RAG_PERF_METRICS
  development-only  EVAL_*, DATABASE_URL_BASE, TEST_BASE_URL, TESTSAFE_BLOCK_NETWORK
"""

import os

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(ROOT, ".env"), override=False)

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
CORS_METHODS = ["GET", "POST", "DELETE"]
CORS_HEADERS = ["Authorization", "Content-Type", "X-Request-ID"]

# Request body limits (bytes). Uploads: the PDF limit plus multipart overhead.
MAX_JSON_BODY_BYTES = 1 * 1024 * 1024
MULTIPART_OVERHEAD_BYTES = 1 * 1024 * 1024

# Interactive OpenAPI docs (schema only, no data). Disable with RAG_API_DOCS=0.
_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")
_DOCS_RAW = os.environ.get("RAG_API_DOCS", "1").strip().lower()
DOCS_ENABLED = _DOCS_RAW not in _FALSE


def config_problems() -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for the API configuration.

    Errors make startup fail with a clear message; warnings are logged. Only
    variable NAMES appear in messages, never values of secrets.
    """
    errors, warnings = [], []
    if os.getenv('LOCAL_V1_PROFILE') == '1':
        from services.request_budget import configured_timeout
        from services.local_release_profile import require_embedding_model
        try:
            configured_timeout()
            from services import retrieval_config as local_cfg
            require_embedding_model(local_cfg.EMBEDDING_MODEL)
        except ValueError as exc:
            errors.append(str(exc))
    if _DOCS_RAW not in _TRUE + _FALSE:
        errors.append(f"RAG_API_DOCS must be one of {', '.join(_TRUE + _FALSE)}")
    try:
        from services import retrieval_config  # noqa: F401  (parses numeric knobs)
    except ValueError as error:
        errors.append(f"invalid retrieval/ingestion setting in the environment or .env: {error}")
    if not os.environ.get("DATABASE_URL"):
        warnings.append("DATABASE_URL is not set: every data endpoint will fail")
    if not os.environ.get("GEMINI_API_KEY"):
        warnings.append("GEMINI_API_KEY is not set: /chat will fail until it is configured")
    return errors, warnings
