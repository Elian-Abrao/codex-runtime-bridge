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

## Sending Local Files Back To The User

- If the user asks you to send a local file or image back through a downstream client, add one directive line per file at the end of your final answer:
  `[bridge-attachment path="/absolute/path/to/file.ext"]`
- Use absolute filesystem paths only.
- Only reference files that already exist on disk.
- Keep any human-readable explanation outside the directive lines.

## Notes

- This workspace is safe to use for general assistant interactions.
- For project-specific coding tasks, the caller should pass an explicit `cwd`.
"""

_ATTACHMENT_SECTION_MARKER = "## Sending Local Files Back To The User"
_DEFAULT_WORKSPACE_MARKER = "This is the default workspace used by `codex-runtime-bridge`"
_ATTACHMENT_SECTION = """## Sending Local Files Back To The User

- If the user asks you to send a local file or image back through a downstream client, add one directive line per file at the end of your final answer:
  `[bridge-attachment path="/absolute/path/to/file.ext"]`
- Use absolute filesystem paths only.
- Only reference files that already exist on disk.
- Keep any human-readable explanation outside the directive lines.
"""


def _merge_default_agents_text(existing_text: str | None) -> str:
    if existing_text is None:
        return DEFAULT_WORKSPACE_AGENTS
    if _DEFAULT_WORKSPACE_MARKER not in existing_text:
        return existing_text
    if _ATTACHMENT_SECTION_MARKER in existing_text:
        return existing_text
    return existing_text.rstrip() + "\n\n" + _ATTACHMENT_SECTION.rstrip() + "\n"


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
    existing_text = agents_path.read_text(encoding="utf-8") if agents_path.exists() else None
    merged_text = _merge_default_agents_text(existing_text)
    if existing_text != merged_text:
        agents_path.write_text(merged_text, encoding="utf-8")

    return workspace_path
