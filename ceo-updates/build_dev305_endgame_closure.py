from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import zipfile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE_ZIP = REPO_ROOT / "ceo-updates" / "CEO_1.5.80-rc1-provider-resilience.zip"
BUILD_ROOT = pathlib.Path("/tmp/dev305")
OLD_VERSION = "1.5.80-rc1-provider-resilience"
NEW_VERSION = "1.5.81-rc1-endgame-closure"
NEW_EPOCH = "dev305-endgame-closure-v1"


def replace_once(path: pathlib.Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_scheduler() -> None:
    p = BUILD_ROOT / "ceo_core" / "scheduler.py"
    text = p.read_text(encoding="utf-8")
    text = text.replace(
        'RELIABILITY_EPOCH = "dev304-provider-resilience-v1"',
        f'RELIABILITY_EPOCH = "{NEW_EPOCH}"',
        1,
    )
    if f'RELIABILITY_EPOCH = "{NEW_EPOCH}"' not in text:
        raise RuntimeError("DEV305 reliability epoch replacement failed")

    # DEV304 globally suppressed ensure_progress while any provider wait existed.
    # That prevents the local control plane from constructing the final continuity
    # route at 99%. Provider-specific task backoff already prevents dispatch churn,
    # so the global suppression is both unnecessary and harmful.
    old = '                and not bool((self.state.metadata.get("provider_wait_v1") or {}).get("active"))\n'
    if text.count(old) != 1:
        raise RuntimeError(f"provider-wait progress suppression anchor: {text.count(old)}")
    text = text.replace(old, "", 1)
    p.write_text(text, encoding="utf-8")


def patch_productive_truth() -> None:
    p = BUILD_ROOT / "ceo_core" / "productive_truth_v2.py"
    text = p.read_text(encoding="utf-8")
    text = text.replace(
        'if meta.get("epoch") != "dev304-provider-resilience-v1":',
        f'if meta.get("epoch") != "{NEW_EPOCH}":',
        1,
    )
    text = text.replace(
        '"epoch": "dev304-provider-resilience-v1",',
        f'"epoch": "{NEW_EPOCH}",',
        1,
    )
    if NEW_EPOCH not in text:
        raise RuntimeError("productive truth DEV305 epoch replacement failed")
    p.write_text(text, encoding="utf-8")


def patch_autonomous_loop() -> None:
    p = BUILD_ROOT / "ceo_core" / "autonomous_loop.py"
    text = p.read_text(encoding="utf-8")
    anchor = '''        # Recovery ordering is deliberate: do not jump directly to replanning.
        # The incident ladder below owns retry -> fresh worker -> clean audit ->
        # partial replan -> global replan, which keeps recovery bounded and auditable.
'''
    block = '''        # DEV305: an external-provider wait is a legitimate executable route state,
        # not an autonomy stall. We deliberately reach this point only AFTER the
        # goal-continuity-audit creation block above, so a 99% project may still
        # create its final audit locally. Once all remaining nonterminal work is
        # waiting on a provider, stop recovery/replanning churn until its retry time.
        provider_wait = dict(state.metadata.get("provider_wait_v1") or {})
        provider_wait_tasks = [
            t for t in state.leaf_tasks
            if t.status == TaskStatus.BLOCKED
            and bool(t.metadata.get("waiting_provider_v1"))
        ]
        if provider_wait.get("active") and provider_wait_tasks:
            state.metadata["autonomy_stall_cycles"] = 0
            state.metadata.pop("autonomy_stalled", None)
            state.metadata.pop("productive_stall_escape_required", None)
            state.metadata.pop("suppress_new_internal_recovery", None)
            state.metadata["endgame_route_v1"] = {
                "status": "waiting_provider",
                "task_ids": [t.id for t in provider_wait_tasks[:20]],
                "category": str(provider_wait.get("category") or "provider_unavailable"),
                "retry_after_ts": provider_wait.get("retry_after_ts"),
            }
            return {
                "status": "waiting_provider",
                "created": 0,
                "changed": 0,
                "task_ids": [t.id for t in provider_wait_tasks[:20]],
            }

'''
    if text.count(anchor) != 1:
        raise RuntimeError(f"autonomous-loop recovery anchor: {text.count(anchor)}")
    text = text.replace(anchor, block + anchor, 1)
    p.write_text(text, encoding="utf-8")


def patch_watchdog() -> None:
    p = BUILD_ROOT / "ceo_core" / "useful_output_watchdog_v2.py"
    text = p.read_text(encoding="utf-8")
    anchor = '''    def tick(self,state:ProjectState)->UsefulOutputWatchdogReport:
        truth=self.truth.assess(state)
        fuse=self.fuse.apply(state,attempts_without_progress=truth.worker_recoveries,stalled=truth.stalled)
        action='none';repaired=0
'''
    new = '''    def tick(self,state:ProjectState)->UsefulOutputWatchdogReport:
        truth=self.truth.assess(state)
        provider_wait=dict(state.metadata.get('provider_wait_v1') or {})
        # Provider backoff is not a broken route. Give it precedence over any stale
        # fuse/operator state left by a previous cycle and do not invoke fallback.
        if provider_wait.get('active') and truth.status=='waiting_provider':
            state.metadata.pop('productive_stall_escape_required',None)
            state.metadata.pop('suppress_new_internal_recovery',None)
            state.metadata['operator_productivity_state']='ESPERANDO PROVEEDOR'
            state.metadata['operator_block_reason']=(
                'Proveedor temporalmente no disponible; reintento acotado sin consumir recuperaciones.'
            )
            out=UsefulOutputWatchdogReport(
                'ESPERANDO PROVEEDOR',False,truth.worker_recoveries,False,'provider_wait',0
            )
            state.metadata[self.KEY]=out.to_dict()
            return out
        fuse=self.fuse.apply(state,attempts_without_progress=truth.worker_recoveries,stalled=truth.stalled)
        action='none';repaired=0
'''
    if text.count(anchor) != 1:
        raise RuntimeError(f"watchdog anchor: {text.count(anchor)}")
    text = text.replace(anchor, new, 1)

    old = """            else:
                state.metadata['operator_productivity_state']='BLOQUEADO'
"""
    new2 = """            else:
                state.metadata['operator_productivity_state']='BLOQUEADO'
                blocked=[
                    t for t in state.leaf_tasks
                    if t.status in {TaskStatus.BLOCKED,TaskStatus.FAILED,TaskStatus.NEEDS_REVIEW}
                ] if hasattr(TaskStatus,'BLOCKED') else []
                reason='; '.join(
                    str(t.result or t.metadata.get('blocked_safe_reason') or t.title)
                    for t in blocked[:3]
                )
                state.metadata['operator_block_reason']=reason or 'No existe una ruta ejecutable después del fallback.'
"""
    # Need TaskStatus import for actionable reason.
    text = text.replace(
        "from .models import ProjectState\n",
        "from .models import ProjectState,TaskStatus\n",
        1,
    )
    if text.count(old) != 1:
        raise RuntimeError(f"watchdog blocked reason anchor: {text.count(old)}")
    text = text.replace(old, new2, 1)
    p.write_text(text, encoding="utf-8")


def patch_fallback() -> None:
    p = BUILD_ROOT / "ceo_core" / "productive_fallback_orchestrator_v1.py"
    text = p.read_text(encoding="utf-8")
    old = "        candidates=[t for t in state.leaf_tasks if is_productive(t,state) and t.status in {TaskStatus.FAILED,TaskStatus.BLOCKED,TaskStatus.RETRY,TaskStatus.NEEDS_REVIEW} and not t.metadata.get('explicit_human_gate') and not is_blocked_safe(t)]\n"
    new = "        candidates=[t for t in state.leaf_tasks if is_productive(t,state) and t.status in {TaskStatus.FAILED,TaskStatus.BLOCKED,TaskStatus.RETRY,TaskStatus.NEEDS_REVIEW} and not t.metadata.get('explicit_human_gate') and not is_blocked_safe(t) and not t.metadata.get('waiting_provider_v1')]\n"
    if text.count(old) != 1:
        raise RuntimeError(f"fallback provider-wait exclusion anchor: {text.count(old)}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_work_mode() -> None:
    p = BUILD_ROOT / "scripts" / "ceo_stdlib_work_mode.py"
    text = p.read_text(encoding="utf-8")

    # Action banner must never hide the real block reason behind a generic sentence.
    old = """else if(s.active&&real==='BLOQUEADO'){const bs=s.autonomy_stalled?.blockers||[];const blocked=(s.queue||[]).filter(t=>['blocked','failed','needs_review'].includes(t.status)).slice(0,3).map(t=>t.title+' ['+t.status+']');const why=(bs.length?bs:blocked);$('actionBanner').className='banner errb';$('actionBanner').textContent='✗ CEO está BLOQUEADO.'+(why.length?' Causa: '+why.join(' · '):' El watchdog no encontró una ruta ejecutable.')}"""
    new = """else if(s.active&&real==='BLOQUEADO'){const bs=s.autonomy_stalled?.blockers||[];const blocked=(s.queue||[]).filter(t=>['blocked','failed','needs_review'].includes(t.status)).slice(0,3).map(t=>t.title+' ['+t.status+']');const why=(bs.length?bs:blocked);const explicit=s.operator_block_reason||s.metadata?.operator_block_reason||'';$('actionBanner').className='banner errb';$('actionBanner').textContent='✗ CEO está BLOQUEADO. Causa: '+(why.length?why.join(' · '):(explicit||'bloqueo sin causa estructurada; requiere diagnóstico'))}"""
    if text.count(old) != 1:
        raise RuntimeError(f"UI blocked banner anchor: {text.count(old)}")
    text = text.replace(old, new, 1)

    # Expose block reason in snapshot if metadata contains it.
    snap_anchor = '''            "operational_status": operational_status,
'''
    snap_new = '''            "operational_status": operational_status,
            "operator_block_reason": state.metadata.get("operator_block_reason"),
'''
    if text.count(snap_anchor) != 1:
        raise RuntimeError(f"snapshot block reason anchor: {text.count(snap_anchor)}")
    text = text.replace(snap_anchor, snap_new, 1)

    text = text.replace(OLD_VERSION, NEW_VERSION)
    p.write_text(text, encoding="utf-8")


def update_contract() -> None:
    p = BUILD_ROOT / "CEO_UPDATE_PACKAGE.json"
    contract = json.loads(p.read_text(encoding="utf-8"))
    contract["app_version"] = NEW_VERSION
    hashes = dict(contract.get("file_hashes") or {})
    for rel in list(hashes):
        fp = BUILD_ROOT / rel
        if not fp.is_file():
            raise RuntimeError(f"missing contract file: {rel}")
        hashes[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
    contract["file_hashes"] = hashes
    p.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    if not BASE_ZIP.is_file():
        raise RuntimeError(f"missing base ZIP: {BASE_ZIP}")
    shutil.rmtree(BUILD_ROOT, ignore_errors=True)
    BUILD_ROOT.mkdir(parents=True)
    with zipfile.ZipFile(BASE_ZIP) as zf:
        zf.extractall(BUILD_ROOT)

    patch_scheduler()
    patch_productive_truth()
    patch_autonomous_loop()
    patch_watchdog()
    patch_fallback()
    patch_work_mode()

    bootstrap = BUILD_ROOT / "scripts" / "install_windows_bootstrap.py"
    if bootstrap.exists():
        bootstrap.write_text(
            bootstrap.read_text(encoding="utf-8").replace(OLD_VERSION, NEW_VERSION),
            encoding="utf-8",
        )

    update_contract()
    print(json.dumps({"ok": True, "root": str(BUILD_ROOT), "version": NEW_VERSION}, indent=2))


if __name__ == "__main__":
    main()
