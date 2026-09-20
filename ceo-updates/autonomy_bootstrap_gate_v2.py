from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(os.environ.get("CEO_GATE_ROOT", "")).resolve()
GATE1_PATH = pathlib.Path(__file__).with_name("autonomy_bootstrap_gate_v1.py").resolve()

spec = importlib.util.spec_from_file_location("bootstrap_gate_v1_shared", GATE1_PATH)
gate1 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gate1)

TaskStatus = gate1.TaskStatus


def wait_for_completion(engine, *, timeout_seconds: float = 25.0) -> dict:
    started = time.monotonic()
    samples = []
    while time.monotonic() - started < timeout_seconds:
        engine.call(engine.snapshot(), timeout=15)
        state = engine.state
        samples.append({
            "t": round(time.monotonic() - started, 2),
            "completed": state.completed_at is not None,
            "audit": bool(state.metadata.get("goal_audit_passed")),
            "recoveries": int(state.metadata.get("worker_recoveries", 0) or 0),
            "operator": state.metadata.get("operator_productivity_state"),
            "running": sum(t.status == TaskStatus.RUNNING for t in state.leaf_tasks),
            "ready": sum(t.status == TaskStatus.READY for t in state.leaf_tasks),
        })
        if state.completed_at is not None and state.metadata.get("goal_audit_passed"):
            return {"ok": True, "elapsed": round(time.monotonic() - started, 2), "samples": samples[-12:]}
        if state.cancelled_at is not None:
            return {"ok": False, "reason": "cancelled", "elapsed": round(time.monotonic() - started, 2), "samples": samples[-12:]}
        time.sleep(0.2)
    return {"ok": False, "reason": "timeout", "elapsed": round(time.monotonic() - started, 2), "samples": samples[-12:]}


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

    goals = [
        ("Consecutive Gate A", "Create a short markdown status note named GATE_A.md containing the phrase GATE A PASS and one completed-work summary."),
        ("Consecutive Gate B", "Create a short markdown checklist named GATE_B.md containing exactly three checked items and the phrase GATE B PASS."),
        ("Consecutive Gate C", "Create a short markdown report named GATE_C.md with headings Summary and Result and include the phrase GATE C PASS."),
        ("Consecutive Gate D", "Create a short markdown note named GATE_D.md containing a two-sentence result summary and the phrase GATE D PASS."),
        ("Consecutive Gate E", "Create a short markdown completion record named GATE_E.md containing the phrase GATE E PASS and a one-line conclusion."),
    ]

    runs = []
    seen_projects = set()
    calls_before = provider.calls
    audits_before = provider.audit_calls

    try:
        for index, (name, goal) in enumerate(goals, 1):
            snap = engine.call(engine.start_project({
                "goal": goal,
                "name": name,
                "power_percent": 20,
            }), timeout=60)
            state = engine.state
            pid = state.id
            if pid in seen_projects:
                raise AssertionError(f"project id reused: {pid}")
            seen_projects.add(pid)

            calls_at_start = provider.calls
            audits_at_start = provider.audit_calls
            result = wait_for_completion(engine, timeout_seconds=25.0)
            state = engine.state

            unresolved_decisions = [d for d in state.decisions.values() if not d.resolved]
            productive_complete = [
                t for t in state.leaf_tasks
                if not t.metadata.get("goal_continuity_audit")
                and t.status in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}
            ]
            artifacts = [
                a
                for t in productive_complete
                for a in list(t.metadata.get("artifacts") or [])
                if pathlib.Path(str(a)).is_file()
            ]
            recoveries = int(state.metadata.get("worker_recoveries", 0) or 0)
            handoff = state.metadata.get("project_handoff")

            row = {
                "index": index,
                "project_id": pid,
                "name": name,
                "ok": result["ok"],
                "elapsed_seconds": result["elapsed"],
                "completed_at": str(state.completed_at or ""),
                "goal_audit_passed": bool(state.metadata.get("goal_audit_passed")),
                "recoveries": recoveries,
                "unresolved_human_decisions": len(unresolved_decisions),
                "productive_completed": len(productive_complete),
                "artifact_count": len(artifacts),
                "provider_calls": provider.calls - calls_at_start,
                "audit_calls": provider.audit_calls - audits_at_start,
                "handoff": handoff,
                "samples_tail": result["samples"],
            }
            runs.append(row)
            print("CONSECUTIVE_GATE_RUN", json.dumps(row, default=str))

            assert result["ok"], f"goal {index} did not close: {row}"
            assert state.completed_at is not None, f"goal {index} missing completed_at"
            assert state.metadata.get("goal_audit_passed") is True, f"goal {index} audit did not pass"
            assert recoveries <= 2, f"goal {index} exceeded recovery budget: {recoveries}"
            assert not unresolved_decisions, f"goal {index} required human intervention"
            assert artifacts, f"goal {index} produced no artifact"
            assert len(productive_complete) >= 3, f"goal {index} produced insufficient grounded work"

        report = {
            "passed": True,
            "goals_completed": len(runs),
            "unique_project_ids": len(seen_projects),
            "total_provider_calls": provider.calls - calls_before,
            "total_audit_calls": provider.audit_calls - audits_before,
            "total_recoveries": sum(r["recoveries"] for r in runs),
            "total_elapsed_seconds": round(sum(r["elapsed_seconds"] for r in runs), 2),
            "runs": runs,
        }
        print("AUTONOMY_BOOTSTRAP_GATE_2_REPORT")
        print(json.dumps(report, indent=2, default=str))
        assert len(runs) == 5 and all(r["ok"] for r in runs)
        assert len(seen_projects) == 5
        print("AUTONOMY_BOOTSTRAP_GATE_2_PASS")
        return 0
    finally:
        try:
            engine.call(engine.shutdown(), timeout=20)
        except Exception as exc:
            print("shutdown_warning", type(exc).__name__, str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
