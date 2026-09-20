from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import time

GATE1_PATH = pathlib.Path(__file__).with_name("autonomy_bootstrap_gate_v1.py").resolve()
spec = importlib.util.spec_from_file_location("bootstrap_gate_v1_shared", GATE1_PATH)
gate1 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gate1)

TaskStatus = gate1.TaskStatus


class QuotaFlapProvider(gate1.WorkerProvider):
    name = "autonomy-bootstrap-quota-flap"
    kind = gate1.WorkerKind.MOCK
    capabilities = frozenset({"general", "research", "analysis", "writing", "verification", "local", "file"})

    def __init__(self, engine_getter, trip_after: int = 6):
        self.inner = gate1.GateProvider(engine_getter)
        self.trip_after = trip_after
        self.calls = 0
        self.outage = True
        self.quota_errors = 0

    def supports(self, task) -> bool:
        return True

    async def execute(self, request):
        self.calls += 1
        if self.outage and self.calls >= self.trip_after:
            self.quota_errors += 1
            raise RuntimeError("HTTP 429 RESOURCE_EXHAUSTED: quota exhausted for deterministic Gate 4 provider")
        return await self.inner.execute(request)


def clear_provider_wait(engine, provider):
    engine.execution_enabled = True
    engine.gemini_key_recognized = True
    engine.gemini_key_status = "LIVE_VERIFIED"
    engine.gemini_validation_error = None
    engine.provider_mode = "autonomy-bootstrap-quota-restored"
    state = engine.state
    state.metadata.pop("execution_disabled_reason", None)
    state.metadata.pop("provider_wait_v1", None)
    for task in state.leaf_tasks:
        if task.metadata.pop("waiting_provider_v1", None) is not None:
            task.metadata.pop("retry_after_ts", None)
            task.metadata.pop("provider_wait_category", None)
            if task.status == TaskStatus.BLOCKED:
                task.status = TaskStatus.WAITING
    engine.router = gate1.FixedWorkerRouter(provider)
    if engine.scheduler is not None:
        engine.scheduler.router = engine.router
        engine.scheduler.graph.refresh(state)
    engine.projects.store(state.id).save(state)


def metrics(state):
    wait = dict(state.metadata.get("provider_wait_v1") or {})
    return {
        "project_id": state.id,
        "completed_at": str(state.completed_at or ""),
        "audit": bool(state.metadata.get("goal_audit_passed")),
        "operator": state.metadata.get("operator_productivity_state"),
        "recoveries": int(state.metadata.get("worker_recoveries", 0) or 0),
        "provider_wait": wait,
        "waiting_provider_tasks": sum(bool(t.metadata.get("waiting_provider_v1")) for t in state.leaf_tasks),
        "productive_complete": sum(
            1 for t in state.leaf_tasks
            if not t.metadata.get("goal_continuity_audit")
            and t.status in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}
        ),
    }


