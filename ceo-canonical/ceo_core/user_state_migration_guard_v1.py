from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    if not root.exists():
        return h.hexdigest()
    for p in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda x: x.as_posix()):
        rel = p.relative_to(root).as_posix().encode("utf-8")
        h.update(len(rel).to_bytes(4, "big")); h.update(rel)
        data = p.read_bytes(); h.update(len(data).to_bytes(8, "big")); h.update(data)
    return h.hexdigest()


def capture_user_state_v1(root: str | Path) -> dict[str, Any]:
    p = Path(root)
    return {"root": str(p), "tree_sha256": _tree_digest(p), "read_only": True}


def verify_user_state_unchanged_v1(before: dict[str, Any], after_root: str | Path) -> dict[str, Any]:
    after = capture_user_state_v1(after_root)
    same = str(before.get("tree_sha256") or "") == after["tree_sha256"]
    return {"ok": same, "before_sha256": before.get("tree_sha256"), "after_sha256": after["tree_sha256"],
            "automatic_migration_allowed": False, "user_state_preserved": same}
