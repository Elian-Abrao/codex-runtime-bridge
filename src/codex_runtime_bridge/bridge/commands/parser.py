from __future__ import annotations

from dataclasses import dataclass
import shlex


@dataclass(frozen=True)
class ParsedSlashCommand:
    name: str
    args: list[str]
    raw: str


def parse_slash_command(text: str) -> ParsedSlashCommand:
    command_text = text.strip()
    if not command_text.startswith("/"):
        raise ValueError("slash commands must start with '/'")
    if command_text == "/":
        raise ValueError("slash command is empty")

    try:
        parts = shlex.split(command_text[1:])
    except ValueError as exc:
        raise ValueError(f"invalid slash command: {exc}") from exc
    if not parts:
        raise ValueError("slash command is empty")

    return ParsedSlashCommand(
        name=parts[0].lower(),
        args=parts[1:],
        raw=command_text,
    )
