from __future__ import annotations

import contextlib
import io
import unittest

from codex_runtime_bridge.cli import _ChatStreamPrinter


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
