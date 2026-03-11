# codex-runtime-bridge

`codex-runtime-bridge` exposes the real Codex runtime running on your machine so you can use it from other applications, other devices, and future agent products.

This repository exists because the official Codex CLI is already extremely capable on a developer workstation, but it is still hard to use that same runtime from:

- a phone
- a web app
- a custom desktop app
- another local or remote service
- a future personalized agent product

The goal is not to replace Codex.

The goal is to make the real Codex runtime programmable and reachable.

## Core Idea

Instead of rebuilding auth, sessions, tools, approvals, and agent behavior from scratch, this project sits on top of the official `codex app-server` and provides:

- a Python SDK
- an HTTP API
- a thin CLI for testing and operations

So the architecture becomes:

```text
consumer app / phone / automation
        |
        v
codex-runtime-bridge
        |
        v
codex app-server
        |
        v
real Codex runtime on your machine
```

## Why This Exists

The primary pain this project solves is remote access to the Codex agent that already runs on your computer.

Example:

- you are away from home
- your workstation is still available
- you want to continue working from your phone
- you want the real Codex runtime to keep interacting with your machine
- you do not want to rebuild Codex just to expose it through an API

That is the main reason this repository exists.

The longer-term expansion is also clear:

- reuse the same bridge from many projects
- build richer agent products on top of it
- personalize workflows without forking or cloning the Codex runtime itself

## Product Boundaries

This repository **should** contain:

- process management for `codex app-server`
- JSON-RPC transport handling
- protocol translation
- a stable bridge API
- a Python SDK
- a thin CLI for operations and smoke tests

This repository **should not** become:

- a full replacement for the official Codex CLI
- a parallel reimplementation of the Codex runtime
- the final end-user personalized assistant product

Those richer products should consume this repository, not be merged into it.

## Current Status

The repository already has a functional first vertical slice:

- start and manage a local `codex app-server` subprocess
- initialize the JSON-RPC session
- read account/auth state
- start ChatGPT login through Codex's native auth flow
- list models from the real runtime
- start threads
- run turns and stream real turn events
- surface upstream server requests such as approvals and tool input prompts
- expose a first bridge-level slash command layer for interactive use
- execute `command/exec`
- expose a stable consumer-facing stream contract for downstream gateways
- expose the same capabilities through:
  - CLI
  - HTTP
  - Python SDK

## Requirements

- Python 3.11+
- `codex` available on `PATH`

Check:

```bash
command -v codex
codex app-server --help
```

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## CLI

Show account state:

```bash
codex-runtime-bridge account
```

Start ChatGPT login through the real Codex auth flow:

```bash
codex-runtime-bridge login
```

List models:

```bash
codex-runtime-bridge models
codex-runtime-bridge models --json
```

Run a one-shot prompt:

```bash
codex-runtime-bridge chat "Reply with OK only."
```

By default, terminal output is incremental when `--json` is not used.
Use `--no-stream` to wait for the full response before printing.

Run a streaming prompt:

```bash
codex-runtime-bridge chat --stream "Explain what you are doing in one sentence."
```

Request richer reasoning summaries when the upstream runtime emits them:

```bash
codex-runtime-bridge chat --summary detailed "Think step by step, then answer briefly."
```

Run an interactive chat loop:

```bash
codex-runtime-bridge chat --interactive
```

By default, chat and thread operations now use a dedicated bridge workspace instead of inheriting the shell directory where the bridge process was started. That workspace lives at:

- `CODEX_RUNTIME_BRIDGE_WORKSPACE_DIR`, if set
- otherwise `~/.local/share/codex-runtime-bridge/workspace`

The bridge bootstraps an `AGENTS.md` file there on first use. If you want Codex to operate inside a real project, pass `--cwd /path/to/project`.

Inside interactive chat, the bridge currently supports:

```text
/help
/new
/rename <name>
/skills [--reload]
/experimental [--limit <count>] [--cursor <cursor>]
/review [--detached] [branch <name> | commit <sha> | custom <instructions>]
/logout
```

Execute one command through Codex's `command/exec`:

```bash
codex-runtime-bridge exec -- ls -la
```

Start the HTTP server:

```bash
codex-runtime-bridge serve
```

Use a custom default bridge workspace:

```bash
CODEX_RUNTIME_BRIDGE_WORKSPACE_DIR=/path/to/blank-workspace codex-runtime-bridge serve
```

Use a non-default Codex binary:

```bash
CODEX_COMMAND=/path/to/codex codex-runtime-bridge account
```

## HTTP API

Health:

```bash
curl http://127.0.0.1:8787/healthz
curl http://127.0.0.1:8787/readyz
curl http://127.0.0.1:8787/v1/health
```

Account:

```bash
curl http://127.0.0.1:8787/v1/account
```

Start ChatGPT login:

```bash
curl -X POST http://127.0.0.1:8787/v1/login/chatgpt/start
```

List models:

```bash
curl http://127.0.0.1:8787/v1/models
```

Create a thread:

```bash
curl -X POST http://127.0.0.1:8787/v1/threads/start \
  -H 'Content-Type: application/json' \
  -d '{}'
```

When `cwd` is omitted, the thread starts in the dedicated bridge workspace rather than the bridge repository directory.

Run chat:

```bash
curl -X POST http://127.0.0.1:8787/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Reply with OK only."
  }'
```

Stream chat:

```bash
curl -N -X POST http://127.0.0.1:8787/v1/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Explain what you are doing in one short sentence."
  }'
```

Stable consumer stream for downstream apps such as `codex-chat-gateway`:

