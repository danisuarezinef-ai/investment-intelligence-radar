from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ["CEO_W8_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.progress_tracker import StableProgressTracker
from ceo_core.productive_truth_v2 import ProductiveTruthV2


def add(state: ProjectState, task: Task) -> Task:
    state.tasks[task.id] = task
    state.root_task_ids.append(task.id)
    return task


def productive_state() -> ProjectState:
    s = ProjectState(goal="W8 productivity truth")
    add(s, Task(
        id="p-done", title="Productive done", status=TaskStatus.COMPLETE,
        result="real output", metadata={"task_role":"productive","acceptance_evidence":True},
    ))
    add(s, Task(
        id="p-ready", title="Productive ready", status=TaskStatus.READY,
        metadata={"task_role":"productive"},
    ))
    add(s, Task(
        id="p-blocked", title="Productive blocked", status=TaskStatus.BLOCKED,
        metadata={"task_role":"productive"},
    ))
    add(s, Task(
        id="p-review", title="Productive review", status=TaskStatus.NEEDS_REVIEW,
        metadata={"task_role":"productive"},
    ))
    return s


def add_control_noise(s: ProjectState, *, complete: int, active: int) -> None:
    for i in range(complete):
        add(s, Task(
            id=f"c-done-{i}", title=f"Control audit done {i}", status=TaskStatus.COMPLETE,
            result="heartbeat/audit/recovery", metadata={
                "task_role":"internal_control",
                "control_plane_atomic":True,
                "goal_continuity_audit":True,
            },
        ))
    for i in range(active):
        add(s, Task(
            id=f"c-active-{i}", title=f"Control recovery active {i}", status=TaskStatus.READY,
            metadata={
                "task_role":"internal_control",
                "control_plane_atomic":True,
                "recovery_task":True,
            },
        ))


def snap(s: ProjectState):
    return StableProgressTracker().snapshot(s, persist=True)


def key(row: dict):
    return {
        "display_progress": float(row.get("display_progress", -1)),
        "batch_progress": float(row.get("batch_progress", -1)),
        "productive_total_known": int(row.get("productive_total_known", -1)),
        "productive_completed": int(row.get("productive_completed", -1)),
        "productive_pending": int(row.get("productive_pending", -1)),
        "productive_running": int(row.get("productive_running", -1)),
    }


def main() -> int:
    failures=[]

    base=productive_state()
    base_row=snap(base)
    base_truth=ProductiveTruthV2().assess(base)

    polluted=productive_state()
    polluted.metadata["worker_recoveries"]=250
    polluted.metadata["scheduler_heartbeat_v1"]={"ticks":100000,"status":"healthy"}
    polluted.metadata["watchdog_heartbeat_v1"]={"ticks":100000}
    add_control_noise(polluted,complete=80,active=40)
    polluted_row=snap(polluted)
    polluted_truth=ProductiveTruthV2().assess(polluted)

    print("W8_BASE",json.dumps(key(base_row),sort_keys=True))
    print("W8_POLLUTED",json.dumps({**key(polluted_row),
        "control_completed":polluted_row.get("control_completed"),
        "control_pending":polluted_row.get("control_pending"),
        "worker_recoveries":polluted_truth.worker_recoveries,
        "truth_status":polluted_truth.status,
    },sort_keys=True))

    if key(base_row) != key(polluted_row):
        failures.append(f"control_noise_changed_productive_progress:{key(base_row)}!={key(polluted_row)}")

    for attr in ("productive_completed","productive_running","productive_ready","status"):
        if getattr(base_truth,attr) != getattr(polluted_truth,attr):
            failures.append(f"control_noise_changed_truth_{attr}")

    # Completing only control-plane work must not move productive progress or
    # update the productive watermark/timestamp.
    seq=productive_state()
    controls=[]
    for i in range(12):
        controls.append(add(seq,Task(
            id=f"seq-control-{i}", title=f"Sequential control {i}", status=TaskStatus.READY,
            metadata={"task_role":"internal_control","control_plane_atomic":True},
        )))
    before=snap(seq)
    before_marker=before.get("last_productive_progress_at")
    for t in controls:
        t.status=TaskStatus.COMPLETE
        t.result="internal check complete"
    after=snap(seq)
    after_marker=after.get("last_productive_progress_at")
    print("W8_CONTROL_ONLY_TRANSITION",json.dumps({
        "before":key(before),"after":key(after),
        "before_marker":str(before_marker),"after_marker":str(after_marker),
        "control_completed":after.get("control_completed"),
    },sort_keys=True))
    if key(before) != key(after):
        failures.append("control_completion_increased_productive_progress")
    if before_marker != after_marker:
        failures.append("control_completion_updated_productive_timestamp")

    # Recovery/heartbeat counters alone must not advance progress.
    rec=productive_state()
    r0=snap(rec)
    rec.metadata["worker_recoveries"]=999
    rec.metadata["worker_recovery_history"]=[{"action":"retry","i":i} for i in range(50)]
    rec.metadata["scheduler_heartbeat_v1"]={"ticks":999999}
    r1=snap(rec)
    print("W8_RECOVERY_HEARTBEAT_INVARIANCE",json.dumps({"before":key(r0),"after":key(r1)},sort_keys=True))
    if key(r0)!=key(r1):
        failures.append("recovery_or_heartbeat_inflated_progress")

    # Explicit legacy high-water marks are still preserved: W8 removes only
    # the invalid raw-graph fallback, not the monotonic productive-progress contract.
    legacy=productive_state()
    legacy.metadata["stable_progress_v1"]={"display_progress":60.0}
    legacy_row=snap(legacy)
    print("W8_EXPLICIT_LEGACY_HIGHWATER",json.dumps(key(legacy_row),sort_keys=True))
    if float(legacy_row.get("display_progress",-1)) != 60.0:
        failures.append(f"explicit_legacy_highwater_not_preserved={legacy_row.get('display_progress')}")

    # A project containing only completed control-plane tasks must not be
    # presented as productive completion.
    controls_only=ProjectState(goal="controls only")
    add_control_noise(controls_only,complete=25,active=0)
    only=snap(controls_only)
    truth_only=ProductiveTruthV2().assess(controls_only)
    print("W8_CONTROLS_ONLY",json.dumps({
        **key(only),"truth":truth_only.to_dict()
    },default=str,sort_keys=True))
    if int(only.get("productive_completed",0)) != 0:
        failures.append("controls_only_counted_as_productive_completed")
    if float(only.get("display_progress",0)) > 0:
        failures.append(f"controls_only_display_progress={only.get('display_progress')}")
    if truth_only.productive_completed != 0:
        failures.append("controls_only_truth_productive_completed")

    contract_path=ROOT/"CEO_UPDATE_PACKAGE.json"
    if contract_path.is_file():
        import hashlib
        row=json.loads(contract_path.read_text(encoding="utf-8"))
        expected=str((row.get("file_hashes") or {}).get("ceo_core/progress_tracker.py") or "")
        actual=hashlib.sha256((ROOT/"ceo_core"/"progress_tracker.py").read_bytes()).hexdigest()
        print("W8_PACKAGE_HASH",json.dumps({"expected":expected,"actual":actual},sort_keys=True))
        if expected and expected!=actual:
            failures.append("package_contract_hash_not_updated")

    if failures:
        print("W8_PRODUCTIVITY_TRUTH_FAIL",json.dumps(failures,ensure_ascii=False))
        return 8
    print("W8_PRODUCTIVITY_TRUTH_PASS")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
