from __future__ import annotations

import asyncio
import unittest

from codex_runtime_bridge.bridge import BridgeEvent
from codex_runtime_bridge.bridge import CodexBridgeService


class FakeConnection:
    def __init__(self) -> None:
        self.initialized = True
        self.codex_command = "codex"
        self._subscriptions: set[asyncio.Queue[dict]] = set()
        self.turn_start_calls = 0
        self.last_turn_start_params: dict | None = None
        self.respond_calls: list[dict] = []

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
            elif prompt == "needs approval":
                events = [
                    self._request_approval("req_1", "rm -rf /tmp/demo"),
                    self._done(),
                ]
            for queue in tuple(self._subscriptions):
                for event in events:
                    queue.put_nowait(event)
                if prompt != "needs approval":
                    queue.put_nowait(self._done())
            return {"turn": {"id": "turn_1", "status": "inProgress"}}
        raise AssertionError(f"unexpected method {method}")

    async def respond(self, request_id: str | int, *, result: object = None, error: dict | None = None) -> None:
        self.respond_calls.append(
            {
                "request_id": request_id,
                "result": result,
                "error": error,
            }
        )

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

    def _request_approval(self, request_id: str, command: str) -> dict:
        return {
            "id": request_id,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": "thr_1",
                "turnId": "turn_1",
                "itemId": "call_1",
                "command": command,
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

    async def test_stream_turn_events_translates_server_requests(self) -> None:
        service = CodexBridgeService(connection=FakeConnection())
        events = [event async for event in service.stream_turn_events(prompt="needs approval")]

        approval_event = next(event for event in events if event.type == "item/commandExecution/requestApproval")
        self.assertIsInstance(approval_event, BridgeEvent)
        self.assertEqual(approval_event.kind, "server_request")
        self.assertEqual(approval_event.request_id, "req_1")
        self.assertEqual(approval_event.payload["command"], "rm -rf /tmp/demo")

    async def test_stream_turn_keeps_legacy_wire_shape_for_server_requests(self) -> None:
        service = CodexBridgeService(connection=FakeConnection())
        events = [event async for event in service.stream_turn(prompt="needs approval")]

        approval_event = next(event for event in events if event["type"] == "item/commandExecution/requestApproval")
        self.assertEqual(approval_event["requestId"], "req_1")
        self.assertEqual(approval_event["payload"]["command"], "rm -rf /tmp/demo")

    async def test_respond_server_request_uses_connection_response_channel(self) -> None:
        connection = FakeConnection()
        service = CodexBridgeService(connection=connection)

        result = await service.resolve_command_execution_approval("req_1", "decline")

        self.assertEqual(result, {"ok": True, "requestId": "req_1"})
        self.assertEqual(
            connection.respond_calls,
            [
                {
                    "request_id": "req_1",
                    "result": {"decision": "decline"},
                    "error": None,
                }
            ],
        )
