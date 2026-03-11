from __future__ import annotations

import argparse
import contextlib
import io
import unittest
from unittest import mock

from codex_runtime_bridge.bridge import BridgeEvent
from codex_runtime_bridge.cli import _ChatStreamPrinter
from codex_runtime_bridge.cli.main import main
from codex_runtime_bridge.cli.main import _interactive_chat


class ChatStreamPrinterTests(unittest.TestCase):
    def test_printer_renders_incremental_sections(self) -> None:
        printer = _ChatStreamPrinter()
        output = io.StringIO()
        events = [
            {
                "type": "item/started",
                "payload": {
                    "item": {
                        "type": "agentMessage",
                        "id": "commentary_1",
                        "phase": "commentary",
                    }
                },
            },
            {
                "type": "item/agentMessage/delta",
                "payload": {
                    "itemId": "commentary_1",
                    "delta": "Checking files",
                },
            },
            {
                "type": "item/started",
                "payload": {
                    "item": {
                        "type": "commandExecution",
                        "id": "cmd_1",
                        "command": "ls",
                    }
                },
            },
            {
                "type": "item/completed",
                "payload": {
                    "item": {
                        "type": "commandExecution",
                        "id": "cmd_1",
                        "aggregatedOutput": "README.md\n",
                    }
                },
            },
            {
                "type": "item/started",
                "payload": {
                    "item": {
                        "type": "agentMessage",
                        "id": "final_1",
                        "phase": "final_answer",
                    }
                },
            },
            {
                "type": "item/agentMessage/delta",
                "payload": {
                    "itemId": "final_1",
                    "delta": "Done",
                },
            },
            {"type": "turn/completed", "payload": {}},
        ]

        with contextlib.redirect_stdout(output):
            for event in events:
                printer.render(event)
            printer.finish()

        self.assertEqual(
            output.getvalue(),
            "[commentary] Checking files\n[exec] ls\nREADME.md\n[assistant] Done\n",
        )

    def test_printer_renders_server_requests(self) -> None:
        printer = _ChatStreamPrinter()
        output = io.StringIO()
        event = BridgeEvent(
            kind="server_request",
            type="item/commandExecution/requestApproval",
            payload={"command": "git push"},
            thread_id="thr_1",
            turn_id="turn_1",
            request_id="req_7",
        )

        with contextlib.redirect_stdout(output):
            printer.render(event)
            printer.finish()

        self.assertEqual(output.getvalue(), "[approval] git push (request req_7)\n")


class InteractiveChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_interactive_chat_routes_slash_commands_through_service(self) -> None:
        output = io.StringIO()

        class FakeService:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def execute_slash_command(self, command: str, **kwargs: object) -> dict[str, object]:
                self.calls.append({"command": command, "kwargs": kwargs})
                return {
                    "command": "new",
                    "message": "Started new thread thr_new.",
                    "data": {"thread": {"id": "thr_new"}},
                    "threadId": "thr_new",
                }

            async def close(self) -> None:
                return None

        fake_service = FakeService()
        args = argparse.Namespace(
            thread_id=None,
            cwd="/tmp/demo",
            model=None,
            approval_policy=None,
            sandbox=None,
            effort=None,
            summary=None,
            personality=None,
        )
        user_input = iter(["/new", "/exit"])

        with (
            contextlib.redirect_stdout(output),
            mock.patch("builtins.input", side_effect=lambda _: next(user_input)),
        ):
            result = await _interactive_chat(args, service=fake_service)

        self.assertEqual(result, 0)
        self.assertEqual(
            fake_service.calls,
            [
                {
                    "command": "/new",
                    "kwargs": {
                        "thread_id": None,
                        "cwd": "/tmp/demo",
                        "model": None,
                        "approval_policy": None,
                        "sandbox": None,
                        "personality": None,
                    },
                }
            ],
        )
        self.assertIn("Started new thread thr_new.", output.getvalue())


class MainEntrypointTests(unittest.TestCase):
    def test_main_suppresses_keyboard_interrupt_traceback(self) -> None:
        def fake_asyncio_run(coro):
            coro.close()
            raise KeyboardInterrupt

        with (
            mock.patch("argparse.ArgumentParser.parse_args", return_value=argparse.Namespace(command="serve")),
            mock.patch("asyncio.run", side_effect=fake_asyncio_run),
        ):
            with self.assertRaises(SystemExit) as raised:
                main()

        self.assertEqual(raised.exception.code, 130)
