"""Provider/model configuration (read-only).

The repository implements ONE provider today: Gemini (services/llm_service.py).
Its model settings are resolved WITHOUT importing llm_service (importing it
creates an SDK client and requires the API key): defaults are read statically
from llm_service.py with ``ast`` and overridden by the process environment or
.env, the same precedence the application uses. API key VALUES are never read
into responses — only whether a key is configured. Writing provider settings
or credentials is deferred to Phase 7 (secure credential storage).
"""

import ast
import os

from fastapi import APIRouter

from backend.config import ROOT
from backend.schemas import ProviderInfo, ProvidersResponse

router = APIRouter(prefix="/providers", tags=["providers"])

_LLM_SERVICE = os.path.join(ROOT, "services", "llm_service.py")


def _getenv_defaults(path: str) -> dict:
    """Static map NAME -> default for os.getenv("NAME", "default") calls."""
    defaults = {}
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "getenv"
                and len(node.args) == 2 and all(isinstance(a, ast.Constant) for a in node.args)):
            defaults[node.args[0].value] = node.args[1].value
    return defaults


def _resolve(name: str, defaults: dict, file_values: dict):
    if name in os.environ:
        return os.environ[name], "process environment"
    if name in file_values:
        return file_values[name], ".env"
    return defaults.get(name), "code default"


@router.get("", response_model=ProvidersResponse)
def list_providers():
    from dotenv import dotenv_values

    file_values = dotenv_values(os.path.join(ROOT, ".env"))
    defaults = _getenv_defaults(_LLM_SERVICE)
    primary, primary_src = _resolve("GEMINI_MODEL", defaults, file_values)
    fallbacks, fallback_src = _resolve("GEMINI_FALLBACK_MODELS", defaults, file_values)
    key_configured = bool(os.environ.get("GEMINI_API_KEY") or file_values.get("GEMINI_API_KEY"))
    del file_values

    return ProvidersResponse(
        providers=[ProviderInfo(
            name="gemini",
            implemented=True,
            api_key_configured=key_configured,
            primary_model=primary,
            fallback_models=[m.strip() for m in (fallbacks or "").split(",") if m.strip()],
            settings_source={"GEMINI_MODEL": primary_src, "GEMINI_FALLBACK_MODELS": fallback_src},
        )],
        write_support=False,
        note=("Only the Gemini provider is implemented in this repository. Provider/model changes and "
              "credential management are not exposed (deferred to Phase 7); fallback policy is unchanged."),
    )
