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
    chat_parser.add_argument("--personality")
    chat_parser.add_argument("--stream", action="store_true")

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


async def _run_chat_stream(service: CodexBridgeService, **kwargs: Any) -> dict[str, Any]:
    final: dict[str, Any] | None = None
    async for event in service.stream_turn(**kwargs):
        if event["type"] == "item/agentMessage/delta":
            print(event["payload"]["delta"], end="", flush=True)
        elif event["type"] == "turn.completed":
            final = event
    print()
    return final or {}


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

            result = await service.chat(
                prompt,
                thread_id=thread_id,
                cwd=args.cwd,
                model=args.model,
                approval_policy=args.approval_policy,
                sandbox=args.sandbox,
                effort=args.effort,
                personality=args.personality,
            )
            thread_id = result["threadId"]
            print(result["assistantText"])
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
            if args.stream and not args.json:
                await _run_chat_stream(
                    service,
                    prompt=args.prompt,
                    thread_id=args.thread_id,
                    cwd=args.cwd,
                    model=args.model,
                    approval_policy=args.approval_policy,
                    sandbox=args.sandbox,
                    effort=args.effort,
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
