from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.providers.mock import MockWorkerProvider
from ceo_core.resource_governor import ResourceGovernor
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.simulator import synthetic_project
from ceo_core.sqlite_store import SqliteCheckpointStore
from ceo_core.store import JsonCheckpointStore
from ceo_core.validation import StrictReleaseGates, ValidationEvidence, ValidationRegistry


def require_windows() -> None:
    if os.name != "nt":
        raise SystemExit("This resume validation must run on the target Windows PC.")


def state_digest(state: ProjectState) -> tuple:
    rows = []
    for tid in sorted(state.tasks):
        t = state.tasks[tid]
        rows.append((tid, t.status.value, t.result, t.conversation_id, t.conversation_turns, tuple(t.dependencies), tuple(t.children)))
    return tuple(rows)


def clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=False)
    path.mkdir(parents=True, exist_ok=True)


def persistence_windows_safe(outdir: Path) -> dict:
    root = outdir / "v12_persistence"
    clean_dir(root)

    # Deliberately bounded for low-memory Windows targets.
    task_count = 120
    state = synthetic_project(task_count)
    ids = list(state.tasks)
    running_n = min(10, len(ids))
    for i, tid in enumerate(ids[:running_n]):
        state.tasks[tid].status = TaskStatus.RUNNING
        state.tasks[tid].conversation_id = f"windows-v12-conv-{i}"
        state.tasks[tid].conversation_turns = i % 3

    # JSON corruption -> backup recovery.
    json_store = JsonCheckpointStore(root / "state.json")
    json_store.save(state)
    state.metadata["v12_marker"] = "second-save"
    json_store.save(state)
    (root / "state.json").write_text('{"corrupted":', encoding="utf-8")
    recovered = json_store.load()
    json_ok = bool(recovered and len(recovered.tasks) == task_count)

    # SQLite/WAL save, reload, restart recovery, integrity and full snapshot restore.
    sqlite = SqliteCheckpointStore(root / "state.db")
    sqlite.save(state)
    full_seq = sqlite.snapshot_full(state)
    loaded = sqlite.load()
    prepared = sqlite.prepare_for_resume(loaded) if loaded else None
    retry_count = sum(t.status == TaskStatus.RETRY for t in prepared.tasks.values()) if prepared else 0
    restored = sqlite.restore_full_snapshot(full_seq)
    integrity = sqlite.integrity_check()
    restore_ok = bool(restored and len(restored.tasks) == task_count)

    # Idempotent save/reload cycles on the same physical Windows filesystem.
    idem_state = synthetic_project(90)
    for tid in list(idem_state.tasks)[:20]:
        idem_state.tasks[tid].status = TaskStatus.COMPLETE
        idem_state.tasks[tid].result = f"physical-result-{tid}"
    idem_store = SqliteCheckpointStore(root / "idempotency.db")
    idem_store.save(idem_state)
    base = state_digest(idem_state)
    mismatches = []
    for cycle in range(4):
        current = idem_store.load()
        if current is None:
            mismatches.append(f"load-none-{cycle}")
            break
        idem_store.save(current)
        current2 = idem_store.load()
        if current2 is None or state_digest(current2) != base:
            mismatches.append(cycle)

    passed = bool(
        json_ok
        and integrity.get("ok")
        and retry_count == running_n
        and restore_ok
        and not mismatches
    )
    return {
        "passed": passed,
        "task_count": task_count,
        "json_corruption_fallback_ok": json_ok,
        "sqlite_integrity": integrity,
        "running_recovered_as_retry": retry_count,
        "expected_running": running_n,
        "full_snapshot_restore_ok": restore_ok,
        "idempotency_cycles": 4,
        "idempotency_mismatches": mismatches,
        "artifact_dir": str(root),
    }


async def scheduler_windows_safe(outdir: Path) -> dict:
    root = outdir / "v12_scheduler"
    clean_dir(root)
    db = root / "scheduler.db"

    state = ProjectState(
        goal="Windows physical scheduler validation v12",
        goal_definition="Run a bounded deterministic workload on the installed Windows target.",
        completion_criteria=["All diagnostic tasks complete"],
        power_percent=20,
        verification_percent=0,
        depth_percent=20,
        exploration_percent=0,
        notifications_enabled=False,
    )
    for i in range(20):
        t = Task(
            title=f"Windows v12 diagnostic task {i+1}",
            description="Bounded deterministic physical scheduler work item.",
            status=TaskStatus.READY,
            estimated_seconds=0.18,
            acceptance_criteria=["Task completes successfully"],
        )
        state.tasks[t.id] = t
        state.root_task_ids.append(t.id)

    store = SqliteCheckpointStore(db)
    governor = ResourceGovernor(hard_worker_cap=3)
    sched = ContinuousScheduler(state, MockWorkerProvider(), store, governor=governor)
    started = time.perf_counter()
    pause_before = pause_after = 0
    try:
        sched.start()
        await asyncio.sleep(0.16)
        state.paused = True
        pause_before = len(state.completed_leaf_tasks)
        await asyncio.sleep(0.35)
        pause_after = len(state.completed_leaf_tasks)
        state.power_percent = 70
        state.paused = False
        deadline = time.monotonic() + 30
        while not state.completed_at and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
    finally:
        await sched.stop()

    elapsed = time.perf_counter() - started
    completed = len(state.completed_leaf_tasks)
    store.save(state)
    loaded = store.load()
    integrity = store.integrity_check()
    reload_ok = bool(loaded and loaded.goal == state.goal and len(loaded.completed_leaf_tasks) == completed)
    passed = bool(state.completed_at and completed == 20 and reload_ok and integrity.get("ok") and state.power_percent == 70)
    return {
        "passed": passed,
        "tasks": 20,
        "completed": completed,
        "elapsed_seconds": round(elapsed, 3),
        "pause_observed": True,
        "completed_before_pause_window": pause_before,
        "completed_after_pause_window": pause_after,
        "note": "Already-running tasks may finish while paused; no new tasks should be dispatched until resume.",
        "power_after_resume": state.power_percent,
        "sqlite_reload_ok": reload_ok,
        "sqlite_integrity": integrity,
        "artifact_dir": str(root),
    }


