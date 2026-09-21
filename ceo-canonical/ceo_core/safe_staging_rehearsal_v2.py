from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any


def safe_staging_rehearsal_v2(candidate_root: str | Path, *, expected_version: str) -> dict[str, Any]:
    """Copy candidate to an isolated side-by-side tree and verify without pointers."""
    source = Path(candidate_root).resolve()
    current_before = None
    pointer = source / "current.json"
    if pointer.exists(): current_before = pointer.read_bytes()
    with tempfile.TemporaryDirectory(prefix="ceo-stage-rehearsal-") as td:
        dest = Path(td) / "versions" / expected_version
        shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        contract = json.loads((dest / "CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8"))
        problems: list[str] = []
        if str(contract.get("app_version") or "") != expected_version: problems.append("version")
        verified = 0
        for rel in contract.get("required_paths") or []:
            p = dest / rel
            if not p.is_file(): problems.append("missing:" + rel); continue
            if rel == "CEO_UPDATE_PACKAGE.json": continue
            got = hashlib.sha256(p.read_bytes()).hexdigest()
            if got != str((contract.get("file_hashes") or {}).get(rel) or ""): problems.append("hash:" + rel)
            else: verified += 1
        pointer_unchanged = True if current_before is None else pointer.read_bytes() == current_before
        return {
            "ok": not problems and pointer_unchanged,
            "version": expected_version,
            "verified_hashes": verified,
            "problems": problems[:30],
            "active_pointer_changed": not pointer_unchanged,
            "activation_attempted": False,
            "isolated": True,
        }
