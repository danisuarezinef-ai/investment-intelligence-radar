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


def main() -> int:
    os.environ.setdefault("CEO_NO_BROWSER", "1")
    work = gate1.load_work_mode()
    engine = work.CEOEngine(None)
    provider = gate1.GateProvider(lambda: engine)

    engine.execution_enabled = True
    engine.provider_mode = "autonomy-bootstrap-gate"
    engine.gemini_key_status = "GATE_PROVIDER"
    engine.gemini_validation_error = None
    engine._router = lambda: gate1.FixedWorkerRouter(provider)

    started = time.monotonic()
    engine.call(engine.start_project({
        "goal": "Create a short markdown status note named EFFICIENCY_GATE.md containing the phrase EFFICIENCY PASS and one sentence summarizing the result.",
        "name": "Autonomy Bootstrap Gate 5 Efficiency",
        "power_percent": 20,
    }), timeout=60)

    initial_leaf_count = len(engine.state.leaf_tasks)
    initial_root_count = len(engine.state.root_task_ids)
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        engine.call(engine.snapshot(), timeout=15)
        state = engine.state
        if state.completed_at is not None and state.metadata.get("goal_audit_passed"):
            break
        time.sleep(0.15)

    state = engine.state
    unresolved = [d for d in state.decisions.values() if not d.resolved]
    artifacts = [
        str(a)
        for t in state.leaf_tasks
        for a in list(t.metadata.get("artifacts") or [])
        if pathlib.Path(str(a)).is_file()
    ]
    verification_passes = [
        t for t in state.leaf_tasks
        if isinstance(t.metadata.get("verification_application"), dict)
        and str((t.metadata.get("verification_application") or {}).get("verdict") or "").lower() == "pass"
    ]
    report = {
        "passed_completion": state.completed_at is not None and bool(state.metadata.get("goal_audit_passed")),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "initial_leaf_count": initial_leaf_count,
        "initial_root_count": initial_root_count,
        "final_leaf_count": len(state.leaf_tasks),
        "provider_calls": provider.calls,
        "audit_calls": provider.audit_calls,
        "worker_recoveries": int(state.metadata.get("worker_recoveries", 0) or 0),
        "unresolved_human_decisions": len(unresolved),
        "artifact_count": len(artifacts),
        "verification_passes": len(verification_passes),
        "decomposition_profile": state.metadata.get("decomposition_profile"),
        "goal_audit_passed": bool(state.metadata.get("goal_audit_passed")),
        "operator_state": state.metadata.get("operator_productivity_state"),
    }
    print("AUTONOMY_BOOTSTRAP_GATE_5_REPORT")
    print(json.dumps(report, indent=2, default=str))

    try:
        engine.call(engine.shutdown(), timeout=20)
    except Exception as exc:
        print("shutdown_warning", type(exc).__name__, str(exc))

    assert report["passed_completion"], "simple goal did not close"
    assert report["worker_recoveries"] <= 2
    assert report["unresolved_human_decisions"] == 0
    assert report["artifact_count"] >= 1
    assert report["verification_passes"] >= 1
    assert report["initial_leaf_count"] <= 6, f"simple goal over-decomposed at intake: {initial_leaf_count}"
    assert report["provider_calls"] <= 15, f"simple goal used too many provider calls: {provider.calls}"
    print("AUTONOMY_BOOTSTRAP_GATE_5_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
