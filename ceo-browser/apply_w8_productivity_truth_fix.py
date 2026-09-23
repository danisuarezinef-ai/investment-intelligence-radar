from __future__ import annotations

import hashlib
import json
import os
import pathlib


def sha256_file(path: pathlib.Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def apply(root:pathlib.Path)->dict:
    root=root.resolve()
    path=root/"ceo_core"/"progress_tracker.py"
    text=path.read_text(encoding="utf-8")

    old='''            legacy_v1 = state.metadata.get("stable_progress_v1") or {}
            legacy_display = float(legacy_v1.get("display_progress", state.progress) or 0.0)
            inflated = (not completed) and legacy_display >= 95.0 and batch_progress + 15.0 < legacy_display
            display = candidate if inflated else max(candidate, min(99.0, legacy_display))
'''
    new='''            legacy_v1_raw = state.metadata.get("stable_progress_v1")
            legacy_v1 = legacy_v1_raw if isinstance(legacy_v1_raw, dict) else {}

            # W8: state.progress is the raw graph ratio and includes control,
            # verification, heartbeat and recovery leaves. It is not a valid
            # fallback for an operator-facing productive high-water mark.
            #
            # Preserve an explicit legacy v1 display value when it actually
            # exists, but for projects with no legacy tracker baseline start
            # strictly from productive batch progress.
            has_explicit_legacy_display = "display_progress" in legacy_v1
            legacy_display = (
                float(legacy_v1.get("display_progress", 0.0) or 0.0)
                if has_explicit_legacy_display
                else candidate
            )
            inflated = (
                has_explicit_legacy_display
                and (not completed)
                and legacy_display >= 95.0
                and batch_progress + 15.0 < legacy_display
            )
            display = candidate if inflated else max(candidate, min(99.0, legacy_display))
'''
    if text.count(old)!=1:
        raise RuntimeError(f"W8 progress migration anchor count={text.count(old)}")
    path.write_text(text.replace(old,new,1),encoding="utf-8")

    contract_path=root/"CEO_UPDATE_PACKAGE.json"
    updated=False
    if contract_path.is_file():
        row=json.loads(contract_path.read_text(encoding="utf-8"))
        hashes=dict(row.get("file_hashes") or {})
        rel="ceo_core/progress_tracker.py"
        if rel in hashes:
            hashes[rel]=sha256_file(path)
            row["file_hashes"]=hashes
            contract_path.write_text(json.dumps(row,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
            updated=True
    return {"ok":True,"patched":"ceo_core/progress_tracker.py","sha256":sha256_file(path),"contract_hash_updated":updated}


def main()->int:
    root=str(os.environ.get("CEO_W8_ROOT") or "").strip()
    if not root:
        raise RuntimeError("CEO_W8_ROOT is required")
    out=apply(pathlib.Path(root))
    print("W8_PRODUCTIVITY_TRUTH_PATCH_APPLIED")
    print(json.dumps(out,ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
