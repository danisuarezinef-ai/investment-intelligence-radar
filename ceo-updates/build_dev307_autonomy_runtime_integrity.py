from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE = REPO / "ceo-updates" / "CEO_1.5.82-rc1-autonomy-bootstrap.zip"
ROOT = pathlib.Path(os.environ.get("CEO_DEV307_BUILD_ROOT", "/tmp/ceo-dev307"))
VERSION = "1.5.83-rc1-autonomy-runtime-integrity"
OLD_VERSION = "1.5.82-rc1-autonomy-bootstrap"
EPOCH = "dev307-autonomy-runtime-integrity-v1"


def replace_once(path: pathlib.Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {n}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_scheduler() -> None:
    p = ROOT / "ceo_core" / "scheduler.py"
    s = p.read_text(encoding="utf-8")

    s = s.replace(
        "from .blocked_safe_state_v1 import mark_blocked_safe, preserve_blocked_safe",
        "from .blocked_safe_state_v1 import mark_blocked_safe, preserve_blocked_safe, release_blocked_safe",
        1,
    )

    s, n = re.subn(
        r'RELIABILITY_EPOCH\s*=\s*"[^"]+"',
        f'RELIABILITY_EPOCH = "{EPOCH}"',
        s,
        count=1,
    )
    if n != 1:
        raise RuntimeError("scheduler reliability epoch anchor missing")

    old_collect = '''    def _collect_finished(self) -> None:
        finished = [task_id for task_id, future in self._active.items() if future.done()]
        for task_id in finished:
            self._active.pop(task_id, None)
            self._active_provider.pop(task_id, None)
'''
    new_collect = '''    def _collect_finished(self) -> None:
        finished = [task_id for task_id, future in self._active.items() if future.done()]
        for task_id in finished:
            future = self._active.get(task_id)
            task = self.state.tasks.get(task_id)
            provider = self._active_provider.get(task_id) or (task.provider_name if task else None)

            # DEV307 invariant: a completed Future may never disappear while its
            # durable task still says RUNNING. That state was interpreted by the
            # worker watchdog as an orphan and created recovery storms in the field.
            if task is not None and task.status == TaskStatus.RUNNING:
                outcome = "completed_without_terminal_state"
                detail = ""
                if future is not None:
                    if future.cancelled():
                        outcome = "cancelled_without_state_handoff"
                    else:
                        try:
                            exc = future.exception()
                        except BaseException as err:  # cancelled/broken future access
                            exc = err
                        if exc is not None:
                            outcome = "exception_without_state_handoff"
                            detail = f"{type(exc).__name__}: {exc}"[:1000]

                count = int(task.metadata.get("worker_terminal_normalization_count", 0) or 0) + 1
                task.metadata["worker_terminal_normalization_count"] = count
                task.metadata["worker_terminal_normalization_v1"] = {
                    "outcome": outcome,
                    "detail": detail,
                    "provider": provider,
                    "count": count,
                    "ts": utcnow().isoformat(),
                    "recovery_budget_consumed": False,
                }
                task.metadata["provider_stage"] = "terminal_normalized"
                task.metadata["provider_stage_ts"] = utcnow().isoformat()
                task.metadata["live_recovery_reason"] = "worker_future_finished_without_durable_state"
                task.worker_id = None

                # This is an internal bookkeeping failure, not a provider/task
                # failure. Permit at most two normalizations before failing the unit
                # so fallback/replanning can take over without an infinite loop.
                if count <= 2:
                    task.status = TaskStatus.RETRY
                    task.attempts = max(0, int(task.attempts) - 1)
                    task.metadata["retry_after_ts"] = time.time() + 1.0
                    if not (task.result or "").strip():
                        task.result = "Internal worker handoff normalized; retrying without consuming recovery budget."
                else:
                    task.status = TaskStatus.FAILED
                    task.result = (task.result or "") + (
                        "\nInternal worker handoff failed repeatedly; bounded terminal failure for autonomous replanning."
                    )

                hist = self.state.metadata.setdefault("worker_terminal_normalization_history", [])
                hist.append({
                    "task_id": task.id,
                    "outcome": outcome,
                    "count": count,
                    "provider": provider,
                    "ts": utcnow().isoformat(),
                    "recovery_budget_consumed": False,
                })
                del hist[:-200]

            self._active.pop(task_id, None)
            self._active_provider.pop(task_id, None)
'''
    if s.count(old_collect) != 1:
        raise RuntimeError(f"collect_finished anchor count={s.count(old_collect)}")
    s = s.replace(old_collect, new_collect, 1)

    migration_anchor = '''    # Retire only stale internal units that the OLD recovery guard made
    # permanently undispatchable. Do not release protected human gates and
    # do not erase the blocked-safe evidence.
    retired = []
'''
    migration_new = '''    # DEV307 field migration: release only fail-closed tasks whose evidence
    # proves they were blocked by the 1.5.82 orphan-worker bookkeeping defect.
    # Legitimate safety/human gates remain untouched.
    released_orphan_worker_tasks = []
    recovery_history = list(state.metadata.get("worker_recovery_history") or [])
    for task in state.leaf_tasks:
        if protected_human_gate(task):
            continue
        reason = str(task.metadata.get("blocked_safe_reason") or "")
        source = str(task.metadata.get("blocked_safe_source") or "")
        orphan_history = any(
            str(row.get("task_id") or "") == task.id
            and str(row.get("reason") or "") == "orphan_running_without_live_future"
            for row in recovery_history
            if isinstance(row, dict)
        )
        affected = (
            reason == "orphan_running_without_live_future"
            or (
                reason == "worker_recovery_budget_exhausted"
                and source in {"worker_recovery_supervisor", "worker_watchdog"}
                and orphan_history
            )
        )
        if affected and (task.metadata.get("blocked_safe") or task.metadata.get("manual_release_required")):
            row = release_blocked_safe(
                task,
                reason="DEV307 repairs false orphan-worker field block",
                strategy="finished_future_durable_state_normalization",
            )
            if row.get("released"):
                task.metadata.pop("live_recovery_reason", None)
                task.metadata.pop("strategy_change_requested", None)
                task.metadata.pop("strategy_change_applied", None)
                task.metadata.pop("strategy_change_from", None)
                task.metadata.pop("recovery_strategy", None)
                task.metadata.pop("recovery_storm_guard_v1", None)
                task.metadata["dev307_orphan_field_migration"] = now
                task.attempts = max(0, min(int(task.attempts), max(0, int(task.max_attempts) - 1)))
                task.metadata["retry_after_ts"] = 0
                released_orphan_worker_tasks.append(task.id)

    # Retire only stale internal units that the OLD recovery guard made
    # permanently undispatchable. Do not release protected human gates and
    # do not erase the blocked-safe evidence.
    retired = []
'''
    if s.count(migration_anchor) != 1:
        raise RuntimeError(f"migration anchor count={s.count(migration_anchor)}")
    s = s.replace(migration_anchor, migration_new, 1)

    marker_anchor = '''        "retired_stale_internal_task_ids": retired,
    })
    return {"changed": True, "epoch": RELIABILITY_EPOCH, "retired": retired, "previous": previous}
'''
    marker_new = '''        "retired_stale_internal_task_ids": retired,
        "released_false_orphan_task_ids": released_orphan_worker_tasks,
    })
    return {
        "changed": True,
        "epoch": RELIABILITY_EPOCH,
        "retired": retired,
        "released_false_orphan_task_ids": released_orphan_worker_tasks,
        "previous": previous,
    }
'''
    if s.count(marker_anchor) != 1:
        raise RuntimeError(f"migration return anchor count={s.count(marker_anchor)}")
    s = s.replace(marker_anchor, marker_new, 1)

    p.write_text(s, encoding="utf-8")


def patch_productive_truth() -> None:
    p = ROOT / "ceo_core" / "productive_truth_v2.py"
    s = p.read_text(encoding="utf-8")
    s = re.sub(r'"epoch"\) != "[^"]+"', f'"epoch") != "{EPOCH}"', s, count=1)
    s = re.sub(r'"epoch": "[^"]+"', f'"epoch": "{EPOCH}"', s, count=1)
    if EPOCH not in s:
        raise RuntimeError("productive truth epoch patch failed")
    p.write_text(s, encoding="utf-8")


def patch_quality_correction() -> None:
    p = ROOT / "ceo_core" / "self_correction.py"
    s = p.read_text(encoding="utf-8")

    anchor = '''        history = task.metadata.setdefault("self_correction_history", [])
        same_signature = sum(1 for row in history if row.get("signature") == verdict.signature)
        max_inline = max(1, int(state.metadata.get("max_inline_quality_corrections", 2)))
        event: dict[str, Any] = {
'''
    replacement = '''        history = task.metadata.setdefault("self_correction_history", [])
        same_signature = sum(1 for row in history if row.get("signature") == verdict.signature)
        max_inline = max(1, int(state.metadata.get("max_inline_quality_corrections", 2)))
        generation = int(task.metadata.get("repair_generation", 0) or 0)
        max_generations = max(1, int(state.metadata.get("max_quality_repair_generations", 2)))
        lineage_root = str(task.metadata.get("quality_repair_root_id") or task.id)
        task.metadata["quality_repair_root_id"] = lineage_root
        event: dict[str, Any] = {
'''
    if s.count(anchor) != 1:
        raise RuntimeError(f"self-correction header anchor count={s.count(anchor)}")
    s = s.replace(anchor, replacement, 1)

    spawn_anchor = '''        replacement = self._spawn_replacement(state, task, verdict)
        event["action"] = "replacement_task"
        event["replacement_task_id"] = replacement.id
        self._record(state, task, event)
        return event
'''
    spawn_new = '''        # Bound the entire repair lineage, not only retries of one task id.
        # 1.5.82 changed the quality signature when a replacement received a new
        # task id, allowing an unbounded Repair -> Repair -> Repair chain.
        if generation >= max_generations:
            task.status = TaskStatus.FAILED
            task.metadata["quality_repair_exhausted"] = True
            task.metadata["quality_repair_generation"] = generation
            task.metadata["quality_repair_root_id"] = lineage_root
            task.result = (
                (task.result or "")
                + "\nQuality repair lineage exhausted; handing control to autonomous replanning."
            ).strip()
            event["action"] = "bounded_quality_failure"
            event["repair_generation"] = generation
            event["max_quality_repair_generations"] = max_generations
            self._record(state, task, event)
            return event

        replacement = self._spawn_replacement(state, task, verdict)
        replacement.metadata["quality_repair_root_id"] = lineage_root
        replacement.metadata["quality_repair_generation"] = generation + 1
        event["action"] = "replacement_task"
        event["replacement_task_id"] = replacement.id
        event["repair_generation"] = generation + 1
        self._record(state, task, event)
        return event
'''
    if s.count(spawn_anchor) != 1:
        raise RuntimeError(f"quality spawn anchor count={s.count(spawn_anchor)}")
    s = s.replace(spawn_anchor, spawn_new, 1)

    # Do not carry per-task retry history across a replacement; lineage bounds now
    # live in repair_generation/root_id and are independent of task ids.
    tuple_anchor = '''            "quality_gate", "quality_correction_pending", "provider_stage", "provider_stage_ts",
            "last_provider_error", "retry_after_ts", "empty_provider_response",
'''
    tuple_new = '''            "quality_gate", "quality_correction_pending", "provider_stage", "provider_stage_ts",
            "last_provider_error", "retry_after_ts", "empty_provider_response",
            "self_correction_history",
'''
    if s.count(tuple_anchor) != 1:
        raise RuntimeError(f"replacement metadata anchor count={s.count(tuple_anchor)}")
    s = s.replace(tuple_anchor, tuple_new, 1)

    p.write_text(s, encoding="utf-8")


def update_version_and_contract() -> None:
    for rel in ("scripts/ceo_stdlib_work_mode.py", "scripts/install_windows_bootstrap.py"):
        p = ROOT / rel
        if p.is_file():
            p.write_text(p.read_text(encoding="utf-8").replace(OLD_VERSION, VERSION), encoding="utf-8")

    cpath = ROOT / "CEO_UPDATE_PACKAGE.json"
    contract = json.loads(cpath.read_text(encoding="utf-8"))
    contract["app_version"] = VERSION
    hashes = dict(contract.get("file_hashes") or {})
    for rel in hashes:
        fp = ROOT / rel
        if not fp.is_file():
            raise RuntimeError(f"missing contract path {rel}")
        hashes[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
    contract["file_hashes"] = hashes
    cpath.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    if not BASE.is_file():
        raise RuntimeError(f"missing base {BASE}")
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)
    with zipfile.ZipFile(BASE) as z:
        z.extractall(ROOT)

    patch_scheduler()
    patch_productive_truth()
    patch_quality_correction()
    update_version_and_contract()

    print(json.dumps({"ok": True, "root": str(ROOT), "version": VERSION, "epoch": EPOCH}, indent=2))


if __name__ == "__main__":
    main()
