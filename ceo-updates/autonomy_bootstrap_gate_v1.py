from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import tempfile
import time

ROOT = pathlib.Path(os.environ.get("CEO_GATE_ROOT", "/tmp/ceo181")).resolve()
ARTIFACT_DIR = pathlib.Path(os.environ.get("CEO_GATE_ARTIFACTS", "/tmp/ceo-autonomy-gate-artifacts")).resolve()
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

import sys
sys.path.insert(0, str(ROOT))

from ceo_core.contracts import FixedWorkerRouter, WorkerKind, WorkerProvider, WorkerRequest, WorkerResult
from ceo_core.models import TaskStatus


def load_work_mode():
    path = ROOT / "scripts" / "ceo_stdlib_work_mode.py"
    spec = importlib.util.spec_from_file_location("ceo_work_mode_gate", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class GateProvider(WorkerProvider):
    name = "autonomy-bootstrap-gate"
    kind = WorkerKind.MOCK
    capabilities = frozenset({"general", "research", "analysis", "writing", "verification", "local", "file"})

    def __init__(self, engine_getter):
        self.engine_getter = engine_getter
        self.calls = 0
        self.audit_calls = 0

    def supports(self, task) -> bool:
        return True

    async def execute(self, request: WorkerRequest) -> WorkerResult:
        self.calls += 1
        engine = self.engine_getter()
        state = engine.state
        task = state.tasks[request.work_unit.id]
        is_audit = bool(task.metadata.get("goal_continuity_audit"))

        if is_audit:
            self.audit_calls += 1
            generation = int(task.metadata.get("goal_continuity_generation") or state.metadata.get("goal_continuity_generation") or 0)
            required_generation = int(state.metadata.get("min_goal_continuity_generations", 3))
            refs = [
                t.id
                for t in state.leaf_tasks
                if not t.metadata.get("goal_continuity_audit")
                and t.status in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}
                and bool((t.result or "").strip())
                and bool(t.metadata.get("artifacts") or t.metadata.get("evidence_refs") or t.metadata.get("verification_application"))
            ]

            if generation >= required_generation and len(refs) >= 3:
                payload = {
                    "status": "complete",
                    "reason": "Strict completion evidence exists for the locked objective.",
                    "confidence": 1.0,
                    "evidence_refs": refs[:12],
                }
                text = "CEO_GOAL_AUDIT: PASS\n<CEO_RESULT>" + json.dumps(payload) + "</CEO_RESULT>"
                return WorkerResult(
                    provider=self.name,
                    kind=self.kind,
                    success=True,
                    text=text,
                    conversation_id=request.conversation_id or f"gate-audit-{task.id}",
                )

            payload = {
                "status": "spawn",
                "reason": f"Continuity round {generation}/{required_generation} needs another grounded work unit.",
                "confidence": 1.0,
                "followups": [f"Produce additional grounded deliverable evidence for continuity round {generation + 1}"],
                "evidence_refs": refs[:12],
            }
            text = "Locked objective is not yet eligible for final PASS.\n<CEO_RESULT>" + json.dumps(payload) + "</CEO_RESULT>"
            return WorkerResult(
                provider=self.name,
                kind=self.kind,
                success=True,
                text=text,
                conversation_id=request.conversation_id or f"gate-audit-{task.id}",
            )

        artifact = ARTIFACT_DIR / f"{task.id}.md"
        artifact.write_text(
            "# Autonomy Bootstrap Gate artifact\n\n"
            f"Task: {task.title}\n\n"
            f"Goal: {state.goal}\n\n"
            "This file is a concrete output produced by the deterministic gate worker.\n",
            encoding="utf-8",
        )
        payload = {
            "status": "complete",
            "reason": "Concrete work product created and returned to CEO.",
            "confidence": 1.0,
        }
        return WorkerResult(
            provider=self.name,
            kind=self.kind,
            success=True,
            text=(
                f"Completed productive unit '{task.title}'. Artifact: {artifact}\n"
                "<CEO_RESULT>" + json.dumps(payload) + "</CEO_RESULT>"
            ),
            artifacts=[str(artifact)],
            metadata={"sources": [f"gate-source:{task.id}"]},
            conversation_id=request.conversation_id or f"gate-{task.id}",
        )


