from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from .ai_worker import AITransport, AITransportRequest, AITransportResponse
from .browser_worker import BrowserChatConfig, BrowserChatTransport
from .contracts import ProviderHealth, WorkerKind


class MultiProfileBrowserTransport(AITransport):
    """Scales one web service over multiple isolated persistent Chromium profiles."""
    kind = WorkerKind.BROWSER

    def __init__(self, base: BrowserChatConfig, profiles: int = 2) -> None:
        self.name = base.name
        self._queue: asyncio.Queue[BrowserChatTransport] = asyncio.Queue()
        root = Path(base.profile_dir)
        for i in range(max(1, profiles)):
            cfg = replace(base, profile_dir=str(root.parent / f"{root.name}-{i+1}"))
            self._queue.put_nowait(BrowserChatTransport(cfg))

    async def send(self, request: AITransportRequest) -> AITransportResponse:
        worker = await self._queue.get()
        try:
            return await worker.send(request)
        finally:
            self._queue.put_nowait(worker)

    async def healthcheck(self) -> ProviderHealth:
        worker = await self._queue.get()
        try:
            return await worker.healthcheck()
        finally:
            self._queue.put_nowait(worker)
