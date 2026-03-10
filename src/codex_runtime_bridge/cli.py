from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import uvicorn

from .api import create_app
from .service import CodexBridgeService
from .version import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-runtime-bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--json", action="store_true", help="Emit JSON output when possible.")

    subparsers.add_parser("account", parents=[json_parent])
    subparsers.add_parser("models", parents=[json_parent])
    subparsers.add_parser("logout", parents=[json_parent])

    login_parser = subparsers.add_parser("login", parents=[json_parent])
    login_parser.add_argument("--no-browser", action="store_true")
    login_parser.add_argument("--timeout", type=float, default=300.0)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8787)

    chat_parser = subparsers.add_parser("chat", parents=[json_parent])
    chat_parser.add_argument("prompt", nargs="?")
    chat_parser.add_argument("--interactive", action="store_true")
    chat_parser.add_argument("--thread-id")
    chat_parser.add_argument("--cwd")
    chat_parser.add_argument("--model")
    chat_parser.add_argument("--approval-policy")
    chat_parser.add_argument("--sandbox")
    chat_parser.add_argument("--effort")
    chat_parser.add_argument("--summary", choices=["auto", "concise", "detailed", "none"])
    chat_parser.add_argument("--personality")
    chat_parser.add_argument("--stream", action="store_true", help="Force incremental terminal output.")
    chat_parser.add_argument("--no-stream", action="store_true", help="Wait for completion before printing.")

    exec_parser = subparsers.add_parser("exec", parents=[json_parent])
    exec_parser.add_argument("--cwd")
    exec_parser.add_argument("--timeout-ms", type=int)
    exec_parser.add_argument("argv", nargs=argparse.REMAINDER)

    version_parser = subparsers.add_parser("version", parents=[json_parent])
    version_parser.set_defaults(command="version")

    return parser


