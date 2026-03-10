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
        self.last_turn_start_params: dict | None = None

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
            self.last_turn_start_params = params or {}
            prompt = ((params or {}).get("input") or [{}])[0].get("text")
            events = [self._delta("item_1", "Hello")]
            if prompt == "with commentary":
                events = [
                    self._item_started("commentary_item", "commentary"),
                    self._delta("commentary_item", "Thinking"),
                    self._item_started("final_item", "final_answer"),
                    self._delta("final_item", "Answer"),
                ]
            for queue in tuple(self._subscriptions):
                for event in events:
                    queue.put_nowait(event)
                queue.put_nowait(self._done())
            return {"turn": {"id": "turn_1", "status": "inProgress"}}
        raise AssertionError(f"unexpected method {method}")

    async def close(self) -> None:
        return None

    def _delta(self, item_id: str, delta: str) -> dict:
        return {
            "method": "item/agentMessage/delta",
            "params": {
                "threadId": "thr_1",
                "turnId": "turn_1",
                "itemId": item_id,
                "delta": delta,
            },
        }

    def _done(self) -> dict:
        return {
            "method": "turn/completed",
            "params": {
                "threadId": "thr_1",
                "turn": {"id": "turn_1", "status": "completed"},
            },
        }

    def _item_started(self, item_id: str, phase: str) -> dict:
        return {
            "method": "item/started",
            "params": {
                "threadId": "thr_1",
                "turnId": "turn_1",
                "item": {
                    "type": "agentMessage",
                    "id": item_id,
                    "text": "",
                    "phase": phase,
                },
            },
        }


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_aggregates_deltas(self) -> None:
        service = CodexBridgeService(connection=FakeConnection())
        result = await service.chat("hi")
        self.assertEqual(result["threadId"], "thr_1")
        self.assertEqual(result["turnId"], "turn_1")
        self.assertEqual(result["assistantText"], "Hello")

    async def test_chat_ignores_commentary_when_final_answer_is_available(self) -> None:
        service = CodexBridgeService(connection=FakeConnection())
        result = await service.chat("with commentary")
        self.assertEqual(result["assistantText"], "Answer")

    async def test_stream_turn_passes_reasoning_summary(self) -> None:
        connection = FakeConnection()
        service = CodexBridgeService(connection=connection)
        async for _ in service.stream_turn(prompt="hi", summary="detailed"):
            pass
        self.assertEqual(connection.last_turn_start_params["summary"], "detailed")
