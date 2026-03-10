# AGENTS.md

## Purpose

This repository is a programmable bridge on top of the real `codex app-server`.

The core rule for this codebase is:

- do not reimplement the Codex runtime when the official runtime already provides the capability

This project should prefer:

- adapting the official protocol
- exposing stable local interfaces
- keeping the bridge thin

This project should avoid:

- cloning Codex behavior in parallel
- rebuilding auth/session/tool runtimes from scratch
- turning the bridge into the final end-user product

## Product Boundaries

This repository should own:

- process management for `codex app-server`
- JSON-RPC transport handling
- API translation
- SDK ergonomics
- CLI for development and smoke tests

This repository should not own:

- a highly opinionated personal agent persona
- product-specific workflows for one user
- desktop/web UX for a final assistant app

Those belong in future consumer repositories.

## Engineering Rules

- Keep the bridge thin. Favor translation over reinvention.
- Prefer Python standard library unless an external dependency clearly improves delivery.
- Treat the official Codex runtime as the source of truth for auth, thread state, approvals, and tools.
- If a behavior differs from official Codex, document the bridge-specific behavior explicitly.
- Preserve a clean separation between:
  - transport/protocol code
  - bridge service methods
  - HTTP interface
  - CLI interface

## Current Layout

```text
src/codex_runtime_bridge/
  __init__.py
  __main__.py
  version.py
  rpc.py
  service.py
  api.py
  http_client.py
  cli.py
  schemas.py
tests/
```

## Validation

When changing this project:

1. install the package in a local venv
2. run unit tests
3. validate against the real `codex` binary when possible

Typical commands:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -p 'test_*.py'
codex-runtime-bridge account
codex-runtime-bridge models
```

## Notes

- `codex app-server` is the upstream engine
- this repo is the adapter layer
- if you find yourself rebuilding upstream runtime behavior here, stop and reassess

