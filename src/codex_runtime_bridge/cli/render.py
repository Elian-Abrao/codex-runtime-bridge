from __future__ import annotations

from typing import Any

from ..bridge import BridgeEvent


class ChatStreamPrinter:
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

    def _coerce_event(self, event: BridgeEvent | dict[str, Any]) -> tuple[str, dict[str, Any], str | int | None]:
        if isinstance(event, BridgeEvent):
            return event.type, event.payload, event.request_id if event.request_id is not None else None
        return event["type"], event.get("payload", {}), event.get("requestId")

    def _render_server_request(self, event_type: str, payload: dict[str, Any], request_id: str | int | None) -> None:
        self._reset_line()
        if event_type == "item/commandExecution/requestApproval":
            command = payload.get("command") or "<unknown command>"
            self._write(f"[approval] {command} (request {request_id})\n")
            return
        if event_type == "item/fileChange/requestApproval":
            self._write(f"[approval] file changes requested (request {request_id})\n")
            return
        if event_type == "item/tool/requestUserInput":
            self._write(f"[input] tool requested user input (request {request_id})\n")
            return
        if event_type == "item/tool/call":
            tool = payload.get("tool") or "<unknown tool>"
            self._write(f"[tool-call] {tool} (request {request_id})\n")
            return
        if event_type == "mcpServer/elicitation/request":
            self._write(f"[mcp] elicitation requested (request {request_id})\n")
            return
        if event_type == "account/chatgptAuthTokens/refresh":
            self._write(f"[auth] ChatGPT token refresh requested (request {request_id})\n")
            return
        self._write(f"[server-request] {event_type} (request {request_id})\n")

    def render(self, event: BridgeEvent | dict[str, Any]) -> None:
        event_type, payload, request_id = self._coerce_event(event)
        if request_id is not None:
            self._render_server_request(event_type, payload, request_id)
            return

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
