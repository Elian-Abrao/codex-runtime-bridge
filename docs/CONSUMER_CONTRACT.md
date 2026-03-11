# Consumer Contract

This document defines the recommended contract for external consumers such as `codex-chat-gateway`.

The bridge now exposes two streaming shapes:

- `/v1/chat/stream`
  - raw bridge events
  - close to upstream `codex app-server` semantics
  - useful when the consumer wants full low-level fidelity

- `/v1/chat/consumer-stream`
  - stable projected events for downstream apps
  - recommended for gateways, bots, and remote clients

The bridge also exposes official thread lifecycle helpers that are useful for reconnect and recovery flows:

- `GET /v1/threads/{thread_id}`
  - thin wrapper over upstream `thread/read`
- `POST /v1/threads/{thread_id}/resume`
  - thin wrapper over upstream `thread/resume`

## Request Correlation

Every HTTP response includes `X-Request-ID`.

If the client sends `X-Request-ID`, the bridge reuses it.
Otherwise, the bridge generates one.

This applies to:

- normal JSON responses
- standardized error responses
- SSE responses

## Health Endpoints

- `GET /healthz`
  - liveness check
  - returns `{"ok": true}`

- `GET /readyz`
  - readiness check
  - returns the same payload as `/v1/health`

- `GET /v1/health`
  - structured bridge health

## Thread Recovery Endpoints

- `GET /v1/threads/{thread_id}`
  - returns the current thread snapshot without forcing it loaded

- `POST /v1/threads/{thread_id}/resume`
  - loads or refreshes the thread snapshot from the runtime
  - useful after a client reconnects or restarts and needs to inspect the latest completed turn

## Standard Error Shape

Non-streaming HTTP errors now use a stable envelope:

```json
{
  "error": {
    "code": "upstream_request_failed",
    "message": "account/read failed (-32000): boom",
    "details": {
      "method": "account/read",
      "upstreamError": {
        "code": -32000,
        "message": "boom"
      }
    },
    "requestId": "req_123"
  }
}
```

Current bridge-level error codes:

- `invalid_request`
- `http_error`
- `upstream_request_failed`
- `app_server_unavailable`
- `timeout`
- `internal_error`

## Stable Consumer Stream

`POST /v1/chat/consumer-stream`

Request body is the same as `/v1/chat` and `/v1/chat/stream`.

The response is `text/event-stream`.

Each SSE frame includes:

- `event: <stable_event_name>`
- `data: <json payload>`

Supported stable event names:

- `status`
- `commentary`
- `reasoning_summary`
- `action`
- `approval_request`
- `input_request`
- `final`
- `error`

### Event Shapes

`status`

```json
{
  "event": "status",
  "phase": "turn_started",
  "message": "Turn started.",
  "threadId": "thr_1",
  "turnId": "turn_1",
  "sourceType": "turn.started"
}
```

`commentary`

```json
{
  "event": "commentary",
  "text": "Checking the machine state now.",
  "threadId": "thr_1",
  "turnId": "turn_1"
}
```

`reasoning_summary`

```json
{
  "event": "reasoning_summary",
  "text": "Reviewing resource usage.",
  "threadId": "thr_1",
  "turnId": "turn_1"
}
```

`action`

```json
{
  "event": "action",
  "actionType": "command_execution",
  "text": "Executing command: pwd",
  "threadId": "thr_1",
  "turnId": "turn_1",
  "sourceType": "item/started",
  "details": {
    "item": {
      "type": "commandExecution",
      "id": "cmd_1",
      "command": "pwd"
    }
  }
}
```

`approval_request`

```json
{
  "event": "approval_request",
  "approvalType": "command_execution",
  "text": "Approval required for command execution.",
  "requestId": "req_1",
  "threadId": "thr_1",
  "turnId": "turn_1",
  "details": {
    "command": "rm -rf /tmp/demo"
  }
}
```

`final`

```json
{
  "event": "final",
  "text": "All good.",
  "attachments": [
    {
      "kind": "image",
      "localPath": "/tmp/screenshot.png",
      "fileName": "screenshot.png",
      "mimeType": "image/png",
      "sizeBytes": 42133
    }
  ],
  "threadId": "thr_1",
  "turnId": "turn_1"
}
```

The `final` event may include `attachments` when the assistant explicitly asks a downstream
consumer to send one or more existing local files. The bridge currently recognizes the
following directive when it appears on its own line in the assistant's final answer:

```text
[bridge-attachment path="/absolute/path/to/file.ext"]
```

The bridge strips those directive lines from `text` and exposes the normalized files through
`attachments`.

`error`

```json
{
  "event": "error",
  "code": "app_server_unavailable",
  "message": "codex app-server exited",
  "requestId": "req_123",
  "details": {
    "stderrTail": [
      "..."
    ]
  }
}
```

## Consumer Guidance

For external apps:

1. use `/readyz` for readiness probes
2. send `X-Request-ID` for traceability
3. prefer `/v1/chat/consumer-stream` over `/v1/chat/stream`
4. use `/v1/server-requests/respond` for approvals and other runtime requests
5. use `/v1/threads/{thread_id}/resume` when a client needs to recover the latest thread state after restart
6. keep `/v1/chat/stream` only for debugging or when raw event fidelity is required
