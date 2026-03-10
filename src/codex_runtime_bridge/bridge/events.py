from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..transport import JsonDict

EventKind = Literal["synthetic", "notification", "server_request"]
RequestId = str | int


@dataclass(slots=True)
class BridgeEvent:
    kind: EventKind
    type: str
    payload: JsonDict
    thread_id: str | None = None
    turn_id: str | None = None
    request_id: RequestId | None = None

    @classmethod
    def thread_started(cls, thread_id: str, thread: JsonDict) -> BridgeEvent:
        return cls(
            kind="synthetic",
            type="thread.started",
            payload={"thread": thread},
            thread_id=thread_id,
        )

    @classmethod
    def turn_started(cls, thread_id: str, turn_id: str, turn: JsonDict) -> BridgeEvent:
        return cls(
            kind="synthetic",
            type="turn.started",
            payload={"turn": turn},
            thread_id=thread_id,
            turn_id=turn_id,
        )

    @property
    def item(self) -> JsonDict | None:
        item = self.payload.get("item")
        return item if isinstance(item, dict) else None

    @property
    def item_id(self) -> str | None:
        item = self.item
        if item is not None:
            item_id = item.get("id")
            return item_id if isinstance(item_id, str) else None
        item_id = self.payload.get("itemId")
        return item_id if isinstance(item_id, str) else None

    @property
    def turn(self) -> JsonDict | None:
        turn = self.payload.get("turn")
        return turn if isinstance(turn, dict) else None

    def to_dict(self) -> JsonDict:
        data: JsonDict = {"type": self.type}
        if self.thread_id is not None:
            data["threadId"] = self.thread_id
        if self.turn_id is not None:
            data["turnId"] = self.turn_id
        if self.request_id is not None:
            data["requestId"] = self.request_id

        if self.type == "thread.started":
            data["thread"] = self.payload["thread"]
            return data
        if self.type == "turn.started":
            data["turn"] = self.payload["turn"]
            return data

        data["payload"] = self.payload
        return data
