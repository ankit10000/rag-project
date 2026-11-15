"""Gemini provider configuration (Batch 1).

Cheap to import: no SDK import, no client, no API-key check. Both
services/llm_service.py (the provider implementation) and the API's
/providers endpoint read their settings from here, so there is exactly one
definition of the defaults and of the environment precedence:

    process environment  >  .env  >  code default

API key VALUES are never exposed by this module, only whether one is set.
"""

import os

from dotenv import dotenv_values, load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, ".env")

load_dotenv(ENV_FILE, override=False)

PROVIDER_NAME = "gemini"

DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_FALLBACK_MODELS = "gemini-3.1-flash-lite,gemini-2.5-flash"


def parse_model_list(value: str) -> list[str]:
    return [name.strip() for name in (value or "").split(",") if name.strip()]


# Resolved once at import, exactly as llm_service always did.
MODEL_NAME = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

# Tried in order when the current model is out of quota (429), not found (404)
# or temporarily failing (5xx). Override with GEMINI_FALLBACK_MODELS="a,b".
FALLBACK_MODELS = parse_model_list(os.getenv("GEMINI_FALLBACK_MODELS", DEFAULT_FALLBACK_MODELS))


def api_key_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def setting_source(name: str) -> str:
    """Where a setting's effective value comes from (never returns the value)."""
    if name not in os.environ:
        return "code default"
    file_value = dotenv_values(ENV_FILE).get(name) if os.path.isfile(ENV_FILE) else None
    return ".env" if file_value is not None and file_value == os.environ[name] else "process environment"
