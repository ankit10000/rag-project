"""Health and system status. Never connects to the database, never loads a
model, never calls a provider, never returns secrets or connection strings."""

import os
import sys

from fastapi import APIRouter

from backend import API_VERSION, APP_VERSION
from backend.config import ROOT
from backend.schemas import ComponentStatus, HealthResponse, SystemStatusResponse

# Public liveness (no auth, minimal: no versions, no component details).
public_router = APIRouter(tags=["health"])
# Detailed status requires the API token (registered with require_token in app.py).
router = APIRouter(tags=["health"])


def _env_has(name: str) -> bool:
    if os.environ.get(name):
        return True
    try:
        from dotenv import dotenv_values
        return bool(dotenv_values(os.path.join(ROOT, ".env")).get(name))
    except Exception:
        return False


@public_router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@router.get("/health/status", response_model=SystemStatusResponse)
def system_status():
    from services import retrieval_config as cfg

    components = [
        ComponentStatus(
            name="database",
            status="configured" if _env_has("DATABASE_URL") else "unavailable",
            detail="connection string present; connectivity not checked" if _env_has("DATABASE_URL")
            else "DATABASE_URL is not set",
        ),
        ComponentStatus(
            name="embedding_model",
            status="initialized" if "services.embedding_service" in sys.modules else "configured",
            detail=f"model {cfg.EMBEDDING_MODEL}, dim {cfg.EMBEDDING_DIM}; loaded on first use",
        ),
    ]
    reranker = sys.modules.get("services.reranker_service")
    reranker_loaded = bool(reranker and getattr(reranker, "_model", None) is not None)
    components.append(ComponentStatus(
        name="reranker",
        status="initialized" if reranker_loaded else ("configured" if cfg.RERANK_ENABLED else "unavailable"),
        detail=f"model {cfg.RERANK_MODEL}; enabled={cfg.RERANK_ENABLED}; loaded lazily",
    ))
    components.append(ComponentStatus(
        name="llm_provider",
        status="configured" if _env_has("GEMINI_API_KEY") else "unavailable",
        detail="API key presence only; credentials are never validated or returned here",
    ))
    components.append(ComponentStatus(name="provider_connectivity", status="not_checked",
                                      detail="no live provider call is made by status endpoints"))
    return SystemStatusResponse(app_version=APP_VERSION, api_version=API_VERSION, components=components)
