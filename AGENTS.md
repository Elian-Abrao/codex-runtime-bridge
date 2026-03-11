# AGENTS.md

## Purpose

This repository is a programmable bridge on top of the real `codex app-server`.

The primary user problem is:

- "I already use Codex on my machine every day"
- "I want to keep using that same runtime from other devices, including my phone"
- "I do not want to rebuild Codex just to expose it"

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
- safe access patterns for local and remote use

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
- Prefer exposing upstream semantics over inventing a new semantic layer unless the bridge UX clearly needs it.
- Do not document or implement direct unauthenticated public exposure as a recommended deployment pattern.
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
  transport/
    rpc.py
  bridge/
    commands/
    consumer_events.py
    events.py
    service.py
    translator.py
    workspace.py
  http/
    api.py
    client.py
    errors.py
    schemas.py
  cli/
    main.py
    render.py
tests/
```

## Deployment Stance

This repository is intended to make a privileged local Codex runtime reachable.

That means deployment guidance must assume:

- local-first execution
- remote access only through authenticated private networking or secure gateways

Recommended examples:

- Tailscale
- WireGuard
- SSH tunnels
- private reverse proxies with strong auth

Avoid presenting "open port to the internet" as an acceptable default.

## Validation

When changing this project:

1. install the package in a local venv
2. run unit tests
3. validate against the real `codex` binary when possible
4. validate both CLI and HTTP paths when changing bridge behavior

Typical commands:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -p 'test_*.py'
codex-runtime-bridge account
codex-runtime-bridge models
codex-runtime-bridge chat "Reply with OK only."
codex-runtime-bridge exec -- pwd
```

## Notes

- `codex app-server` is the upstream engine
- this repo is the adapter layer
- when no explicit `cwd` is provided, the bridge should use its dedicated default workspace rather than inheriting the repository directory
- if you find yourself rebuilding upstream runtime behavior here, stop and reassess
- a future personal agent product should consume this repository instead of replacing it
- slash commands in this repo should prefer thin handlers over recreating CLI-only behavior end to end
