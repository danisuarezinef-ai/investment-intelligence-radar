from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ["CEO_W7_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.productive_fallback_orchestrator_v1 import ProductiveFallbackOrchestratorV1
from ceo_core.useful_output_watchdog_v2 import UsefulOutputWatchdogV2


def add(state, task):
    state.tasks[task.id] = task
    state.root_task_ids.append(task.id)
    return task


def exhausted_state():
    state = ProjectState(goal="W7 bounded recovery")
    state.metadata["max_productive_replan_generations"] = 3
    state.metadata["worker_recoveries"] = 8
    state.metadata["productive_truth_v2"] = {
        "epoch": "dev308-executable-route-integrity-v1",
        "productive_watermark": 0,
        "recoveries_at_watermark": 0,
    }
    task = add(state, Task(
        title="Execution dead end",
        status=TaskStatus.FAILED,
        attempts=3,
        max_attempts=3,
        metadata={
            "task_role": "productive",
            "stall_replan_generation": 3,
        },
    ))
    add(state, Task(
        title="Internal recovery residue",
        status=TaskStatus.BLOCKED,
        metadata={
            "task_role": "internal_control",
            "control_plane_atomic": True,
        },
    ))
    return state, task


def below_cap_state():
    state = ProjectState(goal="W7 strategy change below cap")
    state.metadata["max_productive_replan_generations"] = 3
    task = add(state, Task(
        title="Execution dead end",
        status=TaskStatus.FAILED,
        attempts=3,
        max_attempts=3,
        metadata={
            "task_role": "productive",
            "stall_replan_generation": 2,
        },
    ))
    return state, task


def main():
    failures = []

    state, task = exhausted_state()
    before_ids = set(state.tasks)
    out = ProductiveFallbackOrchestratorV1().apply(state)
    after_ids = set(state.tasks)
    created = sorted(after_ids - before_ids)

    print("W7_EXHAUSTED_FALLBACK", json.dumps({
        "report": out.to_dict(),
        "task_status": task.status.value,
        "blocked_safe": bool(task.metadata.get("blocked_safe")),
        "reason": task.metadata.get("blocked_safe_reason"),
        "created": created,
        "generation": task.metadata.get("stall_replan_generation"),
    }, default=str, sort_keys=True))

    if created:
        failures.append("exhausted_lineage_created_replacement")
    if task.status != TaskStatus.BLOCKED:
        failures.append(f"exhausted_lineage_status={task.status.value}")
    if task.metadata.get("blocked_safe") is not True:
        failures.append("exhausted_lineage_not_blocked_safe")
    if task.metadata.get("blocked_safe_reason") != "productive_replan_lineage_exhausted":
        failures.append("wrong_exhaustion_reason")

    # Repeated watchdog ticks must not create a fresh replacement after the cap.
    ids_before_watchdog = set(state.tasks)
    wd1 = UsefulOutputWatchdogV2().tick(state)
    ids_after_1 = set(state.tasks)
    wd2 = UsefulOutputWatchdogV2().tick(state)
    ids_after_2 = set(state.tasks)
    print("W7_WATCHDOG_AFTER_EXHAUSTION", json.dumps({
        "first": wd1.to_dict(),
        "second": wd2.to_dict(),
        "task_count": len(state.tasks),
        "operator": state.metadata.get("operator_productivity_state"),
        "block_reason": state.metadata.get("operator_block_reason"),
    }, default=str, sort_keys=True))
    if ids_before_watchdog != ids_after_1 or ids_after_1 != ids_after_2:
        failures.append("watchdog_recreated_exhausted_lineage")
    if state.metadata.get("operator_productivity_state") != "BLOQUEADO":
        failures.append("exhausted_lineage_not_visible_as_blocked")

    # Restart persistence: an exhausted lineage must stay exhausted after
    # serialization/reopen and must not manufacture another replacement.
    payload = state.model_dump_json()
    restored = ProjectState.model_validate_json(payload)
    restored_task = restored.tasks[task.id]
    before_restart = set(restored.tasks)
    out_restart = ProductiveFallbackOrchestratorV1().apply(restored)
    after_restart = set(restored.tasks)
    print("W7_RESTART_PERSISTENCE", json.dumps({
        "report": out_restart.to_dict(),
        "task_status": restored_task.status.value,
        "blocked_safe": bool(restored_task.metadata.get("blocked_safe")),
        "reason": restored_task.metadata.get("blocked_safe_reason"),
        "created": sorted(after_restart - before_restart),
    }, default=str, sort_keys=True))
    if after_restart != before_restart:
        failures.append("restart_reanimated_exhausted_lineage")
    if restored_task.status != TaskStatus.BLOCKED:
        failures.append(f"restart_exhausted_status={restored_task.status.value}")
    if restored_task.metadata.get("blocked_safe") is not True:
        failures.append("restart_lost_blocked_safe")
    if restored_task.metadata.get("blocked_safe_reason") != "productive_replan_lineage_exhausted":
        failures.append("restart_lost_exhaustion_reason")

    # Below the cap, one genuine strategy-changing replacement is still allowed.
    state2, task2 = below_cap_state()
    before2 = set(state2.tasks)
    out2 = ProductiveFallbackOrchestratorV1().apply(state2)
    created2 = list(set(state2.tasks) - before2)
    print("W7_BELOW_CAP_FALLBACK", json.dumps({
        "report": out2.to_dict(),
        "created": created2,
        "old_status": task2.status.value,
        "new_generation": (
            state2.tasks[created2[0]].metadata.get("stall_replan_generation")
            if len(created2) == 1 else None
        ),
    }, default=str, sort_keys=True))
    if len(created2) != 1:
        failures.append(f"below_cap_replacement_count={len(created2)}")
    else:
        replacement = state2.tasks[created2[0]]
        if replacement.status != TaskStatus.READY:
            failures.append(f"below_cap_replacement_status={replacement.status.value}")
        if int(replacement.metadata.get("stall_replan_generation", -1)) != 3:
            failures.append("below_cap_generation_not_incremented")
    if task2.status != TaskStatus.SUPERSEDED:
        failures.append("old_task_not_superseded_after_replan")

    # Provider waiting is not recovery churn and must never be converted into a rebuild.
    wait = ProjectState(goal="provider waiting")
    wait.metadata["worker_recoveries"] = 20
    wait.metadata["productive_truth_v2"] = {
        "epoch": "dev308-executable-route-integrity-v1",
        "productive_watermark": 0,
        "recoveries_at_watermark": 0,
    }
    wait.metadata["provider_wait_v1"] = {"active": True, "category": "provider_unavailable"}
    waiting = add(wait, Task(
        title="External AI task",
        status=TaskStatus.BLOCKED,
        metadata={
            "task_role": "productive",
            "waiting_provider_v1": {"active": True},
        },
    ))
    count_before = len(wait.tasks)
    wd_wait = UsefulOutputWatchdogV2().tick(wait)
    print("W7_PROVIDER_WAIT", json.dumps({
        "watchdog": wd_wait.to_dict(),
        "task_count": len(wait.tasks),
        "status": waiting.status.value,
    }, default=str, sort_keys=True))
    if len(wait.tasks) != count_before:
        failures.append("provider_wait_spawned_recovery")
    if wd_wait.status != "ESPERANDO PROVEEDOR":
        failures.append(f"provider_wait_status={wd_wait.status}")

    # Package contract must follow the patch.
    contract = ROOT / "CEO_UPDATE_PACKAGE.json"
    if contract.is_file():
        import hashlib
        row = json.loads(contract.read_text(encoding="utf-8"))
        expected = str((row.get("file_hashes") or {}).get("ceo_core/productive_fallback_orchestrator_v1.py") or "")
        actual = hashlib.sha256((ROOT / "ceo_core" / "productive_fallback_orchestrator_v1.py").read_bytes()).hexdigest()
        print("W7_PACKAGE_HASH", json.dumps({"expected": expected, "actual": actual}, sort_keys=True))
        if expected and expected != actual:
            failures.append("package_contract_hash_not_updated")

    if failures:
        print("W7_RECOVERY_LINEAGE_REGRESSION_FAIL", failures)
        return 7

    print("W7_RECOVERY_LINEAGE_REGRESSION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
