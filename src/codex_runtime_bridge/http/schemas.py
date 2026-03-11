from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = Field(default=None, alias="requestId")

    model_config = {"populate_by_name": True}


class ErrorEnvelope(BaseModel):
    error: ErrorInfo

    model_config = {"populate_by_name": True}


class HealthResponse(BaseModel):
    ok: bool
    codex_command: str = Field(alias="codexCommand")
    initialized: bool

    model_config = {"populate_by_name": True}


class ChatRequest(BaseModel):
    prompt: str
    thread_id: str | None = Field(default=None, alias="threadId")
    cwd: str | None = None
    model: str | None = None
    approval_policy: str | None = Field(default=None, alias="approvalPolicy")
    sandbox: str | None = None
    effort: str | None = None
    summary: str | None = None
    personality: str | None = None

    model_config = {"populate_by_name": True}


class ChatResponse(BaseModel):
    thread_id: str = Field(alias="threadId")
    turn_id: str = Field(alias="turnId")
    assistant_text: str = Field(alias="assistantText")
    turn: dict[str, Any]
    events: list[dict[str, Any]]

    model_config = {"populate_by_name": True}


class ThreadStartRequest(BaseModel):
    cwd: str | None = None
    model: str | None = None
    approval_policy: str | None = Field(default=None, alias="approvalPolicy")
    sandbox: str | None = None
    personality: str | None = None
    ephemeral: bool | None = None

    model_config = {"populate_by_name": True}


class CommandExecRequest(BaseModel):
    command: list[str]
    timeout_ms: int | None = Field(default=None, alias="timeoutMs")
    cwd: str | None = None
    sandbox_policy: dict[str, Any] | None = Field(default=None, alias="sandboxPolicy")

    model_config = {"populate_by_name": True}


class LoginStartResponse(BaseModel):
    type: str
    login_id: str | None = Field(default=None, alias="loginId")
    auth_url: str | None = Field(default=None, alias="authUrl")

    model_config = {"populate_by_name": True}


class ServerRequestResolveRequest(BaseModel):
    request_id: str | int = Field(alias="requestId")
    result: Any = None
    error: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class SlashCommandDefinition(BaseModel):
    name: str
    usage: str
    summary: str
    aliases: list[str] = Field(default_factory=list)


class SlashCommandListResponse(BaseModel):
    commands: list[SlashCommandDefinition]


class SlashCommandExecuteRequest(BaseModel):
    command: str
    thread_id: str | None = Field(default=None, alias="threadId")
    cwd: str | None = None
    model: str | None = None
    approval_policy: str | None = Field(default=None, alias="approvalPolicy")
    sandbox: str | None = None
    personality: str | None = None
    ephemeral: bool | None = None

    model_config = {"populate_by_name": True}


class SlashCommandExecuteResponse(BaseModel):
    command: str
    message: str
    data: Any = None
    thread_id: str | None = Field(default=None, alias="threadId")

    model_config = {"populate_by_name": True}


class ReviewStartRequest(BaseModel):
    thread_id: str = Field(alias="threadId")
    target: dict[str, Any]
    delivery: str | None = None

    model_config = {"populate_by_name": True}
