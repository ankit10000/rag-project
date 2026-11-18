"""FastAPI application factory.

Importing this module creates the app object only: no database connection,
no model load, no provider client. On startup (lifespan) the API token digest
is loaded (fail closed) and stale upload temp files are removed; nothing else.

Request pipeline (outermost first):
  TrustedHost (Host allow-list, DNS-rebinding protection)
  -> BodySizeLimit (Content-Length required for POST; per-route byte limits)
  -> CORS (only explicitly configured origins; no credentials)
  -> request-id
  -> routers: /health (public, minimal) and everything else behind require_token
"""

import glob
import asyncio
import logging
import os
import uuid
from urllib.parse import urlsplit
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from backend import API_VERSION, APP_VERSION, config, errors
from backend.config import API_PREFIX
from backend.routers import chat, conversations, documents, health, memories, metrics, providers, settings
from backend.security import load_token_digest, require_token
from services.request_budget import request_budget, RequestDeadlineExceeded, remaining_seconds

log = logging.getLogger("rag.api")


class BodySizeLimitMiddleware:
    """Reject oversized or unsized request bodies before they are read/spooled."""

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _limit(path):
        if path.rstrip('/') == f'{API_PREFIX}/documents':
            from services import retrieval_config as cfg
            return int(cfg.MAX_PDF_SIZE_MB * 1024 * 1024) + config.MULTIPART_OVERHEAD_BYTES
        return config.MAX_JSON_BODY_BYTES

    @staticmethod
    async def _reject(scope, receive, send, status, code, message):
        await JSONResponse(status_code=status, content={'error': {
            'code': code, 'message': message, 'request_id': None}})(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if (scope.get('method') not in ('POST', 'PUT', 'PATCH')
                and 'content-length' not in headers and 'transfer-encoding' not in headers):
            return await self.app(scope, receive, send)
        lengths = [v for k, v in scope.get('headers', []) if k.lower() == b'content-length']
        if len(lengths) > 1 or ('transfer-encoding' in headers and lengths):
            return await self._reject(scope, receive, send, 400, 'invalid_length', 'ambiguous request body length')
        length = headers.get("content-length")
        if length is None or not length.isdigit():
            return await self._reject(scope, receive, send, 411, "length_required",
                                      "a Content-Length header is required")
        limit = self._limit(scope.get("path", ""))
        if int(length) > limit:
            return await self._reject(scope, receive, send, 413, "payload_too_large", "request body is too large")
        # Count actual ASGI bytes before downstream code can mutate state. A false
        # Content-Length must not bypass the limit or expose a partial upload.
        messages, received = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            received += len(message.get('body', b''))
            if received > limit:
                return await self._reject(scope, receive, send, 413, 'payload_too_large', 'request body is too large')
            messages.append(message)
            if not message.get('more_body', False):
                break
        if received != int(length):
            return await self._reject(scope, receive, send, 400, 'invalid_length', 'request body length does not match')
        async def replay():
            return messages.pop(0) if messages else await receive()
        return await self.app(scope, replay, send)


class RequestBudgetMiddleware:
    """Propagate a cooperative budget into FastAPI sync worker contexts.

    Never cancels/abandons a worker; operations enforce their own finite waits.
    Buffer the response until budget exit so expiration cannot expose late success.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or os.getenv('LOCAL_V1_PROFILE') != '1':
            return await self.app(scope, receive, send)
        messages = []
        async def capture(message):
            messages.append(message)
        async def bounded_receive():
            # Only the network-body await is cancellable here. A sync operation
            # executing in a worker is never wrapped in wait_for or abandoned.
            try:
                return await asyncio.wait_for(receive(), timeout=remaining_seconds())
            except asyncio.TimeoutError:
                raise RequestDeadlineExceeded() from None
        try:
            with request_budget(suppress_output=True):
                await self.app(scope, bounded_receive, capture)
        except RequestDeadlineExceeded:
            response = JSONResponse(status_code=504, content={'error': {
                'code': 'request_timeout', 'message': 'request deadline exceeded',
                'request_id': scope.get('state', {}).get('request_id')}})
            return await response(scope, receive, send)
        for message in messages:
            await send(message)


def _validated_cors_origins() -> list[str]:
    origins = []
    for origin in config.CORS_ORIGINS:
        parsed = urlsplit(origin)
        if (origin in ("*", "null") or parsed.scheme not in ('http', 'https')
                or not parsed.hostname or '*' in origin or parsed.username or parsed.password
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise RuntimeError(f"refusing unsafe CORS origin {origin!r}; list explicit http(s) origins only")
        origins.append(origin.rstrip("/"))
    return origins


def _remove_stale_upload_temps() -> None:
    """Delete only this API's own interrupted temp files (.upload-*.part).
    Previous-version backups (.previous-*.bak) are never deleted automatically."""
    if not os.path.isdir(config.UPLOAD_DIR):
        return
    for path in glob.glob(os.path.join(config.UPLOAD_DIR, ".upload-*.part")):
        try:
            if os.path.isfile(path) and not os.path.islink(path):
                os.remove(path)
        except OSError:
            log.warning("could not remove a stale upload temp file")
    leftovers = glob.glob(os.path.join(config.UPLOAD_DIR, ".previous-*.pdf.bak"))
    if leftovers:
        log.warning("%d previous-version upload backup(s) found; review the upload directory", len(leftovers))


@asynccontextmanager
async def lifespan(app: FastAPI):
    problems, warnings = config.config_problems()
    if problems:                                   # invalid configuration -> startup fails clearly
        raise RuntimeError("invalid API configuration: " + "; ".join(problems))
    for warning in warnings:
        log.warning("configuration: %s", warning)
    digest, source = load_token_digest()          # raises -> startup fails (fail closed)
    app.state.token_digest = digest
    try:
        _remove_stale_upload_temps()
        log.info("RAG API %s starting (api %s); auth token from %s; models/DB load lazily",
                 APP_VERSION, API_VERSION, source)
        yield
    finally:
        app.state.token_digest = None
        log.info("RAG API stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Local RAG Application API",
        version=APP_VERSION,
        description="Local, single-user API over the existing RAG, conversation and memory services. "
                    "All endpoints except /health require 'Authorization: Bearer <token>'.",
        openapi_url=f"{API_PREFIX}/openapi.json" if config.DOCS_ENABLED else None,
        docs_url=f"{API_PREFIX}/docs" if config.DOCS_ENABLED else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.token_digest = None

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        rid = incoming if (0 < len(incoming) <= 64 and incoming.replace("-", "").isalnum()) else uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    origins = _validated_cors_origins()
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                           allow_methods=config.CORS_METHODS, allow_headers=config.CORS_HEADERS,
                           expose_headers=["X-Request-ID"], max_age=600)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RequestBudgetMiddleware)
    hosts = (["127.0.0.1", "localhost", "::1", "[::1]"]
             if os.getenv('LOCAL_V1_PROFILE') == '1' else config.ALLOWED_HOSTS)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    errors.install(app)
    app.include_router(health.public_router, prefix=API_PREFIX)
    protected = [Depends(require_token)]
    for module in (health, settings, metrics, providers, documents, chat, conversations, memories):
        app.include_router(module.router, prefix=API_PREFIX, dependencies=protected)
    return app


app = create_app()
