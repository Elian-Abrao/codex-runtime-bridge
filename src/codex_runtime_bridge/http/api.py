from __future__ import annotations

import json
from contextlib import asynccontextmanager
from uuid import uuid4
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse

from ..bridge import CodexBridgeService
from ..transport import AppServerProcessError
from ..transport import JsonRpcRequestError
from .errors import REQUEST_ID_HEADER
from .errors import build_error_response
from .errors import build_error_envelope
from .errors import error_info_from_exception
from .errors import handle_http_exception
from .errors import handle_validation_error
from .errors import request_id_from_request
from .schemas import ChatRequest
from .schemas import ChatResponse
from .schemas import CommandExecRequest
from .schemas import HealthResponse
from .schemas import LoginStartResponse
from .schemas import ReviewStartRequest
from .schemas import SlashCommandExecuteRequest
from .schemas import SlashCommandExecuteResponse
from .schemas import SlashCommandListResponse
from .schemas import ServerRequestResolveRequest
from .schemas import ThreadStartRequest


def _sse(message: dict[str, Any], *, event: str | None = None) -> bytes:
    lines: list[str] = []
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(message, ensure_ascii=False)}")
    return ("\n".join(lines) + "\n\n").encode("utf-8")


def create_app(service: CodexBridgeService | None = None) -> FastAPI:
    bridge = service or CodexBridgeService()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await bridge.close()

    app = FastAPI(title="Codex Runtime Bridge", version="0.1.0", lifespan=lifespan)
    app.add_exception_handler(HTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    def with_stderr_tail(details: dict[str, Any]) -> dict[str, Any]:
        if not bridge.recent_stderr:
            return details
        return {
            **details,
            "stderrTail": bridge.recent_stderr[-20:],
        }

    @app.exception_handler(JsonRpcRequestError)
    async def jsonrpc_error(request: Request, exc: JsonRpcRequestError):
        status_code, code, message, details = error_info_from_exception(exc)
        return build_error_response(
            request,
            status_code=status_code,
            code=code,
            message=message,
            details=with_stderr_tail(details),
        )

    @app.exception_handler(AppServerProcessError)
    async def process_error(request: Request, exc: AppServerProcessError):
        status_code, code, message, details = error_info_from_exception(exc)
        return build_error_response(
            request,
            status_code=status_code,
            code=code,
            message=message,
            details=with_stderr_tail(details),
        )

    @app.exception_handler(TimeoutError)
    async def timeout_error(request: Request, exc: TimeoutError):
        status_code, code, message, details = error_info_from_exception(exc)
        return build_error_response(
            request,
            status_code=status_code,
            code=code,
            message=message,
            details=with_stderr_tail(details),
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        status_code, code, message, details = error_info_from_exception(exc)
        return build_error_response(
            request,
            status_code=status_code,
            code=code,
            message=message,
            details=with_stderr_tail(details),
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/readyz", response_model=HealthResponse)
    async def readyz() -> dict[str, Any]:
        return await bridge.health()

    @app.get("/v1/health", response_model=HealthResponse)
    async def health() -> dict[str, Any]:
        return await bridge.health()

    @app.get("/v1/account")
    async def account() -> dict[str, Any]:
        return await bridge.get_account()

    @app.post("/v1/login/chatgpt/start", response_model=LoginStartResponse)
    async def login_start() -> dict[str, Any]:
        return await bridge.start_chatgpt_login()

    @app.post("/v1/logout")
    async def logout() -> dict[str, Any]:
        return await bridge.logout()

    @app.get("/v1/models")
    async def models(include_hidden: bool | None = None) -> dict[str, Any]:
        return await bridge.list_models(include_hidden=include_hidden)

    @app.get("/v1/experimental-features")
    async def experimental_features(
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return await bridge.list_experimental_features(cursor=cursor, limit=limit)

    @app.post("/v1/threads/start")
    async def thread_start(request: ThreadStartRequest) -> dict[str, Any]:
        return await bridge.start_thread(
            cwd=request.cwd,
            model=request.model,
            approval_policy=request.approval_policy,
            sandbox=request.sandbox,
            personality=request.personality,
            ephemeral=request.ephemeral,
        )

    @app.post("/v1/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> dict[str, Any]:
        return await bridge.chat(
            request.prompt,
            thread_id=request.thread_id,
            cwd=request.cwd,
            model=request.model,
            approval_policy=request.approval_policy,
            sandbox=request.sandbox,
            effort=request.effort,
            summary=request.summary,
            personality=request.personality,
        )

    @app.post("/v1/chat/stream")
    async def chat_stream(request: ChatRequest) -> StreamingResponse:
        async def body() -> AsyncIterator[bytes]:
            async for event in bridge.stream_turn_events(
                prompt=request.prompt,
                thread_id=request.thread_id,
                cwd=request.cwd,
                model=request.model,
                approval_policy=request.approval_policy,
                sandbox=request.sandbox,
                effort=request.effort,
                summary=request.summary,
                personality=request.personality,
            ):
                yield _sse(event.to_dict(), event=event.type)

        return StreamingResponse(body(), media_type="text/event-stream")

    @app.post("/v1/chat/consumer-stream")
    async def chat_consumer_stream(request: ChatRequest, http_request: Request) -> StreamingResponse:
        request_id = request_id_from_request(http_request)

        async def body() -> AsyncIterator[bytes]:
            try:
                async for event in bridge.stream_consumer_events(
                    prompt=request.prompt,
                    thread_id=request.thread_id,
                    cwd=request.cwd,
                    model=request.model,
                    approval_policy=request.approval_policy,
                    sandbox=request.sandbox,
                    effort=request.effort,
                    summary=request.summary,
                    personality=request.personality,
                ):
                    yield _sse(event.to_dict(), event=event.event)
            except Exception as exc:
                _, code, message, details = error_info_from_exception(exc)
                if bridge.recent_stderr:
                    details = {
                        **details,
                        "stderrTail": bridge.recent_stderr[-20:],
                    }
                error_event = {
                    "event": "error",
                    "code": code,
                    "message": message,
                    "requestId": request_id,
                    "details": details,
                }
                yield _sse(error_event, event="error")

        return StreamingResponse(body(), media_type="text/event-stream")

    @app.post("/v1/command/exec")
    async def command_exec(request: CommandExecRequest) -> dict[str, Any]:
        return await bridge.exec_command(
            request.command,
            cwd=request.cwd,
            timeout_ms=request.timeout_ms,
            sandbox_policy=request.sandbox_policy,
        )

    @app.post("/v1/reviews/start")
    async def review_start(request: ReviewStartRequest) -> dict[str, Any]:
        return await bridge.start_review(
            thread_id=request.thread_id,
            target=request.target,
            delivery=request.delivery,
        )

    @app.post("/v1/server-requests/respond")
    async def server_request_respond(request: ServerRequestResolveRequest) -> dict[str, Any]:
        return await bridge.respond_server_request(
            request.request_id,
            result=request.result,
            error=request.error,
        )

    @app.get("/v1/slash-commands", response_model=SlashCommandListResponse)
    async def slash_commands() -> dict[str, Any]:
        return {"commands": bridge.available_slash_commands()}

    @app.post("/v1/slash-commands/execute", response_model=SlashCommandExecuteResponse)
    async def slash_command_execute(
        request: SlashCommandExecuteRequest,
        http_request: Request,
    ) -> dict[str, Any]:
        try:
            return await bridge.execute_slash_command(
                request.command,
                thread_id=request.thread_id,
                cwd=request.cwd,
                model=request.model,
                approval_policy=request.approval_policy,
                sandbox=request.sandbox,
                personality=request.personality,
                ephemeral=request.ephemeral,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=build_error_envelope(
                    http_request,
                    code="invalid_request",
                    message=str(exc),
                ).model_dump(by_alias=True),
            ) from exc

    return app
