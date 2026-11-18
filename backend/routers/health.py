"""Public liveness, private status and authenticated database readiness.

Only /health/ready connects to PostgreSQL. No endpoint loads a model, calls a
provider or returns credentials/connection strings.
"""

import os
import sys

from fastapi import APIRouter

from backend import API_VERSION, APP_VERSION
from backend.config import ROOT
from backend.schemas import ComponentStatus, HealthResponse, SystemStatusResponse
from backend.errors import ApiError

# Public liveness (no auth, minimal: no versions, no component details).
public_router = APIRouter(tags=["health"])
# Detailed status requires the API token (registered with require_token in app.py).
router = APIRouter(tags=["health"])


@router.get('/health/ready')
def readiness():
    """Authenticated actual DB connectivity; never calls a model/provider."""
    from services.database import get_connection
    from services.request_budget import check_deadline, RequestDeadlineExceeded
    try:
        check_deadline()
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT 1')
                if cursor.fetchone() != (1,):
                    raise ApiError(503, 'database_unavailable', 'database is unavailable')
        check_deadline()
    except RequestDeadlineExceeded:
        raise
    except Exception:
        raise ApiError(503, 'database_unavailable', 'database is unavailable') from None
    return {'status': 'ready', 'database': 'available'}


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

    embedding = sys.modules.get("services.embedding_service")
    embedding_loaded = bool(embedding and getattr(embedding, "_model", None) is not None)
    components = [
        ComponentStatus(
            name="database",
            status="configured" if _env_has("DATABASE_URL") else "unavailable",
            detail="connection string present; connectivity not checked" if _env_has("DATABASE_URL")
            else "DATABASE_URL is not set",
        ),
        ComponentStatus(
            name="embedding_model",
            status="initialized" if embedding_loaded else "configured",
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
