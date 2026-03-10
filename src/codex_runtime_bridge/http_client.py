from __future__ import annotations

from typing import Any

import httpx


class BridgeHttpClient:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        response = await self._client.get("/v1/health")
        response.raise_for_status()
        return response.json()

    async def account(self) -> dict[str, Any]:
        response = await self._client.get("/v1/account")
        response.raise_for_status()
        return response.json()

    async def start_login(self) -> dict[str, Any]:
        response = await self._client.post("/v1/login/chatgpt/start")
        response.raise_for_status()
        return response.json()

    async def logout(self) -> dict[str, Any]:
        response = await self._client.post("/v1/logout")
        response.raise_for_status()
        return response.json()

    async def models(self) -> dict[str, Any]:
        response = await self._client.get("/v1/models")
        response.raise_for_status()
        return response.json()

    async def start_thread(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self._client.post("/v1/threads/start", json=payload or {})
        response.raise_for_status()
        return response.json()

    async def chat(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        payload = {"prompt": prompt, **kwargs}
        response = await self._client.post("/v1/chat", json=payload)
        response.raise_for_status()
        return response.json()

    async def exec(self, command: list[str], **kwargs: Any) -> dict[str, Any]:
        payload = {"command": command, **kwargs}
        response = await self._client.post("/v1/command/exec", json=payload)
        response.raise_for_status()
        return response.json()

