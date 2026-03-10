# Roadmap

## Product Direction

This repository is the reusable access layer for the real Codex runtime running on a machine you control.

The long-term vision is:

- local Codex runtime
- remotely reachable bridge
- future apps and agents built on top

## Current Phase

The current phase is a functional adapter:

- process management
- auth access
- models
- threads
- turns
- event streaming
- command execution
- CLI
- HTTP API

## Next Technical Steps

1. Cover more upstream app-server methods
   - thread resume
   - thread read
   - fork
   - turn interrupt
   - turn steer

2. Improve event handling
   - structured streaming contracts
   - better event filtering
   - tool and approval event surfacing

3. Improve remote access ergonomics
   - clearer deployment recipes
   - session-oriented APIs
   - long-lived mobile-friendly flows

4. Strengthen SDK ergonomics
   - higher-level thread abstraction
   - streaming helpers
   - approval handling surfaces

## Explicit Non-Goal

Do not rebuild the Codex runtime in this repository.

If a desired capability already exists in `codex app-server`, the preferred path is to adapt and expose it.

