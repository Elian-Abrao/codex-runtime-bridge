from __future__ import annotations

import asyncio
import unittest

from codex_runtime_bridge.service import CodexBridgeService


class FakeConnection:
    def __init__(self) -> None:
        self.initialized = True
        self.codex_command = "codex"
        self._subscriptions: set[asyncio.Queue[dict]] = set()
        self.turn_start_calls = 0

    async def ensure_initialized(self) -> None:
        return None

    def subscribe(self) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        self._subscriptions.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        self._subscriptions.discard(queue)

    async def request(self, method: str, params: dict | None = None) -> dict:
        if method == "thread/start":
            return {"thread": {"id": "thr_1"}}
        if method == "turn/start":
            self.turn_start_calls += 1
            payload = {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thr_1",
                    "turnId": "turn_1",
                    "itemId": "item_1",
                    "delta": "Hello",
                },
            }
            done = {
                "method": "turn/completed",
                "params": {
                    "threadId": "thr_1",
                    "turn": {"id": "turn_1", "status": "completed"},
                },
            }
            for queue in tuple(self._subscriptions):
                queue.put_nowait(payload)
                queue.put_nowait(done)
            return {"turn": {"id": "turn_1", "status": "inProgress"}}
        raise AssertionError(f"unexpected method {method}")

    async def close(self) -> None:
        return None


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_aggregates_deltas(self) -> None:
        service = CodexBridgeService(connection=FakeConnection())
        result = await service.chat("hi")
        self.assertEqual(result["threadId"], "thr_1")
        self.assertEqual(result["turnId"], "turn_1")
        self.assertEqual(result["assistantText"], "Hello")

