from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path("/tmp/dev304")
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.graph import TaskGraph
from ceo_core.scheduler import ContinuousScheduler, _apply_reliability_epoch_migration, RELIABILITY_EPOCH
from ceo_core.productive_truth_v2 import ProductiveTruthV2
from ceo_core.routing import MultiProviderRouter
from ceo_core.contracts import WorkerProvider, WorkerKind

EXPECTED_VERSION = "1.5.80-rc1-provider-resilience"
EXPECTED_EPOCH = "dev304-provider-resilience-v1"


class MemoryStore:
    def __init__(self):
        self.last = None
    def save(self, state):
        self.last = state
    def append_event(self, *args, **kwargs):
        return None


class QuotaProvider(WorkerProvider):
    name = "quota-provider"
    kind = WorkerKind.API
    capabilities = frozenset({"general", "reasoning"})
    def supports(self, task):
        return True
    async def execute(self, request):
        raise RuntimeError("HTTP 429 RESOURCE_EXHAUSTED quota exceeded")


def assert_contract() -> None:
    contract = json.loads((ROOT / "CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8"))
    assert contract["app_version"] == EXPECTED_VERSION


def field_epoch_and_wait() -> None:
    s = ProjectState(goal="PRODUCTIVE_GATE_1 field regression", power_percent=20)
    for i in range(3):
        t = Task(title=f"done-{i}", status=TaskStatus.COMPLETE, metadata={"task_role": "productive"})
        s.tasks[t.id] = t
        s.root_task_ids.append(t.id)
    pending = []
    for title in ["Research & discovery", "Execution", "Verification", "Integration", "Final audit"]:
        t = Task(title=title, status=TaskStatus.BLOCKED, attempts=1, max_attempts=3, metadata={"task_role": "productive"})
        s.tasks[t.id] = t
        s.root_task_ids.append(t.id)
        pending.append(t)

    s.metadata["worker_recoveries"] = 637
    s.metadata["autonomy_recovery_tasks_created"] = 200
    s.metadata["reliability_epoch_v1"] = {"epoch": "dev303-productive-resume-v1"}
    s.metadata["productive_truth_v2"] = {
        "epoch": "dev303-productive-resume-v1",
        "productive_watermark": 3,
        "recoveries_at_watermark": 0,
        "status": "stalled",
        "stalled": True,
    }

    report = _apply_reliability_epoch_migration(s)
    assert RELIABILITY_EPOCH == EXPECTED_EPOCH
    assert report["changed"] is True
    assert s.metadata["worker_recoveries"] == 637

    truth = ProductiveTruthV2().assess(s)
    assert truth.worker_recoveries == 0, truth
    assert truth.stalled is False, truth

    s.metadata["provider_wait_v1"] = {
        "active": True,
        "category": "quota",
        "provider": "gemini-interactions",
        "retry_after_ts": time.time() + 300,
        "retry_after_seconds": 300,
        "recoveries_consumed": 0,
    }
    truth = ProductiveTruthV2().assess(s)
    assert truth.status == "waiting_provider", truth
    assert truth.stalled is False, truth

    p = pending[0]
    p.metadata["retry_after_ts"] = time.time() + 300
    TaskGraph().refresh(s)
    assert p.status == TaskStatus.BLOCKED

    again = _apply_reliability_epoch_migration(s)
    assert again["changed"] is False
    print("DEV304_FIELD_EPOCH_WAIT_PASS")


async def scheduler_quota_zero_recovery() -> None:
    s = ProjectState(goal="quota wait scheduler test", power_percent=10)
    t = Task(title="Research", status=TaskStatus.READY, metadata={"task_role": "productive"})
    s.tasks[t.id] = t
    s.root_task_ids.append(t.id)
    sched = ContinuousScheduler(s, None, MemoryStore(), graph=TaskGraph(), router=MultiProviderRouter([QuotaProvider()]))
    sched.start()
    for _ in range(100):
        await asyncio.sleep(0.05)
        if t.metadata.get("waiting_provider_v1"):
            break
    await sched.stop()
    assert t.metadata.get("waiting_provider_v1"), t.metadata
    assert t.metadata["waiting_provider_v1"]["category"] == "quota"
    assert t.status == TaskStatus.BLOCKED, t.status
    assert t.attempts == 0, t.attempts
    assert int(s.metadata.get("worker_recoveries", 0) or 0) == 0, s.metadata.get("worker_recoveries")
    assert s.metadata["provider_wait_v1"]["recoveries_consumed"] == 0
    print("DEV304_SCHEDULER_QUOTA_ZERO_RECOVERY_PASS")


def source_semantics() -> None:
    wm = (ROOT / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")
    sch = (ROOT / "ceo_core" / "scheduler.py").read_text(encoding="utf-8")
    gem = (ROOT / "ceo_core" / "providers" / "gemini_interactions.py").read_text(encoding="utf-8")
    obs = (ROOT / "ceo_core" / "observability.py").read_text(encoding="utf-8")
    truth = (ROOT / "ceo_core" / "productive_truth_v2.py").read_text(encoding="utf-8")
    assert "pre_scheduler_reliability_migration" in wm
    assert "ESPERANDO PROVEEDOR" in wm
    assert "start_stored_provider_revalidation_background" in wm
    assert "waiting_provider_v1" in sch
    assert "No recovery budget consumed" in sch
    assert "KNOWN_UNAVAILABLE_MODELS" in gem
    assert "waiting_provider" in obs
    assert "waiting_provider" in truth
    assert 'RELIABILITY_EPOCH = "dev304-provider-resilience-v1"' in sch
    print("DEV304_SOURCE_SEMANTICS_PASS")


def main() -> None:
    assert_contract()
    field_epoch_and_wait()
    asyncio.run(scheduler_quota_zero_recovery())
    source_semantics()
    print("DEV304_PROVIDER_RESILIENCE_QUALIFICATION_PASS")


if __name__ == "__main__":
    main()
