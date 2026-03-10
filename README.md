# codex-runtime-bridge

`codex-runtime-bridge` is a thin programmable layer on top of the real `codex app-server`.

The goal is simple:

- keep using the official Codex runtime
- avoid reimplementing auth, sessions, tools, approvals, and agent behavior
- expose that runtime through:
  - a Python SDK
  - an HTTP API
  - a CLI

This repository is intentionally not a replacement for Codex itself. It is an adapter around the real Codex runtime already available through `codex app-server`.

## Status

This repository already provides a functional first vertical slice:

- start and manage a local `codex app-server` subprocess
- initialize the JSON-RPC session
- read account/auth state
- start ChatGPT login through Codex's native auth flow
- list models
- start threads
- run turns and stream turn events
- execute `command/exec`
- expose the same capabilities via CLI and HTTP

## Product Shape

This project is the reusable base layer.

It should contain:

- process management for the official Codex runtime
- protocol translation
- a stable API for other projects
- a Python SDK
- a thin CLI for development and testing

It should not become the final personal agent product. A future consumer repository can build a richer agent UX on top of this bridge.

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
```

Run a one-shot prompt:

```bash
codex-runtime-bridge chat "Reply with OK only."
```

Run an interactive chat loop:

```bash
codex-runtime-bridge chat --interactive
```

Execute one command through Codex's `command/exec`:

```bash
codex-runtime-bridge exec -- ls -la
```

Start the HTTP server:

```bash
codex-runtime-bridge serve
```

## HTTP API

Health:

```bash
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
    await client.close()


asyncio.run(main())
```

## Architecture

The current architecture is intentionally simple:

- `rpc.py`
  - stdio JSON-RPC client for `codex app-server`
- `service.py`
  - high-level bridge methods on top of the Codex runtime
- `api.py`
  - HTTP facade on top of the same service
- `http_client.py`
  - SDK client for the HTTP API
- `cli.py`
  - terminal UX for login, models, chat, exec, and serve

## Why this repository exists

The official Codex runtime already exposes:

- auth
- threads and turns
- streaming events
- command execution
- tools and approvals

Reimplementing all of that in another runtime is the wrong tradeoff.

This project exists to make the real Codex runtime easier to consume from applications, automations, and future agent products.

