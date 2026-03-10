from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from ..bridge import CodexBridgeService
from .schemas import ChatRequest
from .schemas import ChatResponse
from .schemas import CommandExecRequest
from .schemas import HealthResponse
from .schemas import LoginStartResponse
from .schemas import ThreadStartRequest


def _sse(message: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(message, ensure_ascii=False)}\n\n".encode("utf-8")


def create_app(service: CodexBridgeService | None = None) -> FastAPI:
    bridge = service or CodexBridgeService()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await bridge.close()

    app = FastAPI(title="Codex Runtime Bridge", version="0.1.0", lifespan=lifespan)

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
            async for event in bridge.stream_turn(
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
                yield _sse(event)

        return StreamingResponse(body(), media_type="text/event-stream")

    @app.post("/v1/command/exec")
    async def command_exec(request: CommandExecRequest) -> dict[str, Any]:
        return await bridge.exec_command(
            request.command,
            cwd=request.cwd,
            timeout_ms=request.timeout_ms,
            sandbox_policy=request.sandbox_policy,
        )

    return app
