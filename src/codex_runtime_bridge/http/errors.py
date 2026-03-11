from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..transport import AppServerProcessError
from ..transport import JsonRpcRequestError
from .schemas import ErrorEnvelope
from .schemas import ErrorInfo

REQUEST_ID_HEADER = "x-request-id"


def request_id_from_request(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) else None


def build_error_envelope(
    request: Request,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> ErrorEnvelope:
    return ErrorEnvelope(
        error=ErrorInfo(
            code=code,
            message=message,
            details=details or {},
            request_id=request_id_from_request(request),
        )
    )


def error_info_from_exception(exc: Exception) -> tuple[int, str, str, dict[str, Any]]:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            error = detail["error"]
            return (
                exc.status_code,
                error.get("code", "http_error"),
                error.get("message", "HTTP error"),
                error.get("details", {}) or {},
            )
        return exc.status_code, "http_error", str(detail), {}
    if isinstance(exc, RequestValidationError):
        return 422, "invalid_request", "Request validation failed.", {"errors": exc.errors()}
    if isinstance(exc, JsonRpcRequestError):
        return (
            502,
            "upstream_request_failed",
            str(exc),
            {
                "method": exc.method,
                "upstreamError": exc.error,
            },
        )
    if isinstance(exc, AppServerProcessError):
        return 503, "app_server_unavailable", str(exc), {}
    if isinstance(exc, asyncio.TimeoutError):
        return 504, "timeout", "The request timed out while waiting for the Codex runtime.", {}
    return 500, "internal_error", "Unexpected bridge failure.", {"type": exc.__class__.__name__}


def build_error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    envelope = build_error_envelope(
        request,
        code=code,
        message=message,
        details=details,
    )
    headers: dict[str, str] = {}
    request_id = request_id_from_request(request)
    if request_id is not None:
        headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(by_alias=True),
        headers=headers,
    )


async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    status_code, code, message, details = error_info_from_exception(exc)
    return build_error_response(request, status_code=status_code, code=code, message=message, details=details)


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    status_code, code, message, details = error_info_from_exception(exc)
    return build_error_response(request, status_code=status_code, code=code, message=message, details=details)


async def handle_jsonrpc_error(request: Request, exc: JsonRpcRequestError) -> JSONResponse:
    status_code, code, message, details = error_info_from_exception(exc)
    return build_error_response(request, status_code=status_code, code=code, message=message, details=details)


async def handle_process_error(request: Request, exc: AppServerProcessError) -> JSONResponse:
    status_code, code, message, details = error_info_from_exception(exc)
    return build_error_response(request, status_code=status_code, code=code, message=message, details=details)


async def handle_timeout_error(request: Request, exc: asyncio.TimeoutError) -> JSONResponse:
    status_code, code, message, details = error_info_from_exception(exc)
    return build_error_response(request, status_code=status_code, code=code, message=message, details=details)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    status_code, code, message, details = error_info_from_exception(exc)
    return build_error_response(request, status_code=status_code, code=code, message=message, details=details)
