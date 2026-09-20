from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE = REPO / "ceo-updates" / "CEO_1.5.82-rc1-autonomy-bootstrap.zip"
ROOT = pathlib.Path(os.environ.get("CEO_DEV307_BUILD_ROOT", "/tmp/ceo-dev307-autonomy-invariants"))
VERSION = "1.5.83-rc1-autonomy-invariants"
OLD_VERSION = "1.5.82-rc1-autonomy-bootstrap"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)
    with zipfile.ZipFile(BASE) as z:
        z.extractall(ROOT)

    # Invariant 1:
    # A finished asyncio Future may not disappear from the in-memory active map while
    # its durable Task is still RUNNING. Normalize that impossible state exactly once,
    # without spending worker recovery budget, before removing the Future.
    p = ROOT / "ceo_core" / "scheduler.py"
    s = p.read_text(encoding="utf-8")
    old = '''    def _collect_finished(self) -> None:
        finished = [task_id for task_id, future in self._active.items() if future.done()]
        for task_id in finished:
            self._active.pop(task_id, None)
            self._active_provider.pop(task_id, None)
'''
    new = '''    def _collect_finished(self) -> None:
        finished = [task_id for task_id, future in self._active.items() if future.done()]
        for task_id in finished:
            future = self._active.get(task_id)
            task = self.state.tasks.get(task_id)
            if task is not None and task.status == TaskStatus.RUNNING:
                # A completed Future with durable RUNNING state is an internal
                # finalization inconsistency, not a dead worker. Repair the state
                # before removing the Future so WorkerRecoverySupervisor never sees
                # a false orphan and never consumes recovery budget for it.
                future_error = ""
                if future is not None:
                    try:
                        if not future.cancelled():
                            exc = future.exception()
                            if exc is not None:
                                future_error = f"{type(exc).__name__}: {exc}"[:1000]
                    except BaseException as exc:  # inspection must never strand state
                        future_error = f"{type(exc).__name__}: {exc}"[:1000]

                task.worker_id = None
                if int(task.attempts or 0) < int(task.max_attempts or 0):
                    task.status = TaskStatus.RETRY
                    task.metadata["retry_after_ts"] = 0
                    if not (task.result or "").strip():
                        task.result = "RETRY: worker future ended before durable task-state finalization."
                else:
                    task.status = TaskStatus.FAILED
                    if not (task.result or "").strip():
                        task.result = "FAILED: worker future ended before durable task-state finalization."

                task.metadata["provider_stage"] = "future_finished_state_reconciled"
                task.metadata["provider_stage_ts"] = utcnow().isoformat()
                row = {
                    "task_id": task.id,
                    "status": task.status.value,
                    "future_error": future_error,
                    "ts": utcnow().isoformat(),
                    "recovery_budget_consumed": False,
                }
                task.metadata["worker_future_state_reconciled_v1"] = row
                ledger = self.state.metadata.setdefault("worker_future_state_reconciliations_v1", [])
                ledger.append(dict(row))
                del ledger[:-200]

            self._active.pop(task_id, None)
            self._active_provider.pop(task_id, None)
'''
    s = replace_once(s, old, new, "scheduler _collect_finished")
    p.write_text(s, encoding="utf-8")

    # Invariant 2:
    # Quality-repair retry/replacement is bounded by a lineage signature that does
    # not contain task.id. Replacement tasks therefore cannot reset the correction
    # budget merely by receiving a new id.
    p = ROOT / "ceo_core" / "self_correction.py"
    s = p.read_text(encoding="utf-8")

    old = '''        history = task.metadata.setdefault("self_correction_history", [])
        same_signature = sum(1 for row in history if row.get("signature") == verdict.signature)
        max_inline = max(1, int(state.metadata.get("max_inline_quality_corrections", 2)))
        event: dict[str, Any] = {
            "ts": _utcnow(),
            "task_id": task.id,
            "signature": verdict.signature,
            "reasons": list(verdict.reasons),
            "same_signature_seen": same_signature,
        }
'''
    new = '''        history = task.metadata.setdefault("self_correction_history", [])
        same_signature = sum(1 for row in history if row.get("signature") == verdict.signature)
        lineage_signature = "|".join(sorted(str(x) for x in verdict.reasons)) + f"|{float(verdict.threshold):.4f}"
        same_lineage_signature = sum(
            1 for row in history if row.get("lineage_signature") == lineage_signature
        )
        max_inline = max(1, int(state.metadata.get("max_inline_quality_corrections", 2)))
        generation = max(0, int(task.metadata.get("repair_generation", 0) or 0))
        max_generations = max(0, int(state.metadata.get("max_quality_repair_generations", 2)))
        event: dict[str, Any] = {
            "ts": _utcnow(),
            "task_id": task.id,
            "signature": verdict.signature,
            "lineage_signature": lineage_signature,
            "reasons": list(verdict.reasons),
            "same_signature_seen": same_signature,
            "same_lineage_signature_seen": same_lineage_signature,
            "repair_generation": generation,
            "max_quality_repair_generations": max_generations,
        }
'''
    s = replace_once(s, old, new, "self correction lineage setup")

    old = '''        if same_signature < max_inline and task.attempts < task.max_attempts:
            task.status = TaskStatus.RETRY
            task.metadata["retry_after_ts"] = 0
            task.metadata["quality_correction_pending"] = True
            task.metadata["next_instruction"] = self._repair_instruction(task, verdict)
            event["action"] = "inline_retry"
            self._record(state, task, event)
            return event

        replacement = self._spawn_replacement(state, task, verdict)
        event["action"] = "replacement_task"
        event["replacement_task_id"] = replacement.id
        self._record(state, task, event)
        return event
'''
    new = '''        if same_lineage_signature < max_inline and task.attempts < task.max_attempts:
            task.status = TaskStatus.RETRY
            task.metadata["retry_after_ts"] = 0
            task.metadata["quality_correction_pending"] = True
            task.metadata["next_instruction"] = self._repair_instruction(task, verdict)
            event["action"] = "inline_retry"
            self._record(state, task, event)
            return event

        if generation >= max_generations:
            # Bounded fail-closed exit. Do not spawn another Repair: task with a
            # fresh id because that would reset the effective quality-repair budget.
            task.status = TaskStatus.FAILED
            task.metadata.pop("quality_correction_pending", None)
            task.metadata["quality_repair_exhausted_v1"] = {
                "lineage_signature": lineage_signature,
                "generation": generation,
                "max_generations": max_generations,
                "reasons": list(verdict.reasons),
                "ts": _utcnow(),
            }
            event["action"] = "quality_repair_exhausted"
            self._record(state, task, event)
            return event

        replacement = self._spawn_replacement(state, task, verdict)
        event["action"] = "replacement_task"
        event["replacement_task_id"] = replacement.id
        self._record(state, task, event)
        return event
'''
    s = replace_once(s, old, new, "self correction bounded replacement")
    p.write_text(s, encoding="utf-8")

    # Exact version identity.
    for rel in ("scripts/ceo_stdlib_work_mode.py", "scripts/install_windows_bootstrap.py"):
        q = ROOT / rel
        if q.is_file():
            t = q.read_text(encoding="utf-8")
            q.write_text(t.replace(OLD_VERSION, VERSION), encoding="utf-8")

    contract_path = ROOT / "CEO_UPDATE_PACKAGE.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["app_version"] = VERSION
    hashes = dict(contract.get("file_hashes") or {})
    for rel in hashes:
        fp = ROOT / rel
        if not fp.is_file():
            raise RuntimeError(f"missing contract path {rel}")
        hashes[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
    contract["file_hashes"] = hashes
    contract_path.write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "ok": True,
        "root": str(ROOT),
        "version": VERSION,
        "base": OLD_VERSION,
        "invariants": [
            "finished_future_never_leaves_durable_running",
            "quality_repair_lineage_is_bounded_across_replacement_ids",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
