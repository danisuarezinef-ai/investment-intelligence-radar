from __future__ import annotations

import asyncio

from ceo_core.contracts import WorkerKind, WorkerProvider, WorkerRequest, WorkerResult


class MockWorkerProvider(WorkerProvider):
    name = "mock"
    kind = WorkerKind.MOCK
    capabilities = frozenset({"general"})

    def supports(self, task) -> bool:
        # The development mock intentionally accepts every task so architecture tests
        # never depend on a capability catalog.
        return True

    async def execute(self, request: WorkerRequest) -> WorkerResult:
        work = request.work_unit
        await asyncio.sleep(float(work.metadata.get("estimated_seconds", 0.01)))
        return WorkerResult(
            provider=self.name,
            kind=self.kind,
            text=f"Completed '{work.title}' for goal: {request.goal.objective}",
            success=True,
            conversation_id=request.conversation_id or f"mock-{work.id}",
            suggested_followups=[],
        )
