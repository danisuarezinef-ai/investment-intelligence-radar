from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import types

ROOT = pathlib.Path(os.environ["CEO_W12_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.store import JsonCheckpointStore

WORK_MODE = ROOT / "scripts" / "ceo_stdlib_work_mode.py"
spec = importlib.util.spec_from_file_location("ceo_w12_work_mode", WORK_MODE)
if spec is None or spec.loader is None:
    raise RuntimeError("Unable to load work mode")
wm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wm)


class FakeProjects:
    def __init__(self, store: JsonCheckpointStore):
        self._store = store
        self.active = "active"
        self.touches = 0

    def store(self, project_id: str):
        return self._store

    def touch(self, state):
        self.touches += 1
        self._store.save(state)

    def set_active(self, project_id):
        self.active = project_id


class FakeLiveScheduler:
    def __init__(self, state, store, worker=None):
        self.state = state
        self.store = store
        self.worker = worker
        self.stop_calls = 0

    async def stop(self):
        self.stop_calls += 1
        for task in self.state.tasks.values():
            if task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.RETRY
                task.metadata["interrupted_by_shutdown"] = "w12"
                task.metadata["provider_stage"] = "interrupted"
        if self.worker is not None and not self.worker.done():
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        self.store.save(self.state)


class FakeRestartedScheduler:
    instances = []

    def __init__(self, state, decomposer, store, *, graph, router):
        self.state = state
        self.store = store
        self.graph = graph
        self.router = router
        self.started = False
        FakeRestartedScheduler.instances.append(self)

    def start(self):
        self.started = True


async def fake_snapshot(self):
    state = self._state_obj()
    return {
        "active": state is not None,
        "paused": bool(state.paused) if state is not None else False,
        "cancelled_at": str(state.cancelled_at) if state is not None and state.cancelled_at else None,
    }


def engine_for(state, store, scheduler):
    engine = wm.CEOEngine.__new__(wm.CEOEngine)
    engine.state = state
    engine.scheduler = scheduler
    engine.router = object() if scheduler is not None else None
    engine.projects = FakeProjects(store)
    engine.ContinuousScheduler = FakeRestartedScheduler
    engine.Graph = lambda: object()
    engine._router = types.MethodType(lambda self: {"kind": "w12-fake-router"}, engine)
    engine.snapshot = types.MethodType(fake_snapshot, engine)
    return engine


def state_with_tasks(*statuses):
    state = ProjectState(project_name="W12", goal="W12 operator controls")
    for idx, status in enumerate(statuses, start=1):
        task = Task(title=f"Execution {idx}", status=status)
        state.tasks[task.id] = task
        state.root_task_ids.append(task.id)
    return state


async def raw_pause_side_effect_case(tmp: pathlib.Path):
    state = state_with_tasks(TaskStatus.RUNNING)
    store = JsonCheckpointStore(tmp / "raw-pause.json")
    store.save(state)
    entered = asyncio.Event()
    release = asyncio.Event()
    target = tmp / "RAW_PAUSE_SIDE_EFFECT.txt"

    async def side_effect():
        entered.set()
        await release.wait()
        target.write_text("W12_RAW_EFFECT", encoding="utf-8")

    worker = asyncio.create_task(side_effect())
    scheduler = FakeLiveScheduler(state, store, worker)
    engine = engine_for(state, store, scheduler)
    await entered.wait()
    await engine.pause(True)
    release.set()
    await asyncio.sleep(0.05)
    row = {
        "paused": state.paused,
        "stop_calls": scheduler.stop_calls,
        "side_effect_exists": target.exists(),
        "task_status": next(iter(state.tasks.values())).status.value,
    }
    print("W12_RAW_PAUSE", json.dumps(row, sort_keys=True))
    assert state.paused is True
    assert scheduler.stop_calls == 0, row
    assert target.exists(), row
    return row


async def raw_resume_dead_case(tmp: pathlib.Path):
    state = state_with_tasks(TaskStatus.RETRY)
    state.paused = True
    state.metadata["operator_paused_v1"] = True
    store = JsonCheckpointStore(tmp / "raw-resume.json")
    store.save(state)
    engine = engine_for(state, store, None)
    FakeRestartedScheduler.instances.clear()
    await engine.pause(False)
    row = {
        "paused": state.paused,
        "scheduler_created": engine.scheduler is not None,
        "created_instances": len(FakeRestartedScheduler.instances),
    }
    print("W12_RAW_RESUME", json.dumps(row, sort_keys=True))
    assert state.paused is False
    assert engine.scheduler is None, row
    assert len(FakeRestartedScheduler.instances) == 0, row
    return row


async def patched_pause_resume_case(tmp: pathlib.Path):
    state = state_with_tasks(TaskStatus.RUNNING)
    task = next(iter(state.tasks.values()))
    store = JsonCheckpointStore(tmp / "patched-pause.json")
    store.save(state)
    entered = asyncio.Event()
    release = asyncio.Event()
    target = tmp / "PATCHED_PAUSE_SIDE_EFFECT.txt"

    async def side_effect():
        entered.set()
        await release.wait()
        target.write_text("MUST_NOT_HAPPEN_WHILE_PAUSED", encoding="utf-8")

    worker = asyncio.create_task(side_effect())
    scheduler = FakeLiveScheduler(state, store, worker)
    engine = engine_for(state, store, scheduler)
    await entered.wait()
    await engine.pause(True)
    release.set()
    await asyncio.sleep(0.05)

    paused_saved = store.load()
    assert paused_saved is not None
    row_pause = {
        "paused": state.paused,
        "stop_calls": scheduler.stop_calls,
        "side_effect_exists": target.exists(),
        "scheduler_is_none": engine.scheduler is None,
        "task_status": task.status.value,
        "quiesce": state.metadata.get("operator_pause_quiesce_v1"),
        "durable_paused": paused_saved.paused,
    }
    print("W12_PATCHED_PAUSE", json.dumps(row_pause, default=str, sort_keys=True))
    assert state.paused is True
    assert scheduler.stop_calls == 1, row_pause
    assert not target.exists(), row_pause
    assert engine.scheduler is None, row_pause
    assert task.status == TaskStatus.RETRY, row_pause
    assert paused_saved.paused is True, row_pause
    assert paused_saved.metadata.get("operator_paused_v1") is True

    # App restart must preserve the deliberate pause.
    reopened = JsonCheckpointStore.prepare_for_resume(paused_saved)
    assert reopened.paused is True
    assert reopened.metadata.get("operator_paused_v1") is True

    engine.state = reopened
    FakeRestartedScheduler.instances.clear()
    await engine.pause(False)
    row_resume = {
        "paused": reopened.paused,
        "scheduler_created": engine.scheduler is not None,
        "scheduler_started": bool(getattr(engine.scheduler, "started", False)),
        "instances": len(FakeRestartedScheduler.instances),
        "operator_paused_flag": reopened.metadata.get("operator_paused_v1"),
    }
    print("W12_PATCHED_RESUME", json.dumps(row_resume, default=str, sort_keys=True))
    assert reopened.paused is False, row_resume
    assert engine.scheduler is not None, row_resume
    assert engine.scheduler.started is True, row_resume
    assert len(FakeRestartedScheduler.instances) == 1, row_resume
    assert reopened.metadata.get("operator_paused_v1") is None, row_resume
    return row_pause, row_resume


async def cancel_terminal_case(tmp: pathlib.Path):
    state = state_with_tasks(TaskStatus.RUNNING, TaskStatus.WAITING, TaskStatus.COMPLETE)
    store = JsonCheckpointStore(tmp / "cancel.json")
    store.save(state)
    entered = asyncio.Event()
    release = asyncio.Event()
    target = tmp / "CANCEL_SIDE_EFFECT.txt"

    async def side_effect():
        entered.set()
        await release.wait()
        target.write_text("MUST_NOT_HAPPEN_AFTER_CANCEL", encoding="utf-8")

    worker = asyncio.create_task(side_effect())
    scheduler = FakeLiveScheduler(state, store, worker)
    engine = engine_for(state, store, scheduler)
    await entered.wait()
    await engine.cancel_project()
    release.set()
    await asyncio.sleep(0.05)

    saved = store.load()
    assert saved is not None
    statuses = [t.status.value for t in saved.tasks.values()]
    reopened = JsonCheckpointStore.prepare_for_resume(saved)
    row = {
        "cancelled_at": str(saved.cancelled_at),
        "cancelled_reason": saved.cancelled_reason,
        "paused": saved.paused,
        "autonomy_enabled": saved.autonomy_enabled,
        "statuses": statuses,
        "active_project": engine.projects.active,
        "engine_state_is_none": engine.state is None,
        "side_effect_exists": target.exists(),
        "restart_paused": reopened.paused,
        "restart_autonomy": reopened.autonomy_enabled,
    }
    print("W12_CANCEL_TERMINAL", json.dumps(row, default=str, sort_keys=True))
    assert saved.cancelled_at is not None, row
    assert saved.cancelled_reason == "operator_cancelled", row
    assert saved.paused is True and saved.autonomy_enabled is False, row
    assert statuses.count(TaskStatus.SUPERSEDED.value) == 2, row
    assert statuses.count(TaskStatus.COMPLETE.value) == 1, row
    assert engine.projects.active is None, row
    assert engine.state is None, row
    assert not target.exists(), row
    assert reopened.paused is True and reopened.autonomy_enabled is False, row
    return row


def package_hash(relative: str):
    contract = json.loads((ROOT / "CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8"))
    expected = str((contract.get("file_hashes") or {}).get(relative) or "")
    actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    assert expected and expected == actual, (relative, expected, actual)
    return actual


async def main_async():
    raw = os.environ.get("CEO_W12_EXPECT_RAW_BUG") == "1"
    with tempfile.TemporaryDirectory(prefix="ceo-w12-") as td:
        tmp = pathlib.Path(td)
        if raw:
            await raw_pause_side_effect_case(tmp)
            await raw_resume_dead_case(tmp)
            print("W12_RAW_PAUSE_RESUME_BUGS_REPRODUCED")
            return
        await patched_pause_resume_case(tmp)
        await cancel_terminal_case(tmp)


def main():
    asyncio.run(main_async())
    if os.environ.get("CEO_W12_EXPECT_RAW_BUG") == "1":
        return 0
    digest = package_hash("scripts/ceo_stdlib_work_mode.py")
    print("W12_PACKAGE_HASH", digest)
    print("W12_PAUSE_RESUME_CANCEL_REGRESSION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
