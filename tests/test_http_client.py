from __future__ import annotations

import unittest

import httpx

from codex_runtime_bridge.http import BridgeHttpClient


class BridgeHttpClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_chat_parses_sse_events(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    b'data: {"type":"item/agentMessage/delta","payload":{"delta":"Hi"}}\n\n'
                    b'data: {"type":"turn/completed","payload":{"turn":{"id":"turn_1"}}}\n\n'
                ),
            )

        transport = httpx.MockTransport(handler)
        client = BridgeHttpClient("http://bridge.test")
        client._client = httpx.AsyncClient(
            base_url="http://bridge.test",
            timeout=120.0,
            transport=transport,
        )
        self.addAsyncCleanup(client.close)

        events = [event async for event in client.stream_chat("hi")]

        self.assertEqual(
            events,
            [
                {"type": "item/agentMessage/delta", "payload": {"delta": "Hi"}},
                {"type": "turn/completed", "payload": {"turn": {"id": "turn_1"}}},
            ],
        )

    async def test_respond_server_request_posts_expected_payload(self) -> None:
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["path"] = request.url.path
            captured["body"] = request.content.decode("utf-8")
            return httpx.Response(
                200,
                json={"ok": True, "requestId": "req_1"},
            )

        transport = httpx.MockTransport(handler)
        client = BridgeHttpClient("http://bridge.test")
        client._client = httpx.AsyncClient(
            base_url="http://bridge.test",
            timeout=120.0,
            transport=transport,
        )
        self.addAsyncCleanup(client.close)

        result = await client.respond_server_request("req_1", result={"decision": "decline"})

        self.assertEqual(result, {"ok": True, "requestId": "req_1"})
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/v1/server-requests/respond")
        self.assertEqual(
            captured["body"],
            '{"requestId":"req_1","result":{"decision":"decline"},"error":null}',
        )

    async def test_execute_slash_command_posts_expected_payload(self) -> None:
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["path"] = request.url.path
            captured["body"] = request.content.decode("utf-8")
            return httpx.Response(
                200,
                json={"command": "rename", "message": "Renamed thread thr_1 to 'Demo'.", "threadId": "thr_1"},
            )

        transport = httpx.MockTransport(handler)
        client = BridgeHttpClient("http://bridge.test")
        client._client = httpx.AsyncClient(
            base_url="http://bridge.test",
            timeout=120.0,
            transport=transport,
        )
        self.addAsyncCleanup(client.close)

        result = await client.execute_slash_command("/rename Demo", threadId="thr_1")

        self.assertEqual(result["command"], "rename")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/v1/slash-commands/execute")
        self.assertEqual(
            captured["body"],
            '{"command":"/rename Demo","threadId":"thr_1"}',
        )