def _print(data: Any, *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    if isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


class _ChatStreamPrinter:
    def __init__(self) -> None:
        self._active_stream: tuple[str, str] | None = None
        self._line_open = False
        self._agent_phases: dict[str, str | None] = {}
        self._streamed_command_output: set[str] = set()

    def _write(self, text: str) -> None:
        if not text:
            return
        print(text, end="", flush=True)
        self._line_open = not text.endswith("\n")

    def _reset_line(self) -> None:
        if self._line_open:
            print()
        self._line_open = False
        self._active_stream = None

    def _begin_stream(self, key: tuple[str, str], prefix: str = "") -> None:
        if self._active_stream == key:
            return
        self._reset_line()
        if prefix:
            self._write(prefix)
        self._active_stream = key

    def _format_item_started(self, item: dict[str, Any]) -> None:
        item_type = item.get("type")
        item_id = item.get("id")
        if item_type == "agentMessage" and item_id:
            self._agent_phases[item_id] = item.get("phase")
            return
        if item_type == "commandExecution":
            self._reset_line()
            self._write(f"[exec] {item.get('command', '')}\n")
            return
        if item_type == "mcpToolCall":
            self._reset_line()
            server = item.get("server", "?")
            tool = item.get("tool", "?")
            self._write(f"[tool] {server}/{tool}\n")
            return
        if item_type == "dynamicToolCall":
            self._reset_line()
            self._write(f"[tool] {item.get('tool', '?')}\n")
            return
        if item_type == "fileChange":
            self._reset_line()
            self._write("[file-change]\n")

    def render(self, event: dict[str, Any]) -> None:
        event_type = event["type"]
        payload = event.get("payload", {})
        if event_type == "item/started":
            item = payload.get("item", {})
            if isinstance(item, dict):
                self._format_item_started(item)
            return

        if event_type == "item/agentMessage/delta":
            item_id = payload.get("itemId", "")
            phase = self._agent_phases.get(item_id)
            label = "[commentary] " if phase == "commentary" else "[assistant] "
            self._begin_stream(("agent", item_id), prefix=label)
            self._write(payload.get("delta", ""))
            return

        if event_type in {"item/reasoning/summaryTextDelta", "item/reasoning/textDelta"}:
            item_id = payload.get("itemId", "")
            self._begin_stream(("reasoning", item_id), prefix="[reasoning] ")
            self._write(payload.get("delta", ""))
            return

        if event_type == "item/plan/delta":
            item_id = payload.get("itemId", "")
            self._begin_stream(("plan", item_id), prefix="[plan] ")
            self._write(payload.get("delta", ""))
            return

        if event_type == "item/commandExecution/outputDelta":
            item_id = payload.get("itemId", "")
            self._streamed_command_output.add(item_id)
            self._begin_stream(("command", item_id))
            self._write(payload.get("delta", ""))
            return

        if event_type == "item/completed":
            item = payload.get("item", {})
            if not isinstance(item, dict):
                return
            if item.get("type") == "commandExecution":
                item_id = item.get("id", "")
                aggregated_output = item.get("aggregatedOutput") or ""
                if item_id not in self._streamed_command_output and aggregated_output:
                    self._begin_stream(("command", item_id))
                    self._write(aggregated_output)
                self._reset_line()
            return

        if event_type == "turn/completed":
            self._reset_line()

    def finish(self) -> None:
        self._reset_line()


async def _run_chat_stream(service: CodexBridgeService, **kwargs: Any) -> dict[str, Any]:
    printer = _ChatStreamPrinter()
    current_thread_id = kwargs.get("thread_id")
    current_turn_id: str | None = None
    final_turn: dict[str, Any] = {}
    assistant_fragments: list[str] = []
    agent_message_phases: dict[str, str | None] = {}
    async for event in service.stream_turn(**kwargs):
        printer.render(event)
        current_thread_id = event.get("threadId", current_thread_id)
        if event["type"] in {"turn.started", "turn/started"}:
            current_turn_id = event.get("turnId") or event.get("payload", {}).get("turn", {}).get("id")
        elif event["type"] == "item/started":
            item = event["payload"].get("item", {})
            if item.get("type") == "agentMessage":
                agent_message_phases[item["id"]] = item.get("phase")
        elif event["type"] == "item/agentMessage/delta":
            item_id = event["payload"].get("itemId")
            phase = agent_message_phases.get(item_id)
            if phase in (None, "final_answer"):
                assistant_fragments.append(event["payload"]["delta"])
        elif event["type"] == "turn/completed":
            final_turn = event["payload"].get("turn", {})
    printer.finish()
    return {
        "threadId": current_thread_id,
        "turnId": current_turn_id,
        "assistantText": "".join(assistant_fragments).strip(),
        "turn": final_turn,
    }


async def _interactive_chat(args: argparse.Namespace) -> int:
    service = CodexBridgeService()
    thread_id = args.thread_id
    print("Interactive chat")
    print("Commands: /help /reset /logout /exit")
    try:
        while True:
            prompt = input("bridge> ").strip()
            if not prompt:
                continue
            if prompt == "/exit":
                return 0
            if prompt == "/help":
                print("Commands: /help /reset /logout /exit")
                continue
            if prompt == "/reset":
                thread_id = None
                print("Thread reset.")
                continue
            if prompt == "/logout":
                await service.logout()
                print("Logged out.")
                return 0

            result = await _run_chat_stream(
                service,
                prompt=prompt,
                thread_id=thread_id,
                cwd=args.cwd,
                model=args.model,
                approval_policy=args.approval_policy,
                sandbox=args.sandbox,
                effort=args.effort,
                summary=args.summary,
                personality=args.personality,
            )
            thread_id = result["threadId"]
    finally:
        await service.close()


async def run_async(args: argparse.Namespace) -> int:
    if args.command == "serve":
        app = create_app()
        config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
        return 0

    if args.command == "version":
        _print(__version__, as_json=args.json)
        return 0

    if args.command == "chat" and args.interactive:
        return await _interactive_chat(args)

    service = CodexBridgeService()
    try:
        if args.command == "account":
            _print(await service.get_account(), as_json=args.json)
            return 0

        if args.command == "models":
            _print(await service.list_models(), as_json=args.json)
            return 0

        if args.command == "login":
            payload = await service.login_chatgpt(
                open_browser=not args.no_browser,
                timeout=args.timeout,
            )
            _print(payload, as_json=args.json)
            return 0

        if args.command == "logout":
            _print(await service.logout(), as_json=args.json)
            return 0

        if args.command == "chat":
            if not args.prompt:
                raise SystemExit("chat requires a prompt unless --interactive is used")
            should_stream = not args.json and not args.no_stream
            if args.stream:
                should_stream = True
            if should_stream:
                await _run_chat_stream(
                    service,
                    prompt=args.prompt,
                    thread_id=args.thread_id,
                    cwd=args.cwd,
                    model=args.model,
                    approval_policy=args.approval_policy,
                    sandbox=args.sandbox,
                    effort=args.effort,
                    summary=args.summary,
                    personality=args.personality,
                )
                return 0
            result = await service.chat(
                args.prompt,
                thread_id=args.thread_id,
                cwd=args.cwd,
                model=args.model,
                approval_policy=args.approval_policy,
                sandbox=args.sandbox,
                effort=args.effort,
                summary=args.summary,
                personality=args.personality,
            )
            if args.json:
                _print(result, as_json=True)
            else:
                print(result["assistantText"])
            return 0

        if args.command == "exec":
            raw_command = args.argv
            if raw_command and raw_command[0] == "--":
                raw_command = raw_command[1:]
            if not raw_command:
                raise SystemExit("exec requires a command after --")
            result = await service.exec_command(
                raw_command,
                cwd=args.cwd,
                timeout_ms=args.timeout_ms,
            )
            _print(result, as_json=args.json)
            return 0
    finally:
        await service.close()

    raise SystemExit(f"unknown command: {args.command}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run_async(args)))
