from __future__ import annotations

import asyncio
import inspect
from typing import Callable, Awaitable, Any

from .contracts import WorkerKind, WorkerProvider, WorkerRequest, WorkerResult


class FunctionWorkerProvider(WorkerProvider):
    """Runs bounded local CPU/GPU/file functions through the same provider contract."""
    def __init__(self, name: str, fn: Callable[[WorkerRequest], Any], *, kind: WorkerKind = WorkerKind.LOCAL, capabilities: frozenset[str] | None = None) -> None:
        if kind not in {WorkerKind.LOCAL, WorkerKind.FILE}:
            raise ValueError("FunctionWorkerProvider supports LOCAL or FILE kinds")
        self.name=name; self.fn=fn; self.kind=kind; self.capabilities=capabilities or frozenset({"general"})

    async def execute(self, request: WorkerRequest) -> WorkerResult:
        try:
            if inspect.iscoroutinefunction(self.fn):
                value = await self.fn(request)
            else:
                value = await asyncio.to_thread(self.fn, request)
            if isinstance(value, WorkerResult):
                return value
            if isinstance(value, dict):
                return WorkerResult(provider=self.name,kind=self.kind,text=str(value.get("text",value)),artifacts=list(value.get("artifacts",[])),metadata=dict(value.get("metadata",{})))
            return WorkerResult(provider=self.name,kind=self.kind,text=str(value))
        except Exception as exc:
            return WorkerResult(provider=self.name,kind=self.kind,success=False,error=f"{type(exc).__name__}: {exc}")
