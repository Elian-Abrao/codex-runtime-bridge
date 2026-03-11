from __future__ import annotations

import os
from pathlib import Path


DEFAULT_WORKSPACE_ENV = "CODEX_RUNTIME_BRIDGE_WORKSPACE_DIR"
DEFAULT_WORKSPACE_AGENTS = """# AGENTS.md

## Purpose

This is the default workspace used by `codex-runtime-bridge` when no explicit `cwd`
is provided.

It is intentionally sparse. It exists so the bridge does not accidentally start the
runtime inside its own source repository or another unrelated shell directory.

## Working Rules

- Prefer working inside this directory unless the user explicitly points you to a real project path.
- If a task clearly targets another repository or folder, ask for or use the correct `cwd`.
- Keep responses concise and practical.
- Use available tools when they are needed, but avoid making unrelated filesystem changes here.

## Notes

- This workspace is safe to use for general assistant interactions.
- For project-specific coding tasks, the caller should pass an explicit `cwd`.
"""


def resolve_default_workspace_dir(workspace_dir: str | Path | None = None) -> Path:
    if workspace_dir is not None:
        return Path(workspace_dir).expanduser().resolve()

    configured = os.environ.get(DEFAULT_WORKSPACE_ENV)
    if configured:
        return Path(configured).expanduser().resolve()

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        base_dir = Path(xdg_data_home).expanduser()
    else:
        base_dir = Path.home() / ".local" / "share"
    return (base_dir / "codex-runtime-bridge" / "workspace").resolve()


def ensure_default_workspace(workspace_dir: str | Path | None = None) -> Path:
    workspace_path = resolve_default_workspace_dir(workspace_dir)
    workspace_path.mkdir(parents=True, exist_ok=True)

    agents_path = workspace_path / "AGENTS.md"
    if not agents_path.exists():
        agents_path.write_text(DEFAULT_WORKSPACE_AGENTS, encoding="utf-8")

    return workspace_path