def main() -> int:
    os.environ.setdefault("CEO_NO_BROWSER", "1")
    work = gate1.load_work_mode()
    engine = work.CEOEngine(None)

    provider = QuotaFlapProvider(lambda: engine, trip_after=6)
    engine.execution_enabled = True
    engine.gemini_key_recognized = True
    engine.gemini_key_status = "LIVE_VERIFIED"
    engine.provider_mode = "autonomy-bootstrap-quota-flap"
    engine.gemini_validation_error = None
    engine._router = lambda: gate1.FixedWorkerRouter(provider)

    engine.call(engine.start_project({
        "goal": "Create a short markdown resilience report named PROVIDER_GATE.md containing the phrase PROVIDER RESUME PASS and a one-line completion summary.",
        "name": "Autonomy Bootstrap Gate 4 Provider Outage",
        "power_percent": 20,
    }), timeout=60)

    # Wait for the injected 429 to be classified into provider wait.
    waiting = None
    deadline = time.monotonic() + 15
    timeline_pre = []
    while time.monotonic() < deadline:
        engine.call(engine.snapshot(), timeout=15)
        state = engine.state
        row = metrics(state)
        timeline_pre.append(row)
        wait = row["provider_wait"]
        if wait.get("active") and str(wait.get("category") or "").lower() == "quota":
            waiting = row
            break
        if state.completed_at is not None:
            raise AssertionError("goal completed before quota outage was exercised")
        time.sleep(0.1)

    assert waiting is not None, "429 did not produce provider wait"
    assert provider.quota_errors >= 1, "quota failure was not injected"
    assert waiting["recoveries"] == 0, f"quota wait consumed recoveries: {waiting}"
    assert int((waiting["provider_wait"] or {}).get("recoveries_consumed", 0) or 0) == 0
    assert waiting["waiting_provider_tasks"] >= 1
    project_id = engine.state.id
    completed_before = waiting["productive_complete"]
    print("PROVIDER_GATE_WAITING", json.dumps(waiting, default=str))

    # Hold the outage briefly and prove CEO does not churn recoveries.
    held = []
    hold_until = time.monotonic() + 2.0
    while time.monotonic() < hold_until:
        engine.call(engine.snapshot(), timeout=15)
        held.append(metrics(engine.state))
        time.sleep(0.15)
    assert all(r["recoveries"] == 0 for r in held), "recoveries increased during provider quota wait"

    # Provider becomes available. Model the same state transition as successful
    # provider revalidation, while keeping the real scheduler/project intact.
    provider.outage = False
    clear_provider_wait(engine, provider)
    engine.call(engine._ensure_scheduler_health(), timeout=20)

    terminal = None
    timeline_post = []
    finish_deadline = time.monotonic() + 30
    while time.monotonic() < finish_deadline:
        engine.call(engine.snapshot(), timeout=15)
        state = engine.state
        row = metrics(state)
        timeline_post.append(row)
        if state.completed_at is not None and state.metadata.get("goal_audit_passed"):
            terminal = row
            break
        time.sleep(0.2)

    state = engine.state
    unresolved = [d for d in state.decisions.values() if not d.resolved]
    artifacts = [
        str(a)
        for t in state.leaf_tasks
        for a in list(t.metadata.get("artifacts") or [])
        if pathlib.Path(str(a)).is_file()
    ]
    report = {
        "passed": terminal is not None,
        "project_id": state.id,
        "same_project": state.id == project_id,
        "quota_errors_injected": provider.quota_errors,
        "waiting_state": waiting,
        "held_samples": held[-10:],
        "terminal": terminal,
        "productive_completed_before_outage": completed_before,
        "productive_completed_final": metrics(state)["productive_complete"],
        "worker_recoveries_final": int(state.metadata.get("worker_recoveries", 0) or 0),
        "unresolved_human_decisions": len(unresolved),
        "artifact_count": len(artifacts),
        "goal_audit_passed": bool(state.metadata.get("goal_audit_passed")),
        "provider_wait_final": state.metadata.get("provider_wait_v1"),
        "timeline_post_tail": timeline_post[-15:],
    }
    print("AUTONOMY_BOOTSTRAP_GATE_4_REPORT")
    print(json.dumps(report, indent=2, default=str))

    try:
        engine.call(engine.shutdown(), timeout=20)
    except Exception as exc:
        print("shutdown_warning", type(exc).__name__, str(exc))

    assert terminal is not None, "project did not resume and complete after provider restoration"
    assert state.id == project_id, "provider recovery replaced the project"
    assert state.metadata.get("goal_audit_passed") is True
    assert int(state.metadata.get("worker_recoveries", 0) or 0) <= 2
    assert not unresolved
    assert artifacts
    assert metrics(state)["productive_complete"] > completed_before
    assert not (state.metadata.get("provider_wait_v1") or {}).get("active")
    print("AUTONOMY_BOOTSTRAP_GATE_4_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
