from __future__ import annotations

import hashlib
import json
import os
import pathlib


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def apply(root: pathlib.Path) -> dict:
    root = root.resolve()
    path = root / "ceo_core" / "productive_fallback_orchestrator_v1.py"
    text = path.read_text(encoding="utf-8")

    old_import = "from .blocked_safe_state_v1 import is_blocked_safe\n"
    new_import = "from .blocked_safe_state_v1 import is_blocked_safe, mark_blocked_safe\n"
    if text.count(old_import) != 1:
        raise RuntimeError(f"W7 import anchor count={text.count(old_import)}")
    text = text.replace(old_import, new_import, 1)

    old_apply = """    def apply(self,state:ProjectState)->FallbackReport:
        localized=rebuilt=deferred=human=0
        candidates=[t for t in state.leaf_tasks if is_productive(t,state) and t.status in {TaskStatus.FAILED,TaskStatus.BLOCKED,TaskStatus.RETRY,TaskStatus.NEEDS_REVIEW} and not t.metadata.get('explicit_human_gate') and not is_blocked_safe(t) and not t.metadata.get('waiting_provider_v1')]
        # First, remove the deterministic goal-lock task from the external-provider
"""
    new_apply = """    def apply(self,state:ProjectState)->FallbackReport:
        localized=rebuilt=deferred=human=0
        max_replans=max(1,int(state.metadata.get('max_productive_replan_generations',3) or 3))
        candidates=[t for t in state.leaf_tasks if is_productive(t,state) and t.status in {TaskStatus.FAILED,TaskStatus.BLOCKED,TaskStatus.RETRY,TaskStatus.NEEDS_REVIEW} and not t.metadata.get('explicit_human_gate') and not is_blocked_safe(t) and not t.metadata.get('waiting_provider_v1')]

        # W7 invariant: rebuilding a failed productive unit must itself be bounded
        # across replacement task ids. Otherwise each fresh replacement resets
        # attempts and the watchdog can create A -> A' -> A'' -> ... forever.
        eligible=[]
        for t in candidates:
            generation=int(t.metadata.get('stall_replan_generation',0) or 0)
            if generation >= max_replans:
                mark_blocked_safe(
                    t,
                    'productive_replan_lineage_exhausted',
                    source='productive_fallback_orchestrator_v1',
                )
                t.metadata['productive_replan_lineage_exhausted']=True
                t.metadata['productive_replan_generation']=generation
                t.metadata['max_productive_replan_generations']=max_replans
                t.metadata['recovery_strategy']='bounded_replan_exhausted'
                continue
            eligible.append(t)
        candidates=eligible

        # First, remove the deterministic goal-lock task from the external-provider
"""
    if text.count(old_apply) != 1:
        raise RuntimeError(f"W7 apply anchor count={text.count(old_apply)}")
    text = text.replace(old_apply, new_apply, 1)
    path.write_text(text, encoding="utf-8")

    contract_path = root / "CEO_UPDATE_PACKAGE.json"
    updated = False
    if contract_path.is_file():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        hashes = dict(contract.get("file_hashes") or {})
        rel = "ceo_core/productive_fallback_orchestrator_v1.py"
        if rel in hashes:
            hashes[rel] = sha256_file(path)
            contract["file_hashes"] = hashes
            contract_path.write_text(
                json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            updated = True

    return {
        "ok": True,
        "patched": "ceo_core/productive_fallback_orchestrator_v1.py",
        "sha256": sha256_file(path),
        "contract_hash_updated": updated,
        "max_productive_replan_generations_default": 3,
    }


def main() -> int:
    root = str(os.environ.get("CEO_W7_ROOT") or "").strip()
    if not root:
        raise RuntimeError("CEO_W7_ROOT is required")
    row = apply(pathlib.Path(root))
    print("W7_RECOVERY_LINEAGE_CAP_APPLIED")
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
