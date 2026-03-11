from __future__ import annotations

import unittest

import httpx

from codex_runtime_bridge.bridge import ConsumerStreamEvent
from codex_runtime_bridge.http.api import create_app
from codex_runtime_bridge.transport import JsonRpcRequestError


class FakeApiService:
    def __init__(self) -> None:
        self.raise_account_error = False

    @property
    def recent_stderr(self) -> list[str]:
        return ["stderr one", "stderr two"]

    async def close(self) -> None:
        return None

    async def health(self) -> dict[str, object]:
        return {"ok": True, "codexCommand": "codex", "initialized": True}

    async def get_account(self) -> dict[str, object]:
        if self.raise_account_error:
            raise JsonRpcRequestError("account/read", {"code": -32000, "message": "boom"})
        return {"account": {"email": "demo@example.com"}}

    async def start_chatgpt_login(self) -> dict[str, object]:
        return {"type": "chatgpt", "loginId": "login_1", "authUrl": "https://example.com"}

    async def logout(self) -> dict[str, object]:
        return {"ok": True}

    async def list_models(self, include_hidden: bool | None = None) -> dict[str, object]:
        return {"data": [], "includeHidden": include_hidden}

    async def list_experimental_features(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, object]:
        return {"data": [], "nextCursor": cursor, "limit": limit}

    async def start_thread(self, **_: object) -> dict[str, object]:
        return {"thread": {"id": "thr_1"}}

    async def chat(self, prompt: str, **_: object) -> dict[str, object]:
        return {"threadId": "thr_1", "turnId": "turn_1", "assistantText": prompt, "turn": {}, "events": []}

    async def stream_turn_events(self, **_: object):
        if False:
            yield None

    async def stream_consumer_events(self, **_: object):
        yield ConsumerStreamEvent(event="status", phase="turn_started", message="Turn started.")
        yield ConsumerStreamEvent(event="final", text="All good.")

    async def exec_command(self, command: list[str], **_: object) -> dict[str, object]:
        return {"command": command, "exitCode": 0}

    async def start_review(self, **_: object) -> dict[str, object]:
        return {"reviewThreadId": "thr_review"}

    async def respond_server_request(
        self,
        request_id: str | int,
        *,
        result: object = None,
        error: dict | None = None,
    ) -> dict[str, object]:
        return {"ok": True, "requestId": request_id, "result": result, "error": error}

    def available_slash_commands(self) -> list[dict[str, object]]:
        return [{"name": "help", "usage": "/help", "summary": "Show help.", "aliases": []}]

    async def execute_slash_command(self, command: str, **_: object) -> dict[str, object]:
        if command == "/bad":
            raise ValueError("bad command")
        return {"command": "help", "message": "ok", "threadId": None}


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.service = FakeApiService()
        self.app = create_app(self.service)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_health_aliases_and_request_id_header(self) -> None:
        response = await self.client.get("/readyz", headers={"x-request-id": "req_api_ready"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-request-id"], "req_api_ready")
        self.assertEqual(response.json()["initialized"], True)

    async def test_consumer_stream_uses_named_sse_events(self) -> None:
        async with self.client.stream(
            "POST",
            "/v1/chat/consumer-stream",
            headers={"x-request-id": "req_stream_1"},
            json={"prompt": "hi"},
        ) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["x-request-id"], "req_stream_1")
            content = await response.aread()

        body = content.decode("utf-8")
        self.assertIn("event: status", body)
        self.assertIn('"event": "status"', body)
        self.assertIn("event: final", body)
        self.assertIn('"text": "All good."', body)

    async def test_http_errors_are_standardized(self) -> None:
        self.service.raise_account_error = True

        response = await self.client.get("/v1/account")

        self.assertEqual(response.status_code, 502)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "upstream_request_failed")
        self.assertEqual(payload["error"]["details"]["method"], "account/read")
        self.assertEqual(payload["error"]["details"]["stderrTail"], ["stderr one", "stderr two"])
        self.assertEqual(payload["error"]["requestId"], response.headers["x-request-id"])

    async def test_slash_command_value_errors_are_standardized(self) -> None:
        response = await self.client.post("/v1/slash-commands/execute", json={"command": "/bad"})

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "invalid_request")
        self.assertEqual(payload["error"]["message"], "bad command")
