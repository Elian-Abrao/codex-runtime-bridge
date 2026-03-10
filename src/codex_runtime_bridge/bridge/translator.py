from __future__ import annotations

from ..transport import JsonDict
from .events import BridgeEvent


def _extract_thread_id(params: JsonDict) -> str | None:
    thread_id = params.get("threadId")
    if isinstance(thread_id, str):
        return thread_id
    return None


def _extract_turn_id(params: JsonDict) -> str | None:
    turn_id = params.get("turnId")
    if isinstance(turn_id, str):
        return turn_id
    turn = params.get("turn")
    if isinstance(turn, dict):
        turn_id = turn.get("id")
        if isinstance(turn_id, str):
            return turn_id
    return None


def translate_upstream_message(message: JsonDict) -> BridgeEvent | None:
    method = message.get("method")
    if not isinstance(method, str):
        return None

    params = message.get("params", {})
    if not isinstance(params, dict):
        params = {}

    request_id = message.get("id")
    kind = "server_request" if request_id is not None else "notification"
    return BridgeEvent(
        kind=kind,
        type=method,
        payload=params,
        thread_id=_extract_thread_id(params),
        turn_id=_extract_turn_id(params),
        request_id=request_id if kind == "server_request" else None,
    )
