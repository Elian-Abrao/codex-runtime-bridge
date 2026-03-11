from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import AsyncIterator
from typing import Literal

from ..transport import JsonDict
from .events import BridgeEvent

ConsumerEventName = Literal[
    "status",
    "commentary",
    "reasoning_summary",
    "action",
    "approval_request",
    "input_request",
    "final",
    "error",
]

COMMENTARY_CHUNK_TARGET = 120
REASONING_CHUNK_TARGET = 160


@dataclass(slots=True)
class ConsumerStreamEvent:
    event: ConsumerEventName
    thread_id: str | None = None
    turn_id: str | None = None
    request_id: str | int | None = None
    text: str | None = None
    message: str | None = None
    phase: str | None = None
    action_type: str | None = None
    approval_type: str | None = None
    code: str | None = None
    source_type: str | None = None
    details: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        data: JsonDict = {"event": self.event}
        if self.thread_id is not None:
            data["threadId"] = self.thread_id
        if self.turn_id is not None:
            data["turnId"] = self.turn_id
        if self.request_id is not None:
            data["requestId"] = self.request_id
        if self.text is not None:
            data["text"] = self.text
        if self.message is not None:
            data["message"] = self.message
        if self.phase is not None:
            data["phase"] = self.phase
        if self.action_type is not None:
            data["actionType"] = self.action_type
        if self.approval_type is not None:
            data["approvalType"] = self.approval_type
        if self.code is not None:
            data["code"] = self.code
        if self.source_type is not None:
            data["sourceType"] = self.source_type
        if self.details:
            data["details"] = self.details
        return data

    @classmethod
    def error_event(
        cls,
        *,
        code: str,
        message: str,
        request_id: str | None = None,
        details: JsonDict | None = None,
    ) -> ConsumerStreamEvent:
        return cls(
            event="error",
            code=code,
            message=message,
            request_id=request_id,
            details=details or {},
        )


