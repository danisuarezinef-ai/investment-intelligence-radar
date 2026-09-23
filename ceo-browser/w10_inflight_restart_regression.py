from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(os.environ["CEO_W10_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))
os.environ["CEO_W9_ROOT"] = str(ROOT)

from ceo_core.goal_lock_local_provider_v1 import GoalLockLocalProviderV1
from ceo_core.graph import TaskGraph
from ceo_core.local_finite_file_provider_v1 import LocalFiniteFileProviderV1
from ceo_core.models import ProjectState, TaskStatus
from ceo_core.progress_tracker import StableProgressTracker
from ceo_core.routing import MultiProviderRouter
from ceo_core.scheduler import ContinuousScheduler

# Reuse the already-qualified W9 state builder/store rather than recreating
# a second interpretation of the finite local contract.
W9_PATH = pathlib.Path(__file__).resolve().with_name("w9_local_finite_regression.py")
spec = importlib.util.spec_from_file_location("ceo_w9_regression", W9_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Unable to load W9 regression helpers")
w9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w9)

EXPECTED = w9.EXPECTED
TARGET = "CEO_LOCAL_W9.txt"


class PausingLocalFiniteProvider(LocalFiniteFileProviderV1):
    """Test-only provider that lets W10 stop CEO while Execution is RUNNING."""

    def __init__(self):
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.paused_task_id: str | None = None

    async def execute(self, request):
        mode = str(request.work_unit.metadata.get("local_finite_file_mode") or "")
        if mode == "write" and not self.entered.is_set():
            self.paused_task_id = request.work_unit.id
            self.entered.set()
            await self.release.wait()
        return await super().execute(request)


def leaves_by_prefix(state: ProjectState, prefix: str):
    low = prefix.lower()
    return [t for t in state.leaf_tasks if str(t.title or "").lower().startswith(low)]


async def wait_completed(state: ProjectState, timeout: float = 25.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if state.completed_at is not None:
            return
        bad = [t for t in state.leaf_tasks if t.status in {TaskStatus.FAILED, TaskStatus.NEEDS_REVIEW}]
        if bad:
            raise AssertionError([
                {"id": t.id, "title": t.title, "status": t.status.value, "result": t.result}
                for t in bad
            ])
        await asyncio.sleep(0.05)
    raise AssertionError({
        "reason": "W10 completion timeout",
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status.value,
                "provider": t.provider_name,
                "worker_id": t.worker_id,
                "metadata": {
                    k: v for k, v in (t.metadata or {}).items()
                    if k in {
                        "blocked_safe","blocked_safe_reason","blocked_safe_source",
                        "manual_release_required","worker_lease_v2","worker_lease_collision_v2",
                        "provider_stage","interrupted_by_shutdown","live_recovery_reason",
                        "recovery_strategy","strategy_change_requested","waiting_provider_v1",
                        "dispatch_token","resume_action","resume_reason",
                    }
                },
            }
            for t in state.leaf_tasks
        ],
        "resume_report": state.metadata.get("resume_coordinator_last") or state.metadata.get("application_recovery_last"),
        "scheduler_reconciler": state.metadata.get("scheduler_reconciler_last"),
        "worker_lifecycle": state.metadata.get("worker_lifecycle_v2_last"),
        "recovery_storm": state.metadata.get("recovery_storm_guard_last"),
        "completion": state.metadata.get("completion_assessment"),
        "provider_wait": state.metadata.get("provider_wait_v1"),
    })


def assert_final(state: ProjectState, workspace: pathlib.Path, initial_leaf_ids: set[str]) -> dict:
    target = workspace / TARGET
    assert target.is_file(), target
    assert target.read_text(encoding="utf-8") == EXPECTED
    digest = hashlib.sha256(target.read_bytes()).hexdigest()

    execution = leaves_by_prefix(state, "execution")
    final_audit = leaves_by_prefix(state, "final audit")
    goal_lock = leaves_by_prefix(state, "clarify & lock goal")
    assert len(execution) == 1, [(t.id, t.title, t.status.value) for t in state.leaf_tasks]
    assert len(final_audit) == 1, [(t.id, t.title, t.status.value) for t in state.leaf_tasks]
    assert len(goal_lock) == 1, [(t.id, t.title, t.status.value) for t in state.leaf_tasks]

    ex = execution[0]
    va = final_audit[0]
    assert ex.status == TaskStatus.COMPLETE, ex.status
    assert va.status == TaskStatus.COMPLETE, va.status
    assert state.completed_at is not None
    assert state.metadata.get("goal_audit_passed") is True

    progress = StableProgressTracker().snapshot(state, persist=True)
    assert float(progress.get("display_progress", -1)) == 100.0, progress
    assert int(progress.get("productive_pending", -1)) == 0, progress

    # Restart/reconciliation must not manufacture a second productive lineage.
    final_leaf_ids = {t.id for t in state.leaf_tasks}
    assert final_leaf_ids == initial_leaf_ids, {
        "initial": sorted(initial_leaf_ids),
        "final": sorted(final_leaf_ids),
        "tasks": [(t.id, t.title, t.status.value) for t in state.leaf_tasks],
    }

    writes = list(ex.metadata.get("workspace_writes_v1") or [])
    assert len(writes) == 2, writes
    assert writes[-1].get("sha256") == digest, writes

    verification = dict(va.metadata.get("verification_application") or {})
    assert verification.get("applied") is True, verification
    assert verification.get("verdict") == "pass", verification

    return {
        "completed_at": str(state.completed_at),
        "execution_id": ex.id,
        "execution_attempts": int(ex.attempts),
        "final_audit_id": va.id,
        "target_sha256": digest,
        "target_size": target.stat().st_size,
        "progress": progress,
        "writes": writes,
        "verification": verification,
        "leaf_ids": sorted(final_leaf_ids),
    }


async def clean_restart_case() -> dict:
    with tempfile.TemporaryDirectory(prefix="ceo-w10-clean-ws-") as ws_raw, tempfile.TemporaryDirectory(
        prefix="ceo-w10-clean-state-"
    ) as state_raw:
        workspace = pathlib.Path(ws_raw).resolve()
        state = w9.prepare_state(workspace)
        initial_leaf_ids = {t.id for t in state.leaf_tasks}
        execution = leaves_by_prefix(state, "execution")[0]
        execution_id = execution.id

        store = w9.JsonCheckpointStore(pathlib.Path(state_raw) / "state.json")
        store.save(state)
        pausing = PausingLocalFiniteProvider()
        scheduler = ContinuousScheduler(
            state, None, store, graph=TaskGraph(),
            router=MultiProviderRouter([GoalLockLocalProviderV1(), pausing]),
        )
        scheduler.start()
        await asyncio.wait_for(pausing.entered.wait(), timeout=10.0)

        assert pausing.paused_task_id == execution_id
        assert execution.status == TaskStatus.RUNNING, execution.status
        crash_blob = state.model_dump_json()

        # Clean shutdown must return the in-flight unit to a durable RETRY state.
        await scheduler.stop()
        persisted = store.load()
        assert persisted is not None
        persisted_execution = persisted.tasks[execution_id]
        assert persisted_execution.status == TaskStatus.RETRY, persisted_execution.status
        assert persisted_execution.metadata.get("interrupted_by_shutdown"), persisted_execution.metadata
        assert persisted_execution.metadata.get("provider_stage") == "interrupted", persisted_execution.metadata
        assert not (workspace / TARGET).exists(), "provider was interrupted before any write"

        # Same task id resumes and completes; no replacement/duplicate is permitted.
        resumed = persisted
        scheduler2 = ContinuousScheduler(
            resumed, None, store, graph=TaskGraph(),
            router=MultiProviderRouter([GoalLockLocalProviderV1(), LocalFiniteFileProviderV1()]),
        )
        scheduler2.start()
        await wait_completed(resumed)
        await scheduler2.stop()
        final = assert_final(resumed, workspace, initial_leaf_ids)
        assert final["execution_id"] == execution_id

        # The captured pre-stop blob is returned for the crash-like case contract.
        running_snapshot = ProjectState.model_validate_json(crash_blob)
        assert running_snapshot.tasks[execution_id].status == TaskStatus.RUNNING

        return {
            "interrupted_status": persisted_execution.status.value,
            "interrupted_provider_stage": persisted_execution.metadata.get("provider_stage"),
            "same_execution_id": final["execution_id"] == execution_id,
            "final": final,
        }


async def crash_restart_case() -> dict:
    with tempfile.TemporaryDirectory(prefix="ceo-w10-crash-ws-") as ws_raw, tempfile.TemporaryDirectory(
        prefix="ceo-w10-crash-state-"
    ) as state_raw:
        workspace = pathlib.Path(ws_raw).resolve()
        state = w9.prepare_state(workspace)
        initial_leaf_ids = {t.id for t in state.leaf_tasks}
        execution = leaves_by_prefix(state, "execution")[0]
        execution_id = execution.id

        # Build a realistic persisted RUNNING checkpoint by allowing goal-lock
        # to finish and pausing exactly inside the productive provider call.
        store_live = w9.JsonCheckpointStore(pathlib.Path(state_raw) / "live.json")
        store_live.save(state)
        pausing = PausingLocalFiniteProvider()
        live = ContinuousScheduler(
            state, None, store_live, graph=TaskGraph(),
            router=MultiProviderRouter([GoalLockLocalProviderV1(), pausing]),
        )
        live.start()
        await asyncio.wait_for(pausing.entered.wait(), timeout=10.0)
        assert state.tasks[execution_id].status == TaskStatus.RUNNING
        crash_blob = state.model_dump_json()

        # Clean up only the test's live asyncio objects. The blob above intentionally
        # preserves the pre-cleanup RUNNING state to represent process/Windows loss.
        await live.stop()

        crashed = ProjectState.model_validate_json(crash_blob)
        crashed_execution = crashed.tasks[execution_id]
        assert crashed_execution.status == TaskStatus.RUNNING

        # Simulate a partially materialized file left by an abrupt process loss.
        partial = workspace / TARGET
        partial.write_text("[W10_PARTIAL_FROM_CRASH]", encoding="utf-8")
        partial_sha = hashlib.sha256(partial.read_bytes()).hexdigest()

        crash_store = w9.JsonCheckpointStore(pathlib.Path(state_raw) / "crash.json")
        crash_store.save(crashed)

        # Merely constructing the real scheduler must reconcile stale RUNNING.
        restarted = crash_store.load()
        assert restarted is not None
        scheduler2 = ContinuousScheduler(
            restarted, None, crash_store, graph=TaskGraph(),
            router=MultiProviderRouter([GoalLockLocalProviderV1(), LocalFiniteFileProviderV1()]),
        )
        reconciled = restarted.tasks[execution_id]
        assert reconciled.status != TaskStatus.RUNNING, {
            "status": reconciled.status.value,
            "resume_report": getattr(scheduler2, "_resume_report", None),
            "metadata": reconciled.metadata,
        }
        assert reconciled.status in {TaskStatus.RETRY, TaskStatus.READY}, reconciled.status
        assert reconciled.worker_id in {None, ""}, reconciled.worker_id
        rr_before = getattr(scheduler2, "_resume_report", None)
        if hasattr(rr_before, "to_dict"):
            rr_before = rr_before.to_dict()
        print("W10_CRASH_RECONCILED", json.dumps({
            "status": reconciled.status.value,
            "worker_id": reconciled.worker_id,
            "metadata": reconciled.metadata,
            "resume_report": rr_before,
        }, ensure_ascii=False, default=str, sort_keys=True))

        scheduler2.start()
        await wait_completed(restarted)
        await scheduler2.stop()

        final = assert_final(restarted, workspace, initial_leaf_ids)
        assert final["execution_id"] == execution_id
        assert final["target_sha256"] != partial_sha
        assert partial.read_text(encoding="utf-8") == EXPECTED

        resume_report = getattr(scheduler2, "_resume_report", None)
        if hasattr(resume_report, "to_dict"):
            resume_report = resume_report.to_dict()

        return {
            "stale_status_before_init": TaskStatus.RUNNING.value,
            "reconciled_status": reconciled.status.value,
            "partial_sha256": partial_sha,
            "resume_report": resume_report,
            "same_execution_id": final["execution_id"] == execution_id,
            "final": final,
        }


async def main_async() -> dict:
    for key in (
        "OPENAI_API_KEY","GEMINI_API_KEY","GOOGLE_API_KEY","ANTHROPIC_API_KEY",
        "PERPLEXITY_API_KEY","XAI_API_KEY",
    ):
        os.environ.pop(key, None)
    os.environ["CEO_ALLOW_OPTIONAL_API"] = "0"

    clean = await clean_restart_case()
    print("W10_CLEAN_RESTART_PASS", json.dumps(clean, ensure_ascii=False, default=str, sort_keys=True))
    crash = await crash_restart_case()
    return {"clean_restart": clean, "crash_restart": crash, "api_env_present": False}


def main() -> int:
    result = asyncio.run(main_async())
    print("W10_RESTART_E2E", json.dumps(result, ensure_ascii=False, default=str, sort_keys=True))
    print("W10_RESTART_REGRESSION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
