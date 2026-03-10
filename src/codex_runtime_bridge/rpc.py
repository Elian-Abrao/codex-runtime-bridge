from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .version import __version__

JsonDict = dict[str, Any]


class AppServerProcessError(RuntimeError):
    pass


class JsonRpcRequestError(RuntimeError):
    def __init__(self, method: str, error: JsonDict) -> None:
        self.method = method
        self.error = error
        code = error.get("code")
        message = error.get("message", "unknown error")
        super().__init__(f"{method} failed ({code}): {message}")


@dataclass(slots=True)
class AppServerOptions:
    codex_command: str = os.environ.get("CODEX_COMMAND", "codex")
    listen_url: str = "stdio://"
    client_name: str = "codex_runtime_bridge"
    client_title: str = "Codex Runtime Bridge"
    client_version: str = __version__
    experimental_api: bool = True


class AppServerConnection:
    def __init__(self, options: AppServerOptions | None = None) -> None:
        self.options = options or AppServerOptions()
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future[JsonDict]] = {}
        self._write_lock = asyncio.Lock()
        self._started = False
        self._subscriptions: set[asyncio.Queue[JsonDict]] = set()
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._initialized = False
        self._initialize_lock = asyncio.Lock()
        self._recent_stderr: list[str] = []

    @property
    def codex_command(self) -> str:
        return self.options.codex_command

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def recent_stderr(self) -> list[str]:
        return list(self._recent_stderr)

    async def start(self) -> None:
        if self._started:
            return

        command = [
            *shlex.split(self.options.codex_command),
            "app-server",
            "--listen",
            self.options.listen_url,
        ]

        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_stdout(), name="app-server-stdout")
        self._stderr_task = asyncio.create_task(self._read_stderr(), name="app-server-stderr")
        self._started = True

    async def ensure_initialized(self) -> None:
        if self._initialized:
            return
        async with self._initialize_lock:
            if self._initialized:
                return
            await self.start()
            await self._request_internal(
                "initialize",
                {
                    "clientInfo": {
                        "name": self.options.client_name,
                        "title": self.options.client_title,
                        "version": self.options.client_version,
                    },
                    "capabilities": {
                        "experimentalApi": self.options.experimental_api,
                    },
                },
                ensure_initialized=False,
            )
            await self.notify("initialized")
            self._initialized = True

    def subscribe(self) -> asyncio.Queue[JsonDict]:
        queue: asyncio.Queue[JsonDict] = asyncio.Queue()
        self._subscriptions.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[JsonDict]) -> None:
        self._subscriptions.discard(queue)

    async def request(self, method: str, params: JsonDict | None = None) -> JsonDict:
        return await self._request_internal(method, params=params, ensure_initialized=True)

    async def _request_internal(
        self,
        method: str,
        params: JsonDict | None = None,
        *,
        ensure_initialized: bool,
    ) -> JsonDict:
        if ensure_initialized:
            await self.ensure_initialized()
        else:
            await self.start()
        self._request_id += 1
        request_id = self._request_id
        loop = asyncio.get_running_loop()
        future: asyncio.Future[JsonDict] = loop.create_future()
        self._pending[request_id] = future
        await self._send_message(
            {
                "id": request_id,
                "method": method,
                "params": params or {},
            }
        )
        message = await future
        if "error" in message:
            raise JsonRpcRequestError(method, message["error"])
        return message["result"]

    async def notify(self, method: str, params: JsonDict | None = None) -> None:
        await self.start()
        message: JsonDict = {"method": method}
        if params is not None:
            message["params"] = params
        await self._send_message(message)

    async def close(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

        for task in (self._reader_task, self._stderr_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        if self._process:
            if self._process.returncode is None:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except (asyncio.TimeoutError, ProcessLookupError):
                    self._process.kill()
                    with contextlib.suppress(ProcessLookupError):
                        await self._process.wait()
            self._process = None
        self._started = False
        self._initialized = False

    async def _send_message(self, message: JsonDict) -> None:
        if not self._process or not self._process.stdin:
            raise AppServerProcessError("app-server process is not running")
        payload = json.dumps(message, ensure_ascii=True) + "\n"
        async with self._write_lock:
            self._process.stdin.write(payload.encode("utf-8"))
            await self._process.stdin.drain()

    async def _read_stdout(self) -> None:
        if not self._process or not self._process.stdout:
            raise AppServerProcessError("missing app-server stdout pipe")

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                message = json.loads(line.decode("utf-8"))
                if "id" in message and ("result" in message or "error" in message):
                    request_id = int(message["id"])
                    future = self._pending.pop(request_id, None)
                    if future and not future.done():
                        future.set_result(message)
                    continue

                if "method" in message:
                    for queue in tuple(self._subscriptions):
                        queue.put_nowait(message)
        finally:
            error = AppServerProcessError("codex app-server exited")
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)
            self._pending.clear()

    async def _read_stderr(self) -> None:
        if not self._process or not self._process.stderr:
            return

        while True:
            line = await self._process.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            self._recent_stderr.append(text)
            if len(self._recent_stderr) > 200:
                self._recent_stderr = self._recent_stderr[-200:]


def normalize_cwd(value: str | Path | None) -> str | None:
    if value is None:
        return None
    return str(Path(value).expanduser().resolve())
