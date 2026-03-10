from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from .parser import ParsedSlashCommand
from .parser import parse_slash_command

if TYPE_CHECKING:
    from ..service import CodexBridgeService


@dataclass(frozen=True)
class SlashCommandContext:
    thread_id: str | None = None
    cwd: str | Path | None = None
    model: str | None = None
    approval_policy: str | None = None
    sandbox: str | None = None
    personality: str | None = None
    ephemeral: bool | None = None


@dataclass(frozen=True)
class SlashCommandSpec:
    name: str
    usage: str
    summary: str
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "usage": self.usage,
            "summary": self.summary,
            "aliases": list(self.aliases),
        }


@dataclass(frozen=True)
class SlashCommandResult:
    name: str
    message: str
    data: Any = None
    thread_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.name,
            "message": self.message,
            "data": self.data,
            "threadId": self.thread_id,
        }


SlashCommandHandler = Callable[
    ["CodexBridgeService", ParsedSlashCommand, SlashCommandContext],
    Awaitable[SlashCommandResult],
]


@dataclass(frozen=True)
class RegisteredSlashCommand:
    spec: SlashCommandSpec
    handler: SlashCommandHandler


async def _handle_help(
    _: CodexBridgeService,
    command: ParsedSlashCommand,
    context: SlashCommandContext,
) -> SlashCommandResult:
    if command.args:
        raise ValueError("usage: /help")

    lines = ["Available slash commands:"]
    for spec in available_slash_commands():
        alias_suffix = ""
        if spec.aliases:
            alias_suffix = f" (aliases: {', '.join(f'/{alias}' for alias in spec.aliases)})"
        lines.append(f"{spec.usage}  {spec.summary}{alias_suffix}")

    return SlashCommandResult(
        name="help",
        message="\n".join(lines),
        data={"commands": [spec.to_dict() for spec in available_slash_commands()]},
        thread_id=context.thread_id,
    )


async def _handle_new(
    service: CodexBridgeService,
    command: ParsedSlashCommand,
    context: SlashCommandContext,
) -> SlashCommandResult:
    if command.args:
        raise ValueError("usage: /new")

    result = await service.start_thread(
        cwd=context.cwd,
        model=context.model,
        approval_policy=context.approval_policy,
        sandbox=context.sandbox,
        personality=context.personality,
        ephemeral=context.ephemeral,
    )
    thread = result["thread"]
    thread_id = thread["id"]
    return SlashCommandResult(
        name="new",
        message=f"Started new thread {thread_id}.",
        data=result,
        thread_id=thread_id,
    )


async def _handle_rename(
    service: CodexBridgeService,
    command: ParsedSlashCommand,
    context: SlashCommandContext,
) -> SlashCommandResult:
    if not context.thread_id:
        raise ValueError("/rename requires an active thread")

    name = " ".join(command.args).strip()
    if not name:
        raise ValueError("usage: /rename <name>")

    await service.set_thread_name(context.thread_id, name)
    return SlashCommandResult(
        name="rename",
        message=f"Renamed thread {context.thread_id} to {name!r}.",
        data={"name": name},
        thread_id=context.thread_id,
    )


async def _handle_skills(
    service: CodexBridgeService,
    command: ParsedSlashCommand,
    context: SlashCommandContext,
) -> SlashCommandResult:
    force_reload = False
    for argument in command.args:
        if argument == "--reload":
            force_reload = True
            continue
        raise ValueError("usage: /skills [--reload]")

    cwds = [context.cwd] if context.cwd else None
    result = await service.list_skills(cwds=cwds, force_reload=force_reload)
    entries = result.get("data", [])

    if not entries:
        message = "No skills found."
    else:
        lines: list[str] = []
        for entry in entries:
            cwd = entry.get("cwd") or "<default>"
            lines.append(f"Skills for {cwd}:")
            for skill in entry.get("skills", []):
                description = skill.get("shortDescription") or skill.get("description") or ""
                enabled_suffix = "" if skill.get("enabled", True) else " (disabled)"
                suffix = f" - {description}" if description else ""
                lines.append(f"- {skill['name']} [{skill['scope']}]{enabled_suffix}{suffix}")
            for error in entry.get("errors", []):
                lines.append(f"- error: {error['message']} ({error['path']})")
        message = "\n".join(lines)

    return SlashCommandResult(
        name="skills",
        message=message,
        data=result,
        thread_id=context.thread_id,
    )


async def _handle_logout(
    service: CodexBridgeService,
    command: ParsedSlashCommand,
    _: SlashCommandContext,
) -> SlashCommandResult:
    if command.args:
        raise ValueError("usage: /logout")

    result = await service.logout()
    return SlashCommandResult(
        name="logout",
        message="Logged out.",
        data=result,
        thread_id=None,
    )


_COMMANDS: dict[str, RegisteredSlashCommand] = {
    "help": RegisteredSlashCommand(
        spec=SlashCommandSpec(
            name="help",
            usage="/help",
            summary="Show available slash commands.",
        ),
        handler=_handle_help,
    ),
    "new": RegisteredSlashCommand(
        spec=SlashCommandSpec(
            name="new",
            usage="/new",
            summary="Start a new thread and switch to it.",
            aliases=("reset",),
        ),
        handler=_handle_new,
    ),
    "rename": RegisteredSlashCommand(
        spec=SlashCommandSpec(
            name="rename",
            usage="/rename <name>",
            summary="Rename the current thread.",
        ),
        handler=_handle_rename,
    ),
    "skills": RegisteredSlashCommand(
        spec=SlashCommandSpec(
            name="skills",
            usage="/skills [--reload]",
            summary="List skills available for the current workspace.",
        ),
        handler=_handle_skills,
    ),
    "logout": RegisteredSlashCommand(
        spec=SlashCommandSpec(
            name="logout",
            usage="/logout",
            summary="Log out from the current Codex account.",
        ),
        handler=_handle_logout,
    ),
}

_ALIASES = {
    alias: command_name
    for command_name, registered in _COMMANDS.items()
    for alias in registered.spec.aliases
}


def available_slash_commands() -> list[SlashCommandSpec]:
    return [registered.spec for registered in _COMMANDS.values()]


async def execute_slash_command(
    service: CodexBridgeService,
    text: str,
    context: SlashCommandContext,
) -> SlashCommandResult:
    parsed = parse_slash_command(text)
    canonical_name = _ALIASES.get(parsed.name, parsed.name)
    registered = _COMMANDS.get(canonical_name)
    if registered is None:
        raise ValueError(f"unknown slash command: /{parsed.name}")

    canonical_command = replace(parsed, name=canonical_name)
    return await registered.handler(service, canonical_command, context)
