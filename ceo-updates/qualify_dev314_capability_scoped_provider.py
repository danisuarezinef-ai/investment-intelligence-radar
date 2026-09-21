from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ["CEO_DEV314_BUILD_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))

from ceo_core.autonomous_loop import AutonomousProjectLoop
from ceo_core.contracts import GoalContract, WorkerRequest, WorkUnit
from ceo_core.core_health_contract_v2 import build_core_health_v2
from ceo_core.goal_lock_local_provider_v1 import GoalLockLocalProviderV1
from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.provider_resilience_v2 import ProviderResilienceV2
from ceo_core.routing import MultiProviderRouter


def productive_task(task_id: str, status: TaskStatus, *, waiting_provider: bool = False) -> Task:
    md = {"task_role": "productive"}
    if waiting_provider:
        md["waiting_provider_v1"] = {
            "active": True,
            "category": "provider_unavailable",
            "retry_after_seconds": 300,
            "recoveries_consumed": 0,
        }
        md["retry_after_ts"] = 9999999999.0
    return Task(
        id=task_id,
        title=f"Task {task_id}",
        status=status,
        required_capabilities=["reasoning"],
        metadata=md,
    )


def test_local_provider_scope():
    local = GoalLockLocalProviderV1()
    router = MultiProviderRouter([local])

    lock = Task(
        id="lock",
        title="Clarify & lock goal",
        status=TaskStatus.READY,
        required_capabilities=["reasoning"],
        metadata={"local_fallback_kind": "goal_lock", "task_role": "productive"},
    )
    normal = Task(
        id="reason",
        title="Research unresolved requirement",
        status=TaskStatus.READY,
        required_capabilities=["reasoning"],
        metadata={"task_role": "productive"},
    )

    assert local.supports(lock) is True
    assert local.supports(normal) is False
    selected = router.select(lock, ProjectState(goal="x", tasks={"lock": lock}, root_task_ids=["lock"]))
    assert selected.name == "ceo-local-goal-lock"

    failed = False
    try:
        router.select(normal, ProjectState(goal="x", tasks={"reason": normal}, root_task_ids=["reason"]))
    except RuntimeError as exc:
        failed = "No provider can execute" in str(exc)
    assert failed is True
    return {
        "goal_lock_local": True,
        "reasoning_not_misrouted_local": True,
        "no_provider_is_explicit": True,
    }


def test_no_provider_is_wait_not_recovery():
    decision = ProviderResilienceV2().classify("No provider can execute task 'Research unresolved requirement'", 4)
    assert decision.category == "provider_unavailable"
    assert decision.retry is True
    assert decision.requires_human is False
    assert decision.spending_allowed is False

    scheduler = (ROOT / "ceo_core" / "scheduler.py").read_text(encoding="utf-8")
    assert 'wait_categories = {"quota", "provider_unavailable", "model_unavailable", "transient"}' in scheduler
    assert 'task.attempts = max(0, int(task.attempts) - 1)' in scheduler
    assert '"recoveries_consumed": 0' in scheduler
    assert '"provider_wait"' in scheduler
    return {
        "category": decision.category,
        "retry": decision.retry,
        "human_required": decision.requires_human,
        "spending_allowed": decision.spending_allowed,
        "attempt_refunded": True,
        "recovery_budget_zero": True,
    }


def test_watchdog_holds_provider_wait():
    waiting = productive_task("ai-wait", TaskStatus.BLOCKED, waiting_provider=True)
    state = ProjectState(
        id="dev314-wait",
        goal="Continue project",
        tasks={waiting.id: waiting},
        root_task_ids=[waiting.id],
        metadata={"require_goal_audit": True},
    )
    before = set(state.tasks)
    row = AutonomousProjectLoop().ensure_progress(state)
    after = set(state.tasks)

    assert row["status"] == "waiting_external_provider_capability", row
    assert row["created"] == 0
    assert row["recoveries_consumed"] == 0
    assert before == after
    assert state.metadata["provider_capability_wait_v1"]["active"] is True
    assert not any(t.metadata.get("autonomy_recovery") for t in state.tasks.values())
    return row


def test_runnable_work_beats_provider_wait():
    waiting = productive_task("ai-wait", TaskStatus.BLOCKED, waiting_provider=True)
    local_ready = Task(
        id="local-ready",
        title="Clarify & lock goal",
        status=TaskStatus.READY,
        required_capabilities=["reasoning"],
        metadata={"local_fallback_kind": "goal_lock", "task_role": "productive"},
    )
    state = ProjectState(
        id="dev314-mixed",
        goal="Continue mixed work",
        tasks={waiting.id: waiting, local_ready.id: local_ready},
        root_task_ids=[waiting.id, local_ready.id],
    )
    row = AutonomousProjectLoop().ensure_progress(state)
    assert row["status"] == "productive_work_available", row
    assert "local-ready" in row["productive_task_ids"], row
    return row


def test_core_health_without_gemini():
    row = build_core_health_v2(
        version="1.5.90-test",
        activation_id="test",
        storage_ready=True,
        runtime_ready=True,
        frontend_ready=True,
        provider_mode="gemini-authenticated-waiting",
        execution_enabled=False,
        provider_error="ConnectError",
        provider_validation_in_progress=False,
    )
    assert row["ok"] is True
    assert row["core_health_ok"] is True
    assert row["provider"]["required_for_activation_health"] is False
    assert row["provider"]["state"] == "degraded"
    return {
        "core_ok": row["ok"],
        "provider_state": row["provider"]["state"],
        "provider_required_for_health": row["provider"]["required_for_activation_health"],
    }


def test_work_mode_provider_scope_semantics():
    text = (ROOT / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")

    assert 'Gemini no está validado. Actívalo primero; no se creará un proyecto' not in text
    assert 'state.paused = not self.execution_enabled' not in text
    assert 'if self.execution_enabled and state.completed_at is None:' not in text
    assert 'if not self.engine.execution_enabled:' not in text[text.index('if path == "/api/resume"'):text.index('if path == "/api/cancel"')]
    assert 'state.metadata["operator_paused_v1"] = True' in text
    assert 'state.metadata.pop("operator_paused_v1", None)' in text
    assert "dev314_provider_pause_migrated" in text
    assert "core_execution_available" in text
    assert "external_ai_available" in text
    assert "las tareas que requieren IA esperan sin consumir recuperaciones" in text
    assert "$('resumeBtn').disabled=!hasActive||!s.paused;" in text
    assert "$('startBtn').disabled=false;" in text
    assert "Crear proyecto; las tareas que necesiten Gemini esperarán al proveedor" in text

    active_slice = text[text.index('"active": True'):text.index('"device_fabric":', text.index('"active": True'))]
    assert '"core_execution_available": bool(scheduler_alive)' in active_slice
    inactive_slice = text[text.index('"active": False'):text.index('"message": "Goal Engine', text.index('"active": False'))]
    assert "scheduler_alive" not in inactive_slice
    assert '"core_execution_available": bool(self.loop.is_running() and self.thread.is_alive())' in inactive_slice

    return {
        "start_without_external_ai": True,
        "resume_without_external_ai": True,
        "manual_pause_preserved": True,
        "core_vs_external_ai_exposed": True,
        "ui_capability_scoped": True,
    }


def test_dev313_inherited():
    root = ROOT
    assert (root / "ceo_core" / "deterministic_completion_certifier_v1.py").is_file()
    scheduler = (root / "ceo_core" / "scheduler.py").read_text(encoding="utf-8")
    assert "DeterministicCompletionCertifierV1" in scheduler
    ui = (root / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")
    assert "work_complete_pending_certification" in ui
    return {"dev313_deterministic_completion": True}


def main():
    rows = {
        "local_scope": test_local_provider_scope(),
        "no_provider_wait": test_no_provider_is_wait_not_recovery(),
        "watchdog_hold": test_watchdog_holds_provider_wait(),
        "mixed_work": test_runnable_work_beats_provider_wait(),
        "core_health": test_core_health_without_gemini(),
        "work_mode": test_work_mode_provider_scope_semantics(),
        "inheritance": test_dev313_inherited(),
    }
    print("DEV314_CAPABILITY_SCOPED_PROVIDER_PASS")
    print(rows)


if __name__ == "__main__":
    main()
