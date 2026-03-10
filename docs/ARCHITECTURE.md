# Architecture

## Problem

The official Codex runtime is already highly capable on a local workstation, but difficult to consume programmatically from:

- mobile devices
- custom apps
- remote clients
- future personalized agents

This repository solves that by adapting the official `codex app-server` instead of rebuilding Codex.

## Core Principle

`codex-runtime-bridge` is an adapter, not a clone.

It should reuse:

- official auth
- official thread and turn semantics
- official event stream
- official command execution
- official tool and approval behavior

## Layers

```text
consumer
  |
  +-- CLI
  +-- HTTP client
  +-- future mobile/web app
  +-- future personal agent product
  |
  v
codex-runtime-bridge
  |
  +-- RPC transport
  +-- bridge service
  +-- HTTP API
  +-- CLI
  |
  v
codex app-server
  |
  v
Codex runtime on the machine
```

## Current Modules

- `rpc.py`
  - manages the `codex app-server` subprocess
  - sends JSON-RPC requests over stdio
  - receives responses and notifications

- `service.py`
  - maps bridge use cases onto upstream methods
  - examples:
    - `account/read`
    - `account/login/start`
    - `model/list`
    - `thread/start`
    - `turn/start`
    - `command/exec`

- `api.py`
  - exposes a simple HTTP layer on top of `service.py`

- `http_client.py`
  - client SDK for the HTTP layer

- `cli.py`
  - operational CLI for smoke testing and basic use

## Design Direction

This repository should evolve toward:

1. better coverage of upstream app-server methods
2. clearer event translation
3. better remote-operability guidance
4. stronger consumer interfaces

It should not evolve toward:

1. a second Codex runtime
2. a parallel auth/session/tool implementation
3. a highly opinionated end-user assistant product

