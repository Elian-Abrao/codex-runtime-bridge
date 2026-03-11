from __future__ import annotations

import asyncio
import contextlib
import webbrowser
from pathlib import Path
from typing import Any, AsyncIterator

from .commands import SlashCommandContext
from .commands import available_slash_commands as list_slash_commands
from .commands import execute_slash_command as run_slash_command
from .consumer_events import ConsumerEventProjector
from .consumer_events import ConsumerStreamEvent
from .events import BridgeEvent
from .translator import translate_upstream_message
from ..transport import AppServerConnection
from ..transport import AppServerOptions
from ..transport import JsonDict
from ..transport import normalize_cwd


class CodexBridgeService:
    def __init__(self, connection: AppServerConnection | None = None) -> None:
        self._connection = connection or AppServerConnection(AppServerOptions())

    @property
    def codex_command(self) -> str:
        return self._connection.codex_command

    @property
    def initialized(self) -> bool:
        return self._connection.initialized

    @property
    def recent_stderr(self) -> list[str]:
        return self._connection.recent_stderr

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

    async def respond_server_request(
        self,
        request_id: str | int,
        *,
        result: Any | None = None,
        error: JsonDict | None = None,
    ) -> dict[str, Any]:
        await self._connection.respond(request_id, result=result, error=error)
        return {
            "ok": True,
            "requestId": request_id,
        }

    async def resolve_command_execution_approval(
        self,
        request_id: str | int,
        decision: str | JsonDict,
    ) -> dict[str, Any]:
        return await self.respond_server_request(
            request_id,
            result={"decision": decision},
        )

    async def resolve_file_change_approval(
        self,
        request_id: str | int,
        decision: str,
    ) -> dict[str, Any]:
        return await self.respond_server_request(
            request_id,
            result={"decision": decision},
        )

    async def submit_tool_input(
        self,
        request_id: str | int,
        answers: JsonDict,
    ) -> dict[str, Any]:
        return await self.respond_server_request(
            request_id,
            result={"answers": answers},
        )

    async def submit_dynamic_tool_result(
        self,
        request_id: str | int,
        *,
        content_items: list[JsonDict],
        success: bool,
    ) -> dict[str, Any]:
        return await self.respond_server_request(
            request_id,
            result={
                "contentItems": content_items,
                "success": success,
            },
        )

    async def submit_mcp_elicitation(
        self,
        request_id: str | int,
        *,
        action: str,
        content: Any | None = None,
    ) -> dict[str, Any]:
        return await self.respond_server_request(
            request_id,
            result={
                "action": action,
                "content": content,
            },
        )

    async def submit_chatgpt_auth_refresh(
        self,
        request_id: str | int,
        *,
        access_token: str,
        chatgpt_account_id: str,
        chatgpt_plan_type: str | None = None,
    ) -> dict[str, Any]:
        return await self.respond_server_request(
            request_id,
            result={
                "accessToken": access_token,
                "chatgptAccountId": chatgpt_account_id,
                "chatgptPlanType": chatgpt_plan_type,
            },
        )

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

    async def list_experimental_features(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> JsonDict:
        return await self._connection.request(
            "experimentalFeature/list",
            {
                "cursor": cursor,
                "limit": limit,
            },
        )

    async def list_skills(
        self,
        *,
        cwds: list[str | Path] | None = None,
        force_reload: bool = False,
        per_cwd_extra_user_roots: list[JsonDict] | None = None,
    ) -> JsonDict:
        normalized_cwds: list[str] = []
        if cwds is not None:
            for cwd in cwds:
                normalized = normalize_cwd(cwd)
                if normalized is not None:
                    normalized_cwds.append(normalized)

        return await self._connection.request(
            "skills/list",
            {
                "cwds": normalized_cwds,
                "forceReload": force_reload,
                "perCwdExtraUserRoots": per_cwd_extra_user_roots,
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

    async def start_review(
        self,
        *,
        thread_id: str,
        target: JsonDict,
        delivery: str | None = None,
    ) -> JsonDict:
        return await self._connection.request(
            "review/start",
            {
                "threadId": thread_id,
                "target": target,
                "delivery": delivery,
            },
        )

    async def set_thread_name(self, thread_id: str, name: str) -> JsonDict:
        return await self._connection.request(
            "thread/name/set",
            {
                "threadId": thread_id,
                "name": name,
            },
        )

    def available_slash_commands(self) -> list[dict[str, Any]]:
        return [spec.to_dict() for spec in list_slash_commands()]

    async def execute_slash_command(
        self,
        command: str,
        *,
        thread_id: str | None = None,
        cwd: str | Path | None = None,
        model: str | None = None,
        approval_policy: str | None = None,
        sandbox: str | None = None,
        personality: str | None = None,
        ephemeral: bool | None = None,
    ) -> dict[str, Any]:
        result = await run_slash_command(
            self,
            command,
            SlashCommandContext(
                thread_id=thread_id,
                cwd=cwd,
                model=model,
                approval_policy=approval_policy,
                sandbox=sandbox,
                personality=personality,
                ephemeral=ephemeral,
            ),
        )
        return result.to_dict()

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

    async def stream_turn_events(
        self,
        *,
        prompt: str,
        thread_id: str | None = None,
        cwd: str | Path | None = None,
        model: str | None = None,
        approval_policy: str | None = None,
        sandbox: str | None = None,
        effort: str | None = None,
        summary: str | None = None,
        personality: str | None = None,
    ) -> AsyncIterator[BridgeEvent]:
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
            yield BridgeEvent.thread_started(thread_id, thread)

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
                    "summary": summary,
                    "personality": personality,
                },
            )
            turn = turn_result["turn"]
            turn_id = turn["id"]
            yield BridgeEvent.turn_started(thread_id, turn_id, turn)

            while True:
                message = await queue.get()
                event = translate_upstream_message(message)
                if event is None:
                    continue
                if event.kind == "server_request" and event.thread_id is None and event.turn_id is None:
                    yield event
                    continue
                if event.thread_id != thread_id:
                    continue
                if event.turn_id is not None and event.turn_id != turn_id:
                    continue
                yield event

                if event.type == "turn/completed":
                    break
        finally:
            self._connection.unsubscribe(queue)

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
        summary: str | None = None,
        personality: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        async for event in self.stream_turn_events(
            prompt=prompt,
            thread_id=thread_id,
            cwd=cwd,
            model=model,
            approval_policy=approval_policy,
            sandbox=sandbox,
            effort=effort,
            summary=summary,
            personality=personality,
        ):
            yield event.to_dict()

    async def stream_consumer_events(
        self,
        *,
        prompt: str,
        thread_id: str | None = None,
        cwd: str | Path | None = None,
        model: str | None = None,
        approval_policy: str | None = None,
        sandbox: str | None = None,
        effort: str | None = None,
        summary: str | None = None,
        personality: str | None = None,
    ) -> AsyncIterator[ConsumerStreamEvent]:
        projector = ConsumerEventProjector()
        async for event in projector.project(
            self.stream_turn_events(
                prompt=prompt,
                thread_id=thread_id,
                cwd=cwd,
                model=model,
                approval_policy=approval_policy,
                sandbox=sandbox,
                effort=effort,
                summary=summary,
                personality=personality,
            )
        ):
            yield event

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
        summary: str | None = None,
        personality: str | None = None,
    ) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        assistant_fragments: list[str] = []
        final_turn: JsonDict | None = None
        current_thread_id = thread_id
        current_turn_id: str | None = None
        agent_message_phases: dict[str, str | None] = {}

        async for event in self.stream_turn_events(
            prompt=prompt,
            thread_id=thread_id,
            cwd=cwd,
            model=model,
            approval_policy=approval_policy,
            sandbox=sandbox,
            effort=effort,
            summary=summary,
            personality=personality,
        ):
            events.append(event.to_dict())
            current_thread_id = event.thread_id or current_thread_id
            if event.type == "turn.started":
                current_turn_id = event.turn_id
            elif event.type == "turn/started":
                current_turn_id = event.turn_id or current_turn_id
            elif event.type == "item/started":
                item = event.item or {}
                if item.get("type") == "agentMessage":
                    agent_message_phases[item["id"]] = item.get("phase")
            elif event.type == "item/agentMessage/delta":
                item_id = event.item_id
                phase = agent_message_phases.get(item_id)
                if phase in (None, "final_answer"):
                    assistant_fragments.append(event.payload["delta"])
            elif event.type == "turn/completed":
                final_turn = event.turn

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