def main() -> int:
    os.environ.setdefault("CEO_NO_BROWSER", "1")
    work = load_work_mode()

    engine = work.CEOEngine(None)
    provider = GateProvider(lambda: engine)
    engine.execution_enabled = True
    engine.provider_mode = "autonomy-bootstrap-gate"
    engine.gemini_key_status = "GATE_PROVIDER"
    engine.gemini_validation_error = None
    engine._router = lambda: FixedWorkerRouter(provider)

    started = time.monotonic()
    start_snapshot = engine.call(engine.start_project({
        "goal": "Create a concise markdown deliverable AUTONOMY_BOOTSTRAP_GATE.md proving that CEO can autonomously plan, execute, verify and close a small objective.",
        "name": "Autonomy Bootstrap Gate 1",
        "power_percent": 20,
    }), timeout=60)

    project_id = str(start_snapshot.get("project_id") or start_snapshot.get("id") or "")
    history = []
    terminal = None
    deadline = time.monotonic() + 90

    while time.monotonic() < deadline:
        snap = engine.call(engine.snapshot(), timeout=20)
        state = engine.state
        row = {
            "t": round(time.monotonic() - started, 2),
            "completed_at": str(state.completed_at or ""),
            "goal_audit_passed": bool(state.metadata.get("goal_audit_passed")),
            "operator_state": state.metadata.get("operator_productivity_state"),
            "worker_recoveries": int(state.metadata.get("worker_recoveries", 0) or 0),
            "tasks": {
                str(status.value): sum(1 for t in state.leaf_tasks if t.status == status)
                for status in TaskStatus
            },
            "productive_completed": sum(
                1 for t in state.leaf_tasks
                if not t.metadata.get("goal_continuity_audit")
                and t.status in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}
            ),
            "continuity_generation": int(state.metadata.get("goal_continuity_generation", 0) or 0),
        }
        history.append(row)

        if state.completed_at is not None and state.metadata.get("goal_audit_passed"):
            terminal = "complete"
            break
        if state.cancelled_at is not None:
            terminal = "cancelled"
            break
        time.sleep(0.25)

    state = engine.state
    deliverables = [p for p in ARTIFACT_DIR.glob("*.md") if p.is_file()]
    productive = [
        t for t in state.leaf_tasks
        if not t.metadata.get("goal_continuity_audit")
    ]
    productive_complete = [
        t for t in productive
        if t.status in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}
    ]
    grounded = [
        t for t in productive_complete
        if t.metadata.get("artifacts") or t.metadata.get("evidence_refs") or t.metadata.get("verification_application")
    ]

    report = {
        "terminal": terminal,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "project_id": state.id,
        "goal": state.goal,
        "completed_at": str(state.completed_at or ""),
        "goal_audit_passed": bool(state.metadata.get("goal_audit_passed")),
        "goal_audit_evidence": state.metadata.get("goal_audit_evidence"),
        "last_goal_audit_rejection": state.metadata.get("last_goal_audit_rejection"),
        "operator_state": state.metadata.get("operator_productivity_state"),
        "operator_block_reason": state.metadata.get("operator_block_reason"),
        "worker_recoveries": int(state.metadata.get("worker_recoveries", 0) or 0),
        "provider_calls": provider.calls,
        "audit_calls": provider.audit_calls,
        "productive_tasks": len(productive),
        "productive_completed": len(productive_complete),
        "grounded_completed": len(grounded),
        "artifacts_existing": [str(p) for p in deliverables],
        "human_decisions": len([d for d in state.decisions.values() if not d.resolved]),
        "history_tail": history[-20:],
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status.value,
                "attempts": t.attempts,
                "result": (t.result or "")[:180],
                "audit": bool(t.metadata.get("goal_continuity_audit")),
                "artifacts": list(t.metadata.get("artifacts") or []),
                "evidence_refs": list(t.metadata.get("evidence_refs") or []),
                "verification_application": t.metadata.get("verification_application"),
            }
            for t in state.leaf_tasks
        ],
    }
    print("AUTONOMY_BOOTSTRAP_GATE_REPORT")
    print(json.dumps(report, indent=2, default=str))

    try:
        engine.call(engine.shutdown(), timeout=20)
    except Exception as exc:
        print("shutdown_warning", type(exc).__name__, str(exc))

    assert terminal == "complete", "CEO did not autonomously close the objective"
    assert state.completed_at is not None, "project completed_at was not set"
    assert state.metadata.get("goal_audit_passed") is True, "strict goal audit did not pass"
    assert len(productive_complete) >= 3, "insufficient productive completed work"
    assert len(grounded) >= 2, "insufficient grounded productive evidence"
    assert len(deliverables) >= 1, "no concrete artifact was produced"
    assert int(state.metadata.get("worker_recoveries", 0) or 0) <= 2, "recovery budget exceeded"
    assert not [d for d in state.decisions.values() if not d.resolved], "human decision was required"

    print("AUTONOMY_BOOTSTRAP_GATE_1_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
