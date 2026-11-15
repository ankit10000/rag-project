"""FastAPI application factory.

Importing this module creates the app object only: no database connection,
no model load, no provider client. Startup (lifespan) logs the configured
state and touches nothing else. CORS is not enabled (same-origin/local tools
only); authentication and wider network exposure are Phase 7.
"""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from backend import API_VERSION, APP_VERSION, errors
from backend.config import API_PREFIX
from backend.routers import chat, conversations, documents, health, memories, metrics, providers, settings

log = logging.getLogger("rag.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("RAG API %s starting (api %s); models/DB load lazily on first use", APP_VERSION, API_VERSION)
    yield
    log.info("RAG API stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Local RAG Application API",
        version=APP_VERSION,
        description="Local, single-user API over the existing RAG, conversation and memory services.",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        rid = incoming if (0 < len(incoming) <= 64 and incoming.replace("-", "").isalnum()) else uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    errors.install(app)
    for module in (health, settings, metrics, providers, documents, chat, conversations, memories):
        app.include_router(module.router, prefix=API_PREFIX)
    return app


app = create_app()
