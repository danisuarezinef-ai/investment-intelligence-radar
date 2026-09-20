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


def configure_engine(engine, provider):
    engine.execution_enabled = True
    engine.gemini_key_recognized = True
    engine.provider_mode = "autonomy-bootstrap-gate"
    engine.gemini_key_status = "GATE_PROVIDER"
    engine.gemini_validation_error = None
    engine._router = lambda: gate1.FixedWorkerRouter(provider)


def state_metrics(state):
    return {
        "project_id": state.id,
        "completed_at": str(state.completed_at or ""),
        "goal_audit_passed": bool(state.metadata.get("goal_audit_passed")),
        "recoveries": int(state.metadata.get("worker_recoveries", 0) or 0),
        "productive_complete": sum(
            1 for t in state.leaf_tasks
            if not t.metadata.get("goal_continuity_audit")
            and t.status in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}
        ),
        "running": sum(t.status == TaskStatus.RUNNING for t in state.leaf_tasks),
        "ready": sum(t.status == TaskStatus.READY for t in state.leaf_tasks),
        "waiting": sum(t.status == TaskStatus.WAITING for t in state.leaf_tasks),
        "operator": state.metadata.get("operator_productivity_state"),
    }


def main() -> int:
    os.environ.setdefault("CEO_NO_BROWSER", "1")
    work = gate1.load_work_mode()

    engine1 = work.CEOEngine(None)
    provider1 = gate1.GateProvider(lambda: engine1)
    configure_engine(engine1, provider1)

    engine1.call(engine1.start_project({
        "goal": "Create a short markdown restart-resilience report named RESTART_GATE.md containing the phrase RESTART PASS and a short completion summary.",
        "name": "Autonomy Bootstrap Gate 3 Restart",
        "power_percent": 20,
    }), timeout=60)

    # Stop after measurable real progress but before final completion.
    deadline = time.monotonic() + 12
    before = None
    while time.monotonic() < deadline:
        engine1.call(engine1.snapshot(), timeout=15)
        state = engine1.state
        row = state_metrics(state)
        if row["productive_complete"] >= 5 and state.completed_at is None and not state.metadata.get("goal_audit_passed"):
            before = row
            break
        if state.completed_at is not None:
            raise AssertionError("goal completed before restart could be exercised")
        time.sleep(0.05)

    assert before is not None, "no measurable mid-goal progress before restart"
    original_project_id = engine1.state.id
    original_goal = engine1.state.goal
    calls_before_restart = provider1.calls
    print("RESTART_GATE_BEFORE", json.dumps(before, default=str))

    # Graceful application shutdown is the expected operator/system restart path.
    engine1.call(engine1.shutdown(), timeout=20)
    del engine1
    time.sleep(0.3)

    # New process-equivalent engine instance, same LOCALAPPDATA/APPDATA.
    engine2 = work.CEOEngine(None)
    provider2 = gate1.GateProvider(lambda: engine2)
    configure_engine(engine2, provider2)

    # Give _initialize a moment to restore the active project catalog entry.
    restore_deadline = time.monotonic() + 12
    restored = None
    while time.monotonic() < restore_deadline:
        try:
            engine2.call(engine2.snapshot(), timeout=15)
            state = engine2.state
            if state is not None and state.id == original_project_id:
                restored = state_metrics(state)
                break
        except Exception:
            pass
        time.sleep(0.1)

    assert restored is not None, "new CEO instance did not restore the active project"
    assert engine2.state.goal == original_goal, "restored goal changed"
    assert engine2.state.completed_at is None, "project falsely completed during restart"
    print("RESTART_GATE_RESTORED", json.dumps(restored, default=str))

    # Ensure the restored runtime uses the deterministic gate router and resumes.
    engine2.call(engine2._ensure_scheduler_health(), timeout=20)

    finish_deadline = time.monotonic() + 30
    terminal = None
    timeline = []
    while time.monotonic() < finish_deadline:
        engine2.call(engine2.snapshot(), timeout=15)
        state = engine2.state
        row = state_metrics(state)
        timeline.append(row)
        if state.completed_at is not None and state.metadata.get("goal_audit_passed"):
            terminal = row
            break
        if state.cancelled_at is not None:
            raise AssertionError("restored project became cancelled")
        time.sleep(0.2)

    state = engine2.state
    unresolved = [d for d in state.decisions.values() if not d.resolved]
    artifacts = [
        str(a)
        for t in state.leaf_tasks
        for a in list(t.metadata.get("artifacts") or [])
        if pathlib.Path(str(a)).is_file()
    ]
    report = {
        "passed": terminal is not None,
        "project_id_before": original_project_id,
        "project_id_after": state.id,
        "same_project": original_project_id == state.id,
        "before_restart": before,
        "restored": restored,
        "terminal": terminal,
        "provider_calls_before_restart": calls_before_restart,
        "provider_calls_after_restart": provider2.calls,
        "worker_recoveries": int(state.metadata.get("worker_recoveries", 0) or 0),
        "unresolved_human_decisions": len(unresolved),
        "artifact_count": len(artifacts),
        "goal_audit_passed": bool(state.metadata.get("goal_audit_passed")),
        "completed_at": str(state.completed_at or ""),
        "timeline_tail": timeline[-15:],
    }
    print("AUTONOMY_BOOTSTRAP_GATE_3_REPORT")
    print(json.dumps(report, indent=2, default=str))

    try:
        engine2.call(engine2.shutdown(), timeout=20)
    except Exception as exc:
        print("shutdown_warning", type(exc).__name__, str(exc))

    assert terminal is not None, "restored project did not autonomously complete"
    assert original_project_id == state.id, "restart created a replacement project instead of resuming"
    assert state.metadata.get("goal_audit_passed") is True
    assert int(state.metadata.get("worker_recoveries", 0) or 0) <= 2
    assert not unresolved
    assert artifacts
    assert provider2.calls > 0, "no productive work occurred after restart"
    print("AUTONOMY_BOOTSTRAP_GATE_3_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
