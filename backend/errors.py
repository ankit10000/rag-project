"""Centralized API errors. Clients never see stack traces, SQL, credentials or paths."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("rag.api")


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def conflict(message: str) -> ApiError:
    return ApiError(409, "conflict", message)


def unprocessable(code: str, message: str) -> ApiError:
    return ApiError(422, code, message)


def _body(request: Request, code: str, message: str, extra=None) -> dict:
    body = {"error": {"code": code, "message": message,
                      "request_id": getattr(request.state, "request_id", None)}}
    if extra:
        body["error"]["details"] = extra
    return body


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status_code, content=_body(request, exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        # Field locations and messages only; the submitted values are not echoed.
        details = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in exc.errors()]
        return JSONResponse(status_code=422, content=_body(request, "invalid_request", "request validation failed", details))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        # Log the exception TYPE only (messages can contain SQL, paths or user text).
        log.error("unhandled %s (request_id=%s)", type(exc).__name__, getattr(request.state, "request_id", None))
        return JSONResponse(status_code=500, content=_body(request, "internal_error", "internal server error"))
