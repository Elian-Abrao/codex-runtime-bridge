from __future__ import annotations

import contextlib
import json
from typing import Any, AsyncIterator

import httpx


class BridgeHttpError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        self.details = details or {}
        super().__init__(f"{code} ({status_code}): {message}")


class BridgeHttpClient:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    def _decode_error(self, response: httpx.Response) -> BridgeHttpError:
        payload: dict[str, Any] = {}
        with contextlib.suppress(ValueError):
            payload = response.json()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        message = error.get("message")
        if not isinstance(message, str) or not message:
            message = response.text or response.reason_phrase
        code = error.get("code")
        if not isinstance(code, str) or not code:
            code = "http_error"
        request_id = error.get("requestId") or response.headers.get("x-request-id")
        if not isinstance(request_id, str):
            request_id = None
        details = error.get("details")
        if not isinstance(details, dict):
            details = {}
        return BridgeHttpError(
            status_code=response.status_code,
            code=code,
            message=message,
            request_id=request_id,
            details=details,
        )

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self._client.request(method, path, **kwargs)
        if response.is_error:
            raise self._decode_error(response)
        return response.json()

    async def health(self) -> dict[str, Any]:
        return await self._request_json("GET", "/v1/health")

    async def ready(self) -> dict[str, Any]:
        return await self._request_json("GET", "/readyz")

    async def account(self) -> dict[str, Any]:
        return await self._request_json("GET", "/v1/account")

    async def start_login(self) -> dict[str, Any]:
        return await self._request_json("POST", "/v1/login/chatgpt/start")

    async def logout(self) -> dict[str, Any]:
        return await self._request_json("POST", "/v1/logout")

    async def models(self) -> dict[str, Any]:
        return await self._request_json("GET", "/v1/models")

    async def experimental_features(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = limit
        return await self._request_json("GET", "/v1/experimental-features", params=params or None)

    async def start_thread(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request_json("POST", "/v1/threads/start", json=payload or {})

    async def read_thread(self, thread_id: str) -> dict[str, Any]:
        return await self._request_json("GET", f"/v1/threads/{thread_id}")

    async def resume_thread(self, thread_id: str) -> dict[str, Any]:
        return await self._request_json("POST", f"/v1/threads/{thread_id}/resume")

    async def chat(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        payload = {"prompt": prompt, **kwargs}
        return await self._request_json("POST", "/v1/chat", json=payload)

    async def stream_chat(self, prompt: str, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        payload = {"prompt": prompt, **kwargs}
        async with self._client.stream("POST", "/v1/chat/stream", json=payload) as response:
            if response.is_error:
                await response.aread()
                raise self._decode_error(response)
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                yield json.loads(line[6:])

    async def stream_consumer_chat(self, prompt: str, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        payload = {"prompt": prompt, **kwargs}
        async with self._client.stream("POST", "/v1/chat/consumer-stream", json=payload) as response:
            if response.is_error:
                await response.aread()
                raise self._decode_error(response)
            current_event: str | None = None
            data_lines: list[str] = []
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    current_event = line[7:]
                    continue
                if line.startswith("data: "):
                    data_lines.append(line[6:])
                    continue
                if line:
                    continue
                if not data_lines:
                    current_event = None
                    continue
                payload = json.loads("\n".join(data_lines))
                if current_event and "event" not in payload:
                    payload["event"] = current_event
                yield payload
                current_event = None
                data_lines = []
            if data_lines:
                payload = json.loads("\n".join(data_lines))
                if current_event and "event" not in payload:
                    payload["event"] = current_event
                yield payload

    async def respond_server_request(
        self,
        request_id: str | int,
        *,
        result: Any = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._request_json(
            "POST",
            "/v1/server-requests/respond",
            json={
                "requestId": request_id,
                "result": result,
                "error": error,
            },
        )

    async def start_review(
        self,
        *,
        thread_id: str,
        target: dict[str, Any],
        delivery: str | None = None,
    ) -> dict[str, Any]:
        return await self._request_json(
            "POST",
            "/v1/reviews/start",
            json={
                "threadId": thread_id,
                "target": target,
                "delivery": delivery,
            },
        )

    async def slash_commands(self) -> dict[str, Any]:
        return await self._request_json("GET", "/v1/slash-commands")

    async def execute_slash_command(self, command: str, **kwargs: Any) -> dict[str, Any]:
        return await self._request_json(
            "POST",
            "/v1/slash-commands/execute",
            json={"command": command, **kwargs},
        )

    async def exec(self, command: list[str], **kwargs: Any) -> dict[str, Any]:
        payload = {"command": command, **kwargs}
        return await self._request_json("POST", "/v1/command/exec", json=payload)