@dataclass(slots=True)
class ConsumerEventProjector:
    commentary_chunk_target: int = COMMENTARY_CHUNK_TARGET
    reasoning_chunk_target: int = REASONING_CHUNK_TARGET
    _thread_id: str | None = None
    _turn_id: str | None = None
    _assistant_fragments: list[str] = field(default_factory=list)
    _commentary_buffer: str = ""
    _reasoning_buffer: str = ""
    _agent_message_phases: dict[str, str | None] = field(default_factory=dict)
    _emitted_thread_started: bool = False
    _emitted_turn_started: bool = False

    def _remember_ids(self, event: BridgeEvent) -> None:
        if event.thread_id is not None:
            self._thread_id = event.thread_id
        if event.turn_id is not None:
            self._turn_id = event.turn_id
        elif event.turn is not None:
            turn_id = event.turn.get("id")
            if isinstance(turn_id, str):
                self._turn_id = turn_id

    def _make_event(
        self,
        name: ConsumerEventName,
        *,
        text: str | None = None,
        message: str | None = None,
        phase: str | None = None,
        action_type: str | None = None,
        approval_type: str | None = None,
        source_type: str | None = None,
        request_id: str | int | None = None,
        details: JsonDict | None = None,
    ) -> ConsumerStreamEvent:
        return ConsumerStreamEvent(
            event=name,
            thread_id=self._thread_id,
            turn_id=self._turn_id,
            request_id=request_id,
            text=text,
            message=message,
            phase=phase,
            action_type=action_type,
            approval_type=approval_type,
            source_type=source_type,
            details=details or {},
        )

    def _flush_commentary(self, *, force: bool) -> ConsumerStreamEvent | None:
        chunk = self._commentary_buffer.strip()
        if not chunk:
            return None
        if not force and not (
            len(self._commentary_buffer) >= self.commentary_chunk_target
            or self._commentary_buffer.endswith((".", "!", "?", "\n", ":"))
        ):
            return None
        self._commentary_buffer = ""
        return self._make_event("commentary", text=chunk)

    def _flush_reasoning(self, *, force: bool) -> ConsumerStreamEvent | None:
        chunk = self._reasoning_buffer.strip()
        if not chunk:
            return None
        if not force and not (
            len(self._reasoning_buffer) >= self.reasoning_chunk_target
            or self._reasoning_buffer.endswith((".", "!", "?", "\n"))
        ):
            return None
        self._reasoning_buffer = ""
        return self._make_event("reasoning_summary", text=chunk)

    def push(self, event: BridgeEvent) -> list[ConsumerStreamEvent]:
        self._remember_ids(event)
        emitted: list[ConsumerStreamEvent] = []

        if event.type == "thread.started":
            if self._emitted_thread_started:
                return emitted
            self._emitted_thread_started = True
            emitted.append(
                self._make_event(
                    "status",
                    phase="thread_started",
                    message="Thread started.",
                    source_type=event.type,
                    details={"thread": event.payload.get("thread", {})},
                )
            )
            return emitted

        if event.type in {"turn.started", "turn/started"}:
            if self._emitted_turn_started:
                return emitted
            self._emitted_turn_started = True
            emitted.append(
                self._make_event(
                    "status",
                    phase="turn_started",
                    message="Turn started.",
                    source_type=event.type,
                    details={"turn": event.payload.get("turn", {})},
                )
            )
            return emitted

        if event.type == "item/started":
            item = event.item or {}
            item_type = item.get("type")
            item_id = item.get("id")
            if item_type == "agentMessage" and isinstance(item_id, str):
                phase = item.get("phase")
                self._agent_message_phases[item_id] = phase if isinstance(phase, str) else None
                return emitted

            if item_type == "commandExecution":
                maybe_commentary = self._flush_commentary(force=True)
                if maybe_commentary is not None:
                    emitted.append(maybe_commentary)
                maybe_reasoning = self._flush_reasoning(force=True)
                if maybe_reasoning is not None:
                    emitted.append(maybe_reasoning)
                emitted.append(
                    self._make_event(
                        "action",
                        text=f"Executing command: {item.get('command') or '<unknown command>'}",
                        action_type="command_execution",
                        source_type=event.type,
                        details={"item": item},
                    )
                )
                return emitted

            if item_type == "mcpToolCall":
                maybe_commentary = self._flush_commentary(force=True)
                if maybe_commentary is not None:
                    emitted.append(maybe_commentary)
                maybe_reasoning = self._flush_reasoning(force=True)
                if maybe_reasoning is not None:
                    emitted.append(maybe_reasoning)
                emitted.append(
                    self._make_event(
                        "action",
                        text=f"MCP tool call: {item.get('server') or '?'}/{item.get('tool') or '?'}",
                        action_type="mcp_tool_call",
                        source_type=event.type,
                        details={"item": item},
                    )
                )
                return emitted

            if item_type == "dynamicToolCall":
                maybe_commentary = self._flush_commentary(force=True)
                if maybe_commentary is not None:
                    emitted.append(maybe_commentary)
                maybe_reasoning = self._flush_reasoning(force=True)
                if maybe_reasoning is not None:
                    emitted.append(maybe_reasoning)
                emitted.append(
                    self._make_event(
                        "action",
                        text=f"Dynamic tool call: {item.get('tool') or '?'}",
                        action_type="dynamic_tool_call",
                        source_type=event.type,
                        details={"item": item},
                    )
                )
                return emitted

            if item_type == "fileChange":
                maybe_commentary = self._flush_commentary(force=True)
                if maybe_commentary is not None:
                    emitted.append(maybe_commentary)
                maybe_reasoning = self._flush_reasoning(force=True)
                if maybe_reasoning is not None:
                    emitted.append(maybe_reasoning)
                emitted.append(
                    self._make_event(
                        "action",
                        text="File changes prepared.",
                        action_type="file_change",
                        source_type=event.type,
                        details={"item": item},
                    )
                )
                return emitted

            return emitted

        if event.type == "item/agentMessage/delta":
            item_id = event.item_id
            delta = event.payload.get("delta")
            if not isinstance(item_id, str) or not isinstance(delta, str) or not delta:
                return emitted
            phase = self._agent_message_phases.get(item_id)
            if phase == "commentary":
                self._commentary_buffer += delta
                maybe_commentary = self._flush_commentary(force=False)
                if maybe_commentary is not None:
                    emitted.append(maybe_commentary)
                return emitted
            if phase in (None, "final_answer"):
                self._assistant_fragments.append(delta)
            return emitted

        if event.type == "item/reasoning/summaryTextDelta":
            delta = event.payload.get("delta")
            if isinstance(delta, str) and delta:
                self._reasoning_buffer += delta
                maybe_reasoning = self._flush_reasoning(force=False)
                if maybe_reasoning is not None:
                    emitted.append(maybe_reasoning)
            return emitted

        if event.type == "item/tool/call":
            maybe_commentary = self._flush_commentary(force=True)
            if maybe_commentary is not None:
                emitted.append(maybe_commentary)
            maybe_reasoning = self._flush_reasoning(force=True)
            if maybe_reasoning is not None:
                emitted.append(maybe_reasoning)
            tool_name = event.payload.get("tool") or "<unknown tool>"
            emitted.append(
                self._make_event(
                    "action",
                    text=f"Tool call requested: {tool_name}",
                    action_type="tool_call",
                    source_type=event.type,
                    request_id=event.request_id,
                    details=event.payload,
                )
            )
            return emitted

        if event.type == "item/commandExecution/requestApproval":
            maybe_commentary = self._flush_commentary(force=True)
            if maybe_commentary is not None:
                emitted.append(maybe_commentary)
            maybe_reasoning = self._flush_reasoning(force=True)
            if maybe_reasoning is not None:
                emitted.append(maybe_reasoning)
            emitted.append(
                self._make_event(
                    "approval_request",
                    text="Approval required for command execution.",
                    approval_type="command_execution",
                    source_type=event.type,
                    request_id=event.request_id,
                    details=event.payload,
                )
            )
            return emitted

        if event.type == "item/fileChange/requestApproval":
            maybe_commentary = self._flush_commentary(force=True)
            if maybe_commentary is not None:
                emitted.append(maybe_commentary)
            maybe_reasoning = self._flush_reasoning(force=True)
            if maybe_reasoning is not None:
                emitted.append(maybe_reasoning)
            emitted.append(
                self._make_event(
                    "approval_request",
                    text="Approval required for file changes.",
                    approval_type="file_change",
                    source_type=event.type,
                    request_id=event.request_id,
                    details=event.payload,
                )
            )
            return emitted

        if event.type == "item/tool/requestUserInput":
            maybe_commentary = self._flush_commentary(force=True)
            if maybe_commentary is not None:
                emitted.append(maybe_commentary)
            maybe_reasoning = self._flush_reasoning(force=True)
            if maybe_reasoning is not None:
                emitted.append(maybe_reasoning)
            emitted.append(
                self._make_event(
                    "input_request",
                    text="User input is required to continue.",
                    source_type=event.type,
                    request_id=event.request_id,
                    details=event.payload,
                )
            )
            return emitted

        if event.type == "turn/completed":
            maybe_commentary = self._flush_commentary(force=True)
            if maybe_commentary is not None:
                emitted.append(maybe_commentary)
            maybe_reasoning = self._flush_reasoning(force=True)
            if maybe_reasoning is not None:
                emitted.append(maybe_reasoning)
            final_text = "".join(self._assistant_fragments).strip()
            if final_text:
                emitted.append(
                    self._make_event(
                        "final",
                        text=final_text,
                        source_type=event.type,
                        details={"turn": event.turn or {}},
                    )
                )
            return emitted

        return emitted

    async def project(self, events: AsyncIterator[BridgeEvent]) -> AsyncIterator[ConsumerStreamEvent]:
        async for event in events:
            for projected in self.push(event):
                yield projected