```bash
curl -N -X POST http://127.0.0.1:8787/v1/chat/consumer-stream \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: demo-consumer-1' \
  -d '{
    "prompt": "Reply with OK only."
  }'
```

The raw stream at `/v1/chat/stream` stays available, but new consumers should prefer
`/v1/chat/consumer-stream`.

Respond to an upstream server request such as an approval:

```bash
curl -X POST http://127.0.0.1:8787/v1/server-requests/respond \
  -H 'Content-Type: application/json' \
  -d '{
    "requestId": "req_1",
    "result": {
      "decision": "approve"
    }
  }'
```

## Consumer Contract

Recommended downstream-consumer behavior:

- use `/readyz` for readiness probes
- send `X-Request-ID` on every request
- prefer `/v1/chat/consumer-stream` over the raw stream
- treat `/v1/chat/stream` as a low-level compatibility path
- expect standardized error envelopes on non-streaming HTTP failures

Error shape:

```json
{
  "error": {
    "code": "upstream_request_failed",
    "message": "account/read failed (-32000): boom",
    "details": {
      "method": "account/read"
    },
    "requestId": "req_123"
  }
}
```

The full contract is documented in [docs/CONSUMER_CONTRACT.md](docs/CONSUMER_CONTRACT.md).

List the currently supported bridge slash commands:

```bash
curl http://127.0.0.1:8787/v1/slash-commands
```

Execute a slash command through the bridge:

```bash
curl -X POST http://127.0.0.1:8787/v1/slash-commands/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "command": "/skills"
  }'
```

List experimental features directly:

```bash
curl 'http://127.0.0.1:8787/v1/experimental-features?limit=10'
```

Start a review directly:

```bash
curl -X POST http://127.0.0.1:8787/v1/reviews/start \
  -H 'Content-Type: application/json' \
  -d '{
    "threadId": "thr_123",
    "target": {
      "type": "uncommittedChanges"
    },
    "delivery": "inline"
  }'
```

Exec:

```bash
curl -X POST http://127.0.0.1:8787/v1/command/exec \
  -H 'Content-Type: application/json' \
  -d '{
    "command": ["pwd"]
  }'
```

## Python SDK

Direct local use against the real `codex app-server`:

```python
import asyncio

from codex_runtime_bridge import CodexBridgeService


async def main() -> None:
    service = CodexBridgeService()
    account = await service.get_account()
    print(account)

    result = await service.chat("Reply with OK only.")
    print(result["assistantText"])

    await service.close()


asyncio.run(main())
```

HTTP client use against a running bridge server:

```python
import asyncio

from codex_runtime_bridge import BridgeHttpClient


async def main() -> None:
    client = BridgeHttpClient("http://127.0.0.1:8787")
    print(await client.health())
    print(await client.account())
    print(await client.chat("Reply with OK only."))
    async for event in client.stream_chat("Explain what you are doing in one short sentence."):
        print(event)
    await client.close()


asyncio.run(main())
```

## Architecture

The current implementation is intentionally thin:

- [`transport/rpc.py`](./src/codex_runtime_bridge/transport/rpc.py)
  - stdio JSON-RPC client for `codex app-server`
- [`bridge/service.py`](./src/codex_runtime_bridge/bridge/service.py)
  - bridge methods on top of the official runtime
- [`bridge/commands/`](./src/codex_runtime_bridge/bridge/commands)
  - slash command parsing, registry, and handlers on top of upstream RPC methods
- [`bridge/events.py`](./src/codex_runtime_bridge/bridge/events.py)
  - stable internal event model for streamed bridge activity
- [`bridge/translator.py`](./src/codex_runtime_bridge/bridge/translator.py)
  - translation from upstream JSON-RPC messages into bridge events
- [`http/api.py`](./src/codex_runtime_bridge/http/api.py)
  - HTTP facade on top of the same bridge service
- [`http/client.py`](./src/codex_runtime_bridge/http/client.py)
  - HTTP client SDK
- [`cli/main.py`](./src/codex_runtime_bridge/cli/main.py)
  - terminal UX for login, models, chat, exec, and serve
- [`cli/render.py`](./src/codex_runtime_bridge/cli/render.py)
  - terminal rendering for incremental chat events

Additional design documents:

- [Architecture](./docs/ARCHITECTURE.md)
- [Implementation Map](./docs/IMPLEMENTATION_MAP.md)
- [Deployment](./docs/DEPLOYMENT.md)
- [Roadmap](./docs/ROADMAP.md)

## Security

This bridge sits in front of a privileged local coding agent.

That means:

- it must be treated as sensitive infrastructure
- it should not be exposed directly to the public internet
- it should be placed behind a secure access layer when used remotely

Recommended patterns:

- Tailscale
- WireGuard
- SSH tunnel
- Cloudflare Access in front of a private service
- a private reverse proxy with strong authentication

Do **not** assume that “it is only a chat API”. The underlying runtime can operate on your machine through the real Codex runtime.

## Validation

Typical local validation:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -p 'test_*.py'
codex-runtime-bridge account
codex-runtime-bridge models --json
codex-runtime-bridge chat "Reply with OK only."
codex-runtime-bridge exec -- pwd
```

## Why This Is Better Than Rebuilding Codex

The official Codex runtime already provides:

- auth
- threads and turns
- streaming events
- command execution
- approvals
- tools
- MCP/app-server surfaces

Reimplementing all of that in a parallel runtime is the wrong tradeoff.

This repository exists to make the real runtime easier to consume, not to clone it.