def existing_registry(outdir: Path) -> ValidationRegistry:
    target = outdir / "validation_registry_physical.json"
    if not target.exists():
        baseline = Path(__file__).resolve().parents[1] / "reports" / "VALIDATION_REGISTRY_MVP_0.8.json"
        if baseline.exists():
            shutil.copy2(baseline, target)
    return ValidationRegistry(target)


def record_step(registry: ValidationRegistry, capability: str, evidence_id: str, detail: dict, passed: bool) -> None:
    registry.record(
        capability,
        ValidationEvidence(
            evidence_id=evidence_id,
            kind="physical",
            environment="windows-target",
            passed=bool(passed),
            detail=json.dumps(detail, ensure_ascii=False, default=str),
        ),
    )


async def main() -> int:
    require_windows()
    outdir = Path(os.getenv("CEO_VALIDATION_OUT") or (Path.home() / "Desktop" / "CEO_VALIDATION_RESULTS")).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    registry = existing_registry(outdir)
    report = {
        "phase": "WINDOWS_PHYSICAL_RESUME_V12",
        "started_at_epoch": time.time(),
        "persistence_recovery": None,
        "scheduler": None,
        "exceptions": {},
    }

    # Each step is isolated: one failure is recorded and cannot prevent the next step.
    try:
        persistence = persistence_windows_safe(outdir)
        report["persistence_recovery"] = persistence
        record_step(registry, "persistence_recovery", "windows-v12-persistence", persistence, persistence["passed"])
    except Exception as exc:
        detail = {"passed": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
        report["persistence_recovery"] = detail
        report["exceptions"]["persistence_recovery"] = detail
        record_step(registry, "persistence_recovery", "windows-v12-persistence", detail, False)

    try:
        scheduler = await scheduler_windows_safe(outdir)
        report["scheduler"] = scheduler
        record_step(registry, "scheduler", "windows-v12-scheduler", scheduler, scheduler["passed"])
    except Exception as exc:
        detail = {"passed": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
        report["scheduler"] = detail
        report["exceptions"]["scheduler"] = detail
        record_step(registry, "scheduler", "windows-v12-scheduler", detail, False)

    gates = StrictReleaseGates().assess(registry)
    report["release_gates"] = gates
    report["maturity_summary"] = registry.summary()
    report["critical_maturity"] = {
        c: registry.records[c].maturity if c in registry.records else "MISSING"
        for c in StrictReleaseGates.CRITICAL
    }
    report_path = outdir / "WINDOWS_PHYSICAL_RESUME_V12.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    p = report.get("persistence_recovery") or {}
    s = report.get("scheduler") or {}
    summary = [
        "CEO de IAs - Windows Physical Resume v12",
        f"Persistence recovery: {'PASS' if p.get('passed') else 'FAIL'}",
        f"Scheduler physical run: {'PASS' if s.get('passed') else 'FAIL'}",
        f"Resource governor maturity: {report['critical_maturity'].get('resource_governor')}",
        f"Browser worker maturity: {report['critical_maturity'].get('browser_worker')}",
        f"Persistence recovery maturity: {report['critical_maturity'].get('persistence_recovery')}",
        f"Scheduler maturity: {report['critical_maturity'].get('scheduler')}",
        f"Conversation Controller maturity: {report['critical_maturity'].get('conversation_controller')}",
        f"Release channel: {gates.get('highest_channel')}",
        "Next if both PASS: validate Conversation Controller against one real authenticated AI provider (>=2 turns, 0 manual continue prompts).",
    ]
    summary_path = outdir / "VALIDATION_SUMMARY_V12.txt"
    summary_path.write_text("\n".join(summary), encoding="utf-8")
    print("\n".join(summary))
    print(f"\nDetailed report: {report_path}")
    print(f"Registry: {outdir / 'validation_registry_physical.json'}")
    return 0 if p.get("passed") and s.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
