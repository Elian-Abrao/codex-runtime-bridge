from __future__ import annotations

import unittest

import httpx

from codex_runtime_bridge.http_client import BridgeHttpClient


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
