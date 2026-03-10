from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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

