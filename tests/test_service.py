from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from codex_runtime_bridge.bridge import BridgeEvent
from codex_runtime_bridge.bridge import CodexBridgeService


class FakeConnection:
    def __init__(self) -> None:
        self.initialized = True
        self.codex_command = "codex"
        self._subscriptions: set[asyncio.Queue[dict]] = set()
        self.request_calls: list[dict] = []
        self.thread_start_calls = 0
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
        self.request_calls.append({"method": method, "params": params})
        if method == "thread/start":
            self.thread_start_calls += 1
            return {"thread": {"id": f"thr_{self.thread_start_calls}"}}
        if method == "thread/read":
            return {"thread": {"id": (params or {}).get("threadId"), "status": {"type": "notLoaded"}, "turns": []}}
        if method == "thread/resume":
            return {
                "thread": {
                    "id": (params or {}).get("threadId"),
                    "status": {"type": "idle"},
                    "turns": [{"id": "turn_1", "status": "completed", "items": []}],
                }
            }
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
            elif prompt == "consumer rich":
                events = [
                    self._item_started("commentary_item", "commentary"),
                    self._delta("commentary_item", "Thinking through the machine state."),
                    self._reasoning_delta("reason_1", "Checking resource usage."),
                    self._command_started("cmd_1", "pwd"),
                    self._item_started("final_item", "final_answer"),
                    self._delta("final_item", "All good."),
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
        if method == "thread/name/set":
            return {}
        if method == "skills/list":
            cwd = ((params or {}).get("cwds") or ["/workspace"])[0]
            return {
                "data": [
                    {
                        "cwd": cwd,
                        "errors": [],
                        "skills": [
                            {
                                "name": "playwright",
                                "scope": "system",
                                "description": "Browser automation",
                                "shortDescription": "Browser automation",
                                "path": "/skills/playwright",
                                "enabled": True,
                            }
                        ],
                    }
                ]
            }
        if method == "experimentalFeature/list":
            return {
                "data": [
                    {
                        "name": "stream_review_mode",
                        "displayName": "Stream Review Mode",
                        "description": "Incremental review output.",
                        "stage": "beta",
                        "enabled": True,
                        "defaultEnabled": False,
                    }
                ],
                "nextCursor": "cursor_2",
            }
        if method == "review/start":
            return {
                "reviewThreadId": "thr_review",
                "turn": {"id": "turn_review", "status": "inProgress"},
            }
        if method == "command/exec":
            return {
                "command": (params or {}).get("command", []),
                "cwd": (params or {}).get("cwd"),
                "exitCode": 0,
            }
        if method == "account/logout":
            return {"ok": True}
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

    def _reasoning_delta(self, item_id: str, delta: str) -> dict:
        return {
            "method": "item/reasoning/summaryTextDelta",
            "params": {
                "threadId": "thr_1",
                "turnId": "turn_1",
                "itemId": item_id,
                "delta": delta,
            },
        }

    def _command_started(self, item_id: str, command: str) -> dict:
        return {
            "method": "item/started",
            "params": {
                "threadId": "thr_1",
                "turnId": "turn_1",
                "item": {
                    "type": "commandExecution",
                    "id": item_id,
                    "command": command,
                },
            },
        }


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_without_cwd_uses_default_workspace_and_bootstraps_agents_file(self) -> None:
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_dir = Path(temp_dir) / "workspace"
            service = CodexBridgeService(connection=connection, default_workspace_dir=workspace_dir)

            result = await service.chat("hi")
            agents_path = workspace_dir / "AGENTS.md"
            self.assertTrue(agents_path.exists())
            self.assertIn("default workspace used by `codex-runtime-bridge`", agents_path.read_text(encoding="utf-8"))

        self.assertEqual(result["assistantText"], "Hello")
        self.assertEqual(
            connection.request_calls[0],
            {
                "method": "thread/start",
                "params": {
                    "cwd": str(workspace_dir.resolve()),
                    "model": None,
                    "approvalPolicy": None,
                    "sandbox": None,
                    "personality": None,
                    "ephemeral": None,
                },
            },
        )

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

    async def test_stream_consumer_events_projects_stable_progress_events(self) -> None:
        service = CodexBridgeService(connection=FakeConnection())

        events = [event.to_dict() async for event in service.stream_consumer_events(prompt="consumer rich")]

        self.assertEqual(
            [event["event"] for event in events],
            ["status", "status", "commentary", "reasoning_summary", "action", "final"],
        )
        self.assertEqual(events[0]["phase"], "thread_started")
        self.assertEqual(events[1]["phase"], "turn_started")
        self.assertEqual(events[2]["text"], "Thinking through the machine state.")
        self.assertEqual(events[3]["text"], "Checking resource usage.")
        self.assertEqual(events[4]["actionType"], "command_execution")
        self.assertEqual(events[4]["text"], "Executing command: pwd")
        self.assertEqual(events[5]["text"], "All good.")

    async def test_stream_consumer_events_projects_approval_requests(self) -> None:
        service = CodexBridgeService(connection=FakeConnection())

        events = [event.to_dict() async for event in service.stream_consumer_events(prompt="needs approval")]

        approval_event = next(event for event in events if event["event"] == "approval_request")
        self.assertEqual(approval_event["approvalType"], "command_execution")
        self.assertEqual(approval_event["requestId"], "req_1")
        self.assertEqual(approval_event["details"]["command"], "rm -rf /tmp/demo")

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

    async def test_execute_slash_command_help_returns_registered_commands(self) -> None:
        service = CodexBridgeService(connection=FakeConnection())

        result = await service.execute_slash_command("/help")

        self.assertEqual(result["command"], "help")
        self.assertIn("/new", result["message"])
        self.assertIn("skills", [item["name"] for item in result["data"]["commands"]])

    async def test_execute_slash_command_new_starts_thread(self) -> None:
        connection = FakeConnection()
        service = CodexBridgeService(connection=connection)

        result = await service.execute_slash_command("/new", cwd="/tmp/demo")

        self.assertEqual(result["command"], "new")
        self.assertEqual(result["threadId"], "thr_1")
        self.assertEqual(
            connection.request_calls[0],
            {
                "method": "thread/start",
                "params": {
                    "cwd": "/tmp/demo",
                    "model": None,
                    "approvalPolicy": None,
                    "sandbox": None,
                    "personality": None,
                    "ephemeral": None,
                },
            },
        )

    async def test_execute_slash_command_rename_sets_thread_name(self) -> None:
        connection = FakeConnection()
        service = CodexBridgeService(connection=connection)

        result = await service.execute_slash_command("/rename Demo Thread", thread_id="thr_7")

        self.assertEqual(result["command"], "rename")
        self.assertEqual(result["threadId"], "thr_7")
        self.assertEqual(
            connection.request_calls[0],
            {
                "method": "thread/name/set",
                "params": {"threadId": "thr_7", "name": "Demo Thread"},
            },
        )

    async def test_read_thread_uses_official_upstream_method(self) -> None:
        connection = FakeConnection()
        service = CodexBridgeService(connection=connection)

        result = await service.read_thread("thr_42")

        self.assertEqual(result["thread"]["id"], "thr_42")
        self.assertEqual(
            connection.request_calls[0],
            {
                "method": "thread/read",
                "params": {"threadId": "thr_42"},
            },
        )

    async def test_resume_thread_uses_official_upstream_method(self) -> None:
        connection = FakeConnection()
        service = CodexBridgeService(connection=connection)

        result = await service.resume_thread("thr_42")

        self.assertEqual(result["thread"]["id"], "thr_42")
        self.assertEqual(result["thread"]["status"]["type"], "idle")
        self.assertEqual(
            connection.request_calls[0],
            {
                "method": "thread/resume",
                "params": {"threadId": "thr_42"},
            },
        )

    async def test_execute_slash_command_skills_uses_current_cwd(self) -> None:
        connection = FakeConnection()
        service = CodexBridgeService(connection=connection)

        result = await service.execute_slash_command("/skills --reload", cwd="/tmp/demo")

        self.assertEqual(result["command"], "skills")
        self.assertIn("playwright", result["message"])
        self.assertEqual(
            connection.request_calls[0],
            {
                "method": "skills/list",
                "params": {
                    "cwds": ["/tmp/demo"],
                    "forceReload": True,
                    "perCwdExtraUserRoots": None,
                },
            },
        )

    async def test_list_skills_without_cwd_uses_default_workspace(self) -> None:
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_dir = Path(temp_dir) / "workspace"
            service = CodexBridgeService(connection=connection, default_workspace_dir=workspace_dir)

            result = await service.list_skills()

        self.assertEqual(result["data"][0]["cwd"], str(workspace_dir.resolve()))
        self.assertEqual(
            connection.request_calls[0],
            {
                "method": "skills/list",
                "params": {
                    "cwds": [str(workspace_dir.resolve())],
                    "forceReload": False,
                    "perCwdExtraUserRoots": None,
                },
            },
        )

    async def test_exec_command_without_cwd_uses_default_workspace(self) -> None:
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_dir = Path(temp_dir) / "workspace"
            service = CodexBridgeService(connection=connection, default_workspace_dir=workspace_dir)

            result = await service.exec_command(["pwd"])

        self.assertEqual(result["cwd"], str(workspace_dir.resolve()))
        self.assertEqual(
            connection.request_calls[0],
            {
                "method": "command/exec",
                "params": {
                    "command": ["pwd"],
                    "cwd": str(workspace_dir.resolve()),
                    "timeoutMs": None,
                    "sandboxPolicy": None,
                },
            },
        )

    async def test_execute_slash_command_experimental_lists_features(self) -> None:
        connection = FakeConnection()
        service = CodexBridgeService(connection=connection)

        result = await service.execute_slash_command("/experimental --limit 5")

        self.assertEqual(result["command"], "experimental")
        self.assertIn("stream_review_mode", result["message"])
        self.assertEqual(
            connection.request_calls[0],
            {
                "method": "experimentalFeature/list",
                "params": {"cursor": None, "limit": 5},
            },
        )

    async def test_execute_slash_command_review_starts_detached_review(self) -> None:
        connection = FakeConnection()
        service = CodexBridgeService(connection=connection)

        result = await service.execute_slash_command(
            "/review --detached branch main",
            thread_id="thr_7",
        )

        self.assertEqual(result["command"], "review")
        self.assertEqual(result["threadId"], "thr_review")
        self.assertIn("detached review", result["message"])
        self.assertEqual(
            connection.request_calls[0],
            {
                "method": "review/start",
                "params": {
                    "threadId": "thr_7",
                    "target": {"type": "baseBranch", "branch": "main"},
                    "delivery": "detached",
                },
            },
        )
