from __future__ import annotations

import asyncio
import contextlib
import webbrowser
from pathlib import Path
from typing import Any, AsyncIterator

from .rpc import AppServerConnection, AppServerOptions, JsonDict, normalize_cwd


class CodexBridgeService:
    def __init__(self, connection: AppServerConnection | None = None) -> None:
        self._connection = connection or AppServerConnection(AppServerOptions())

    @property
    def codex_command(self) -> str:
        return self._connection.codex_command

    @property
    def initialized(self) -> bool:
        return self._connection.initialized

    async def close(self) -> None:
        await self._connection.close()

    async def health(self) -> dict[str, Any]:
        await self._connection.ensure_initialized()
        return {
            "ok": True,
            "codexCommand": self.codex_command,
            "initialized": self.initialized,
        }

    async def get_account(self, refresh_token: bool = False) -> JsonDict:
        return await self._connection.request(
            "account/read",
            {"refreshToken": refresh_token},
        )

    async def start_chatgpt_login(self) -> JsonDict:
        return await self._connection.request(
            "account/login/start",
            {"type": "chatgpt"},
        )

    async def wait_for_login_completion(
        self,
        login_id: str | None,
        timeout: float = 300.0,
    ) -> JsonDict:
        queue = self._connection.subscribe()
        try:
            while True:
                message = await asyncio.wait_for(queue.get(), timeout=timeout)
                if message.get("method") != "account/login/completed":
                    continue
                params = message.get("params", {})
                if login_id is not None and params.get("loginId") != login_id:
                    continue
                return params
        finally:
            self._connection.unsubscribe(queue)

    async def login_chatgpt(
        self,
        *,
        open_browser: bool = True,
        timeout: float = 300.0,
    ) -> JsonDict:
        result = await self.start_chatgpt_login()
        auth_url = result.get("authUrl")
        login_id = result.get("loginId")
        if open_browser and auth_url:
            webbrowser.open(auth_url)
        completion = await self.wait_for_login_completion(login_id=login_id, timeout=timeout)
        return {
            "start": result,
            "completion": completion,
        }

    async def cancel_login(self, login_id: str) -> JsonDict:
        return await self._connection.request(
            "account/login/cancel",
            {"loginId": login_id},
        )

    async def logout(self) -> JsonDict:
        return await self._connection.request("account/logout", {})

    async def list_models(
        self,
        *,
        include_hidden: bool | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> JsonDict:
        return await self._connection.request(
            "model/list",
            {
                "includeHidden": include_hidden,
                "cursor": cursor,
                "limit": limit,
            },
        )

    async def start_thread(
        self,
        *,
        cwd: str | Path | None = None,
        model: str | None = None,
        approval_policy: str | None = None,
        sandbox: str | None = None,
        personality: str | None = None,
        ephemeral: bool | None = None,
    ) -> JsonDict:
        return await self._connection.request(
            "thread/start",
            {
                "cwd": normalize_cwd(cwd),
                "model": model,
                "approvalPolicy": approval_policy,
                "sandbox": sandbox,
                "personality": personality,
                "ephemeral": ephemeral,
            },
        )

    async def exec_command(
        self,
        command: list[str],
        *,
        cwd: str | Path | None = None,
        timeout_ms: int | None = None,
        sandbox_policy: JsonDict | None = None,
    ) -> JsonDict:
        return await self._connection.request(
            "command/exec",
            {
                "command": command,
                "cwd": normalize_cwd(cwd),
                "timeoutMs": timeout_ms,
                "sandboxPolicy": sandbox_policy,
            },
        )

    async def stream_turn(
        self,
        *,
        prompt: str,
        thread_id: str | None = None,
        cwd: str | Path | None = None,
        model: str | None = None,
        approval_policy: str | None = None,
        sandbox: str | None = None,
        effort: str | None = None,
        personality: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        if not thread_id:
            thread_result = await self.start_thread(
                cwd=cwd,
                model=model,
                approval_policy=approval_policy,
                sandbox=sandbox,
                personality=personality,
            )
            thread = thread_result["thread"]
            thread_id = thread["id"]
            yield {
                "type": "thread.started",
                "threadId": thread_id,
                "thread": thread,
            }

        queue = self._connection.subscribe()
        try:
            turn_result = await self._connection.request(
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": prompt}],
                    "cwd": normalize_cwd(cwd),
                    "model": model,
                    "approvalPolicy": approval_policy,
                    "effort": effort,
                    "personality": personality,
                },
            )
            turn = turn_result["turn"]
            turn_id = turn["id"]
            yield {
                "type": "turn.started",
                "threadId": thread_id,
                "turnId": turn_id,
                "turn": turn,
            }

            while True:
                message = await queue.get()
                method = message.get("method")
                params = message.get("params", {})
                if params.get("threadId") != thread_id:
                    continue

                current_turn_id = params.get("turnId") or params.get("turn", {}).get("id")
                if current_turn_id != turn_id:
                    continue

                event = {
                    "type": method,
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "payload": params,
                }
                yield event

                if method == "turn/completed":
                    break
        finally:
            self._connection.unsubscribe(queue)

    async def chat(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        cwd: str | Path | None = None,
        model: str | None = None,
        approval_policy: str | None = None,
        sandbox: str | None = None,
        effort: str | None = None,
        personality: str | None = None,
    ) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        assistant_fragments: list[str] = []
        final_turn: JsonDict | None = None
        current_thread_id = thread_id
        current_turn_id: str | None = None

        async for event in self.stream_turn(
            prompt=prompt,
            thread_id=thread_id,
            cwd=cwd,
            model=model,
            approval_policy=approval_policy,
            sandbox=sandbox,
            effort=effort,
            personality=personality,
        ):
            events.append(event)
            current_thread_id = event.get("threadId", current_thread_id)
            if event["type"] == "turn.started":
                current_turn_id = event["turnId"]
            elif event["type"] == "item/agentMessage/delta":
                assistant_fragments.append(event["payload"]["delta"])
            elif event["type"] == "turn/completed":
                final_turn = event["payload"]["turn"]

        return {
            "threadId": current_thread_id,
            "turnId": current_turn_id,
            "assistantText": "".join(assistant_fragments).strip(),
            "turn": final_turn or {},
            "events": events,
        }


@contextlib.asynccontextmanager
async def bridge_service() -> AsyncIterator[CodexBridgeService]:
    service = CodexBridgeService()
    try:
        yield service
    finally:
        await service.close()

