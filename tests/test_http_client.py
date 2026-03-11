from __future__ import annotations

import unittest

import httpx

from codex_runtime_bridge.http import BridgeHttpClient
from codex_runtime_bridge.http.client import BridgeHttpError


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

    async def test_stream_consumer_chat_parses_named_sse_events(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    b'event: status\n'
                    b'data: {"event":"status","phase":"turn_started","message":"Turn started."}\n\n'
                    b'event: final\n'
                    b'data: {"event":"final","text":"Hi"}\n\n'
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

        events = [event async for event in client.stream_consumer_chat("hi")]

        self.assertEqual(
            events,
            [
                {"event": "status", "phase": "turn_started", "message": "Turn started."},
                {"event": "final", "text": "Hi"},
            ],
        )

    async def test_chat_raises_bridge_http_error_with_standardized_payload(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                503,
                json={
                    "error": {
                        "code": "app_server_unavailable",
                        "message": "codex app-server exited",
                        "details": {},
                        "requestId": "req_http_1",
                    }
                },
            )

        transport = httpx.MockTransport(handler)
        client = BridgeHttpClient("http://bridge.test")
        client._client = httpx.AsyncClient(
            base_url="http://bridge.test",
            timeout=120.0,
            transport=transport,
        )
        self.addAsyncCleanup(client.close)

        with self.assertRaises(BridgeHttpError) as raised:
            await client.chat("hi")

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.code, "app_server_unavailable")
        self.assertEqual(raised.exception.request_id, "req_http_1")

    async def test_thread_read_and_resume_use_expected_paths(self) -> None:
        captured: list[tuple[str, str]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            captured.append((request.method, request.url.path))
            if request.method == "GET":
                return httpx.Response(200, json={"thread": {"id": "thr_1", "status": {"type": "notLoaded"}}})
            return httpx.Response(200, json={"thread": {"id": "thr_1", "status": {"type": "idle"}}})

        transport = httpx.MockTransport(handler)
        client = BridgeHttpClient("http://bridge.test")
        client._client = httpx.AsyncClient(
            base_url="http://bridge.test",
            timeout=120.0,
            transport=transport,
        )
        self.addAsyncCleanup(client.close)

        read_result = await client.read_thread("thr_1")
        resume_result = await client.resume_thread("thr_1")

        self.assertEqual(read_result["thread"]["status"]["type"], "notLoaded")
        self.assertEqual(resume_result["thread"]["status"]["type"], "idle")
        self.assertEqual(
            captured,
            [
                ("GET", "/v1/threads/thr_1"),
                ("POST", "/v1/threads/thr_1/resume"),
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

    async def test_experimental_features_gets_expected_query(self) -> None:
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["path"] = request.url.path
            captured["query"] = request.url.query.decode("utf-8")
            return httpx.Response(200, json={"data": [], "nextCursor": None})

        transport = httpx.MockTransport(handler)
        client = BridgeHttpClient("http://bridge.test")
        client._client = httpx.AsyncClient(
            base_url="http://bridge.test",
            timeout=120.0,
            transport=transport,
        )
        self.addAsyncCleanup(client.close)

        result = await client.experimental_features(limit=5, cursor="cursor_1")

        self.assertEqual(result, {"data": [], "nextCursor": None})
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["path"], "/v1/experimental-features")
        self.assertEqual(captured["query"], "cursor=cursor_1&limit=5")

    async def test_start_review_posts_expected_payload(self) -> None:
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["path"] = request.url.path
            captured["body"] = request.content.decode("utf-8")
            return httpx.Response(
                200,
                json={"reviewThreadId": "thr_review", "turn": {"id": "turn_review"}},
            )

        transport = httpx.MockTransport(handler)
        client = BridgeHttpClient("http://bridge.test")
        client._client = httpx.AsyncClient(
            base_url="http://bridge.test",
            timeout=120.0,
            transport=transport,
        )
        self.addAsyncCleanup(client.close)

        result = await client.start_review(
            thread_id="thr_1",
            target={"type": "uncommittedChanges"},
            delivery="inline",
        )

        self.assertEqual(result["reviewThreadId"], "thr_review")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/v1/reviews/start")
        self.assertEqual(
            captured["body"],
            '{"threadId":"thr_1","target":{"type":"uncommittedChanges"},"delivery":"inline"}',
        )
