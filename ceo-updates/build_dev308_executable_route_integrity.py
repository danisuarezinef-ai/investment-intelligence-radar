from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE = REPO / "ceo-updates" / "CEO_1.5.83-rc1-autonomy-runtime-integrity.zip"
ROOT = pathlib.Path(os.environ.get("CEO_DEV308_BUILD_ROOT", "/tmp/ceo-dev308-route-integrity"))
OLD_VERSION = "1.5.83-rc1-autonomy-runtime-integrity"
VERSION = "1.5.84-rc1-executable-route-integrity"
OLD_EPOCH = "dev307-autonomy-runtime-integrity-v1"
EPOCH = "dev308-executable-route-integrity-v1"


def replace_once(path: pathlib.Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_productive_truth() -> None:
    p = ROOT / "ceo_core" / "productive_truth_v2.py"
    s = p.read_text(encoding="utf-8")
    s = s.replace(OLD_EPOCH, EPOCH)
    old1 = "        elif completed == 0 and recoveries >= self.recovery_trip and internal_active and not running:\n"
    new1 = "        elif completed == 0 and recoveries >= self.recovery_trip and internal_active and not running and ready == 0:\n"
    if s.count(old1) != 1:
        raise RuntimeError(f"productive truth zero-completion stall anchor={s.count(old1)}")
    s = s.replace(old1, new1, 1)
    old2 = "        elif useful_rate <= 0 and recoveries >= self.recovery_trip and internal_active and not running:\n"
    new2 = "        elif useful_rate <= 0 and recoveries >= self.recovery_trip and internal_active and not running and ready == 0:\n"
    if s.count(old2) != 1:
        raise RuntimeError(f"productive truth useful-rate stall anchor={s.count(old2)}")
    s = s.replace(old2, new2, 1)
    p.write_text(s, encoding="utf-8")


def patch_recovery_fuse() -> None:
    p = ROOT / "ceo_core" / "recovery_churn_fuse_v2.py"
    s = p.read_text(encoding="utf-8")
    old = """        elif not stalled:
            state.metadata.pop('productive_stall_escape_required',None)
"""
    new = """        elif not stalled:
            state.metadata.pop('productive_stall_escape_required',None)
            # A closed fuse must also release the suppression it owns. Leaving this
            # marker behind can poison a later healthy planning cycle.
            state.metadata.pop('suppress_new_internal_recovery',None)
"""
    if s.count(old) != 1:
        raise RuntimeError(f"recovery fuse close anchor={s.count(old)}")
    p.write_text(s.replace(old, new, 1), encoding="utf-8")


def patch_watchdog() -> None:
    p = ROOT / "ceo_core" / "useful_output_watchdog_v2.py"
    s = p.read_text(encoding="utf-8")
    anchor = """        provider_wait=dict(state.metadata.get('provider_wait_v1') or {})
        # Provider backoff is not a broken route. Give it precedence over any stale
"""
    block = """        provider_wait=dict(state.metadata.get('provider_wait_v1') or {})

        # DEV308 executable-route invariant: queued/running productive work is
        # itself an executable route. Recovery history must never convert it into
        # a global BLOQUEADO state merely because no worker is active at this exact
        # scheduler tick.
        if truth.productive_running or truth.productive_ready:
            fuse=self.fuse.apply(
                state,
                attempts_without_progress=truth.worker_recoveries,
                stalled=False,
            )
            state.metadata.pop('autonomy_stalled',None)
            state.metadata.pop('operator_block_reason',None)
            state.metadata.pop('productive_stall_escape_required',None)
            state.metadata.pop('suppress_new_internal_recovery',None)
            operator='TRABAJANDO' if truth.productive_running else 'PLANIFICANDO'
            state.metadata['operator_productivity_state']=operator
            out=UsefulOutputWatchdogReport(
                operator,False,truth.worker_recoveries,fuse.open,'executable_route',0
            )
            state.metadata[self.KEY]=out.to_dict()
            return out

        # Provider backoff is not a broken route. Give it precedence over any stale
"""
    if s.count(anchor) != 1:
        raise RuntimeError(f"watchdog executable route anchor={s.count(anchor)}")
    p.write_text(s.replace(anchor, block, 1), encoding="utf-8")


def patch_scheduler() -> None:
    p = ROOT / "ceo_core" / "scheduler.py"
    s = p.read_text(encoding="utf-8")
    s = s.replace(f'RELIABILITY_EPOCH = "{OLD_EPOCH}"', f'RELIABILITY_EPOCH = "{EPOCH}"', 1)
    if f'RELIABILITY_EPOCH = "{EPOCH}"' not in s:
        raise RuntimeError("scheduler epoch replacement failed")

    circuit_anchor = """    state.metadata.pop("control_plane_circuit_open", None)
    state.metadata.pop("productive_stall_escape_required", None)

    # DEV307 field migration: release only fail-closed tasks whose evidence
"""
    circuit_new = """    state.metadata.pop("control_plane_circuit_open", None)
    state.metadata.pop("productive_stall_escape_required", None)

    # DEV308: rebase the separate recovery-churn fuse and remove only stale
    # operator/suppression state when concrete productive execution is already
    # available. Protected task-level blocks remain untouched.
    churn = state.metadata.setdefault("recovery_churn_fuse_v2", {})
    churn.update({
        "open": False,
        "attempts_without_progress": 0,
        "retired": 0,
        "reason": "reliability epoch migrated",
    })
    executable_productive = [
        task for task in state.leaf_tasks
        if is_productive(task, state)
        and task.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING}
    ]
    if executable_productive:
        state.metadata.pop("suppress_new_internal_recovery", None)
        state.metadata.pop("autonomy_stalled", None)
        state.metadata.pop("operator_block_reason", None)
        state.metadata["operator_productivity_state"] = (
            "TRABAJANDO" if any(t.status == TaskStatus.RUNNING for t in executable_productive)
            else "PLANIFICANDO"
        )

    # DEV307 field migration: release only fail-closed tasks whose evidence
"""
    if s.count(circuit_anchor) != 1:
        raise RuntimeError(f"scheduler migration anchor={s.count(circuit_anchor)}")
    s = s.replace(circuit_anchor, circuit_new, 1)

    old_status = """        truth_state = str(self.state.metadata.get("operator_productivity_state") or "").upper()
        if truth_state in {"ATASCADO", "BLOQUEADO"}:
            return "BLOQUEADO"
        if truth_state == "REPLANIFICANDO":
            return "CORRIGIENDO"

        # Active execution is authoritative. A durable autonomy_stalled marker can
        # legitimately survive from a prior watchdog cycle until the next save; it
        # must never override a currently running worker. Likewise a blocked branch
        # does not mean the whole CEO is blocked while another branch is executing.
        active = [self.state.tasks.get(tid) for tid in self._active]
        active = [t for t in active if t is not None]
        if active:
            if any(t.metadata.get("verification_task") for t in active):
                return "VERIFICANDO"
            if any(t.metadata.get("autonomy_recovery") or t.metadata.get("controller_action") == "correct" for t in active):
                return "CORRIGIENDO"
            return "TRABAJANDO"

        # If executable work is queued, CEO is planning/dispatching rather than
        # globally blocked, even if another leaf is blocked.
        if any(t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.WAITING} for t in leaves):
            return "PLANIFICANDO"
"""
    new_status = """        # Active execution and genuinely executable queued work are authoritative.
        # A stale watchdog/operator marker must never override them.
        active = [self.state.tasks.get(tid) for tid in self._active]
        active = [t for t in active if t is not None]
        if active:
            if any(t.metadata.get("verification_task") for t in active):
                return "VERIFICANDO"
            if any(t.metadata.get("autonomy_recovery") or t.metadata.get("controller_action") == "correct" for t in active):
                return "CORRIGIENDO"
            return "TRABAJANDO"

        if any(t.status in {TaskStatus.READY, TaskStatus.RETRY} for t in leaves):
            return "PLANIFICANDO"

        truth_state = str(self.state.metadata.get("operator_productivity_state") or "").upper()
        if truth_state in {"ATASCADO", "BLOQUEADO"}:
            return "BLOQUEADO"
        if truth_state == "REPLANIFICANDO":
            return "CORRIGIENDO"

        # WAITING is soft pending work, not proof of a hard global block.
        if any(t.status == TaskStatus.WAITING for t in leaves):
            return "PLANIFICANDO"
"""
    if s.count(old_status) != 1:
        raise RuntimeError(f"operational status precedence anchor={s.count(old_status)}")
    s = s.replace(old_status, new_status, 1)
    p.write_text(s, encoding="utf-8")


def patch_decomposer() -> None:
    p = ROOT / "ceo_core" / "decomposer.py"
    s = p.read_text(encoding="utf-8")

    old_complex = """        complex_terms = (
            "research", "investigate", "compare", "audit", "analyse", "analyze",
            "multiple", "several", " all ", "systematic", "review ", "repository",
            "implement", "refactor", "deploy", "integrate", "across ", "pipeline",
            "database", "architecture", "migration", "benchmark", "experiment",
        )
"""
    new_complex = """        complex_terms = (
            "research", "investigate", "compare", "audit", "analyse", "analyze",
            "multiple", "several", " all ", "systematic", "review ", "repository",
            "implement", "refactor", "deploy", "integrate", "across ", "pipeline",
            "database", "architecture", "migration", "benchmark", "experiment",
            "investiga", "compar", "audita", "sistemát", "sistemat", "repositorio",
            "implementa", "refactoriza", "despliega", "integra", "base de datos",
            "arquitectura", "migración", "migracion", "experimento", "múltiples",
            "multiples", "varios archivos", "todos los archivos",
        )
"""
    if s.count(old_complex) != 1:
        raise RuntimeError(f"decomposer complex terms anchor={s.count(old_complex)}")
    s = s.replace(old_complex, new_complex, 1)

    old_compact = """        # Conservative compact mode: it is used only for bounded, single-output
        # requests. Ambiguous/complex goals keep the full six-phase decomposition.
        compact = (
            len(text) <= 260
            and complex_score == 0
            and conjunctions <= 2
            and simple_score >= 1
        )
        return {
            "mode": "compact" if compact else "full",
            "characters": len(text),
            "complex_score": complex_score,
            "simple_output_score": simple_score,
            "conjunctions": conjunctions,
        }
"""
    new_compact = """        # DEV308: verbosity is not complexity. A detailed specification for one
        # explicit output file remains a bounded single-deliverable goal.
        file_hits = sum(low.count(ext) for ext in (".md", ".txt", ".json", ".csv", ".html"))
        single_explicit_file = file_hits == 1
        compact = (
            complex_score == 0
            and simple_score >= 1
            and (
                (single_explicit_file and len(text) <= 1200)
                or (len(text) <= 260 and conjunctions <= 2)
            )
        )
        return {
            "mode": "compact" if compact else "full",
            "characters": len(text),
            "complex_score": complex_score,
            "simple_output_score": simple_score,
            "conjunctions": conjunctions,
            "single_explicit_file": single_explicit_file,
            "file_hits": file_hits,
        }
"""
    if s.count(old_compact) != 1:
        raise RuntimeError(f"decomposer compact anchor={s.count(old_compact)}")
    p.write_text(s.replace(old_compact, new_compact, 1), encoding="utf-8")


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

    patch_productive_truth()
    patch_recovery_fuse()
    patch_watchdog()
    patch_scheduler()
    patch_decomposer()
    update_version_and_contract()

    print(json.dumps({
        "ok": True,
        "root": str(ROOT),
        "base": OLD_VERSION,
        "version": VERSION,
        "epoch": EPOCH,
        "invariants": [
            "productive_ready_is_executable_route",
            "closed_fuse_clears_owned_suppression",
            "executable_route_precedes_stale_blocked_operator_state",
            "single_explicit_file_verbosity_not_complexity",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
