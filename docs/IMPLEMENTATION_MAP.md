# Implementation Map

This document maps the architectural cleanup in three concrete steps and the
adjustments made to the repository.

## Step 1: Typed Bridge Events

Goal:

- stop treating streamed turn activity as anonymous dictionaries
- create a stable internal event model for bridge consumers

Implementation:

- `src/codex_runtime_bridge/bridge/events.py`
  - introduces `BridgeEvent`
  - keeps `type`, `thread_id`, `turn_id`, `payload`, and `request_id`
  - preserves the existing wire shape through `to_dict()`

Decision:

- keep the external stream payload compatible with the previous API
- use typed events internally, convert to dictionaries only at interface edges

## Step 2: Translation Layer

Goal:

- separate upstream JSON-RPC message parsing from bridge orchestration
- keep service logic focused on use cases rather than protocol decoding

Implementation:

- `src/codex_runtime_bridge/bridge/translator.py`
  - translates upstream notifications and server requests into `BridgeEvent`

- `src/codex_runtime_bridge/bridge/service.py`
  - adds `stream_turn_events()` as the typed stream
  - keeps `stream_turn()` as the legacy dictionary stream for compatibility
  - updates `chat()` to aggregate from typed events instead of raw dictionaries

Decision:

- `stream_turn_events()` is now the internal source of truth
- `stream_turn()` remains as a compatibility adapter, not the primary model

## Step 3: Bidirectional Server Requests

Goal:

- surface approvals, tool calls, and other server-initiated requests
- provide a generic response channel back to `codex app-server`

Implementation:

- `src/codex_runtime_bridge/transport/rpc.py`
  - adds `respond()` for JSON-RPC responses initiated by the client

- `src/codex_runtime_bridge/bridge/service.py`
  - adds `respond_server_request()`
  - adds convenience helpers for:
    - command execution approvals
    - file change approvals
    - tool input responses
    - dynamic tool responses
    - MCP elicitation responses
    - ChatGPT auth refresh responses

- `src/codex_runtime_bridge/http/api.py`
  - adds `POST /v1/server-requests/respond`

- `src/codex_runtime_bridge/http/client.py`
  - adds `respond_server_request()`

- `src/codex_runtime_bridge/cli/render.py`
  - renders server requests explicitly in terminal output

Decision:

- expose a generic response endpoint instead of inventing many bridge-specific flows
- keep upstream request methods visible in the event stream

## Repository Adjustments

- `transport/` owns process and JSON-RPC transport
- `bridge/` owns event translation and bridge service methods
- `http/` owns FastAPI, schemas, and the async HTTP client
- `cli/` owns command routing and terminal rendering

## Compatibility Policy

- top-level imports remain stable:
  - `from codex_runtime_bridge import CodexBridgeService`
  - `from codex_runtime_bridge import BridgeHttpClient`

- stream consumers can keep using dictionary events via `stream_turn()`
- new internal consumers should prefer `stream_turn_events()`
