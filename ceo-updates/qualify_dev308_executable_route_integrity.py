from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ["CEO_DEV308_BUILD_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.decomposer import TaskDecomposer
from ceo_core.productive_truth_v2 import ProductiveTruthV2
from ceo_core.useful_output_watchdog_v2 import UsefulOutputWatchdogV2
from ceo_core.scheduler import ContinuousScheduler, RELIABILITY_EPOCH, _apply_reliability_epoch_migration
from ceo_core.blocked_safe_state_v1 import mark_blocked_safe

EXPECTED_EPOCH = "dev308-executable-route-integrity-v1"

FIELD_GOAL = (
    "Crea en tu espacio de trabajo un archivo AUTONOMY_GATE_1.md. Debe contener tu "
    "versión activa, estado del proveedor IA, estado del scheduler, número de tareas "
    "creadas, completadas y bloqueadas, recuperaciones utilizadas durante este objetivo "
    "y una conclusión indicando si el objetivo se completó sin intervención humana. "
    "Comprueba que el archivo existe y tiene contenido antes de dar el objetivo por "
    "terminado. No modifiques CEO, no prepares actualizaciones y no solicites "
    "intervención humana salvo que exista un bloqueo imposible de resolver autónomamente."
)


def add(state: ProjectState, task: Task) -> Task:
    state.tasks[task.id] = task
    state.root_task_ids.append(task.id)
    return task


def test_detailed_single_file_is_compact() -> dict:
    d = TaskDecomposer()
    profile = d._complexity_profile(FIELD_GOAL)
    assert profile["mode"] == "compact", profile
    assert profile["single_explicit_file"] is True, profile
    state = d.plan(FIELD_GOAL)
    assert state.metadata["decomposition_profile"]["mode"] == "compact"
    assert len(state.root_task_ids) == 3, len(state.root_task_ids)
    assert len(state.leaf_tasks) == 3, len(state.leaf_tasks)

    complex_goal = (
        "Investiga y compara múltiples arquitecturas, audita el repositorio, implementa "
        "una migración y crea finalmente REPORT.md."
    )
    assert d._complexity_profile(complex_goal)["mode"] == "full"
    return {
        "field_goal_chars": len(FIELD_GOAL),
        "profile": profile,
        "roots": len(state.root_task_ids),
        "leaves": len(state.leaf_tasks),
        "complex_control": d._complexity_profile(complex_goal),
    }


def route_state(*, old_epoch: bool = False) -> tuple[ProjectState, Task]:
    state = ProjectState(goal=FIELD_GOAL)
    ready = add(state, Task(
        title="Execution · work unit 1",
        status=TaskStatus.READY,
        metadata={"task_role": "productive"},
    ))
    add(state, Task(
        title="Internal recovery control",
        status=TaskStatus.BLOCKED,
        metadata={"task_role": "internal_control", "control_plane_atomic": True},
    ))
    state.metadata["worker_recoveries"] = 8
    state.metadata["productive_truth_v2"] = {
        "epoch": "dev307-autonomy-runtime-integrity-v1" if old_epoch else EXPECTED_EPOCH,
        "productive_watermark": 0,
        "recoveries_at_watermark": 0,
    }
    return state, ready


def test_productive_ready_never_stalls() -> dict:
    state, _ = route_state()
    report = ProductiveTruthV2(recovery_trip=4).assess(state)
    assert report.productive_ready == 1, report
    assert report.worker_recoveries == 8, report
    assert report.stalled is False, report
    assert report.status == "planning", report

    state.metadata["suppress_new_internal_recovery"] = True
    state.metadata["productive_stall_escape_required"] = True
    state.metadata["operator_productivity_state"] = "BLOQUEADO"
    state.metadata["operator_block_reason"] = "No existe una ruta ejecutable después del fallback."
    wd = UsefulOutputWatchdogV2().tick(state)
    assert wd.fuse_open is False, wd
    assert wd.fallback_action == "executable_route", wd
    assert wd.status == "PLANIFICANDO", wd
    assert state.metadata.get("operator_productivity_state") == "PLANIFICANDO"
    assert "operator_block_reason" not in state.metadata
    assert "suppress_new_internal_recovery" not in state.metadata
    assert "productive_stall_escape_required" not in state.metadata
    return {"truth": report.to_dict(), "watchdog": wd.to_dict()}


def test_epoch_migration_recovers_exact_field_shape() -> dict:
    state, _ = route_state(old_epoch=True)
    state.metadata["reliability_epoch_v1"] = {"epoch": "dev307-autonomy-runtime-integrity-v1"}
    state.metadata["operator_productivity_state"] = "BLOQUEADO"
    state.metadata["operator_block_reason"] = "No existe una ruta ejecutable después del fallback."
    state.metadata["suppress_new_internal_recovery"] = True
    state.metadata["productive_stall_escape_required"] = True
    state.metadata["autonomy_stalled"] = {"action": "stale_field_block"}
    state.metadata["recovery_churn_fuse_v2"] = {
        "open": True,
        "attempts_without_progress": 8,
        "retired": 1,
        "reason": "recovery budget exhausted without useful output",
    }

    # A legitimate protected block must not be released by this migration.
    protected = add(state, Task(
        title="Protected destructive action",
        status=TaskStatus.BLOCKED,
        metadata={"task_role": "productive", "explicit_human_gate": True},
    ))
    mark_blocked_safe(protected, "destructive_action_requires_approval", source="safety")

    out = _apply_reliability_epoch_migration(state)
    assert RELIABILITY_EPOCH == EXPECTED_EPOCH
    assert out["changed"] is True, out
    assert state.metadata["reliability_epoch_v1"]["epoch"] == EXPECTED_EPOCH
    assert state.metadata["operator_productivity_state"] == "PLANIFICANDO"
    assert "operator_block_reason" not in state.metadata
    assert "suppress_new_internal_recovery" not in state.metadata
    assert "productive_stall_escape_required" not in state.metadata
    assert "autonomy_stalled" not in state.metadata
    assert (state.metadata.get("recovery_churn_fuse_v2") or {}).get("open") is False
    assert protected.status == TaskStatus.BLOCKED
    assert protected.metadata.get("blocked_safe") is True
    return {
        "migration": out,
        "operator": state.metadata.get("operator_productivity_state"),
        "fuse": state.metadata.get("recovery_churn_fuse_v2"),
        "protected_preserved": bool(protected.metadata.get("blocked_safe")),
    }


def test_operator_status_executable_precedence() -> dict:
    state, ready = route_state()
    state.metadata["operator_productivity_state"] = "BLOQUEADO"
    state.metadata["operator_block_reason"] = "stale"
    sched = object.__new__(ContinuousScheduler)
    sched.state = state
    sched._active = {}
    status = ContinuousScheduler.operational_status(sched)
    assert status == "PLANIFICANDO", status

    ready.status = TaskStatus.RUNNING
    sched._active = {ready.id: object()}
    status2 = ContinuousScheduler.operational_status(sched)
    assert status2 == "TRABAJANDO", status2
    return {"queued": status, "running": status2}


def test_real_no_route_still_fail_closed() -> dict:
    state = ProjectState(goal="genuine protected block")
    protected = add(state, Task(
        title="External destructive operation",
        status=TaskStatus.BLOCKED,
        metadata={"task_role": "productive", "explicit_human_gate": True},
    ))
    mark_blocked_safe(protected, "destructive_action_requires_approval", source="safety")
    add(state, Task(
        title="Internal control",
        status=TaskStatus.BLOCKED,
        metadata={"task_role": "internal_control", "control_plane_atomic": True},
    ))
    state.metadata["worker_recoveries"] = 4
    state.metadata["productive_truth_v2"] = {
        "epoch": EXPECTED_EPOCH,
        "productive_watermark": 0,
        "recoveries_at_watermark": 0,
    }
    truth = ProductiveTruthV2(recovery_trip=4).assess(state)
    assert truth.productive_ready == 0
    assert truth.productive_running == 0
    # The DEV308 change must not turn a genuinely non-executable protected task READY.
    UsefulOutputWatchdogV2().tick(state)
    assert protected.status == TaskStatus.BLOCKED
    assert protected.metadata.get("blocked_safe") is True
    return {"truth": truth.to_dict(), "protected_status": protected.status.value}


def main() -> int:
    assert RELIABILITY_EPOCH == EXPECTED_EPOCH, RELIABILITY_EPOCH
    rows = {
        "detailed_single_file_compact": test_detailed_single_file_is_compact(),
        "productive_ready_route": test_productive_ready_never_stalls(),
        "field_migration": test_epoch_migration_recovers_exact_field_shape(),
        "operator_status": test_operator_status_executable_precedence(),
        "fail_closed_control": test_real_no_route_still_fail_closed(),
    }
    print("DEV308_EXECUTABLE_ROUTE_INTEGRITY_PASS")
    print(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
