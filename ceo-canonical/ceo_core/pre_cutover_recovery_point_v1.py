from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

POINTER_FILES = ("current.json", "previous.json", "operation.json", "progress.json", "restart-progress.json")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PreCutoverRecoveryPointV1:
    """Copies only updater control-plane state; project/user data are never rewritten."""

    def __init__(self, updates_root: str | Path):
        self.root = Path(updates_root)

    def create(self, *, campaign_id: str) -> dict[str, Any]:
        target = self.root / "recovery-points" / str(campaign_id)
        target.mkdir(parents=True, exist_ok=True)
        files: dict[str, Any] = {}
        for name in POINTER_FILES:
            src = self.root / name
            if src.is_file():
                dst = target / name
                shutil.copy2(src, dst)
                files[name] = {"sha256": _sha(dst), "size_bytes": dst.stat().st_size}
        manifest = {
            "schema_version": 1,
            "campaign_id": str(campaign_id),
            "created_at_epoch": time.time(),
            "files": files,
            "project_data_touched": False,
        }
        manifest_path = target / "manifest.json"
        tmp = manifest_path.with_name(manifest_path.name + f".tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        try:
            tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(tmp, manifest_path)
        finally:
            tmp.unlink(missing_ok=True)
        return {**manifest, "path": str(target), "restorable": "current.json" in files}

    def verify(self, campaign_id: str) -> dict[str, Any]:
        target = self.root / "recovery-points" / str(campaign_id)
        try:
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "problems": [f"manifest_unreadable:{type(exc).__name__}"]}
        problems = []
        for name, meta in (manifest.get("files") or {}).items():
            path = target / name
            if not path.is_file():
                problems.append(f"missing:{name}")
            elif _sha(path) != str(meta.get("sha256") or ""):
                problems.append(f"hash:{name}")
        return {"ok": not problems, "problems": problems, "manifest": manifest}
