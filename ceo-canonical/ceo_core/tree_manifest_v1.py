from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_rel(root: Path, path: Path) -> str:
    rel = path.relative_to(root).as_posix()
    if rel.startswith("../") or rel == ".." or rel.startswith("/"):
        raise ValueError("unsafe manifest path")
    return rel


def build_tree_manifest(
    root: str | Path, *, include_prefixes: Iterable[str] = ("ceo_core", "ceo_app", "scripts", "assets"),
    max_files: int = 20_000, max_file_bytes: int = 16 * 1024 * 1024,
) -> dict[str, Any]:
    base = Path(root).resolve()
    rows: list[dict[str, Any]] = []
    prefixes = tuple(str(x).strip("/\\") for x in include_prefixes)
    for prefix in prefixes:
        target = base / prefix
        if not target.exists():
            continue
        for path in sorted(target.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"symlink rejected: {_safe_rel(base, path)}")
            if not path.is_file():
                continue
            if len(rows) >= max_files:
                raise ValueError("tree manifest file limit exceeded")
            size = path.stat().st_size
            if size > max_file_bytes:
                raise ValueError(f"manifest file too large: {_safe_rel(base, path)}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append({"path": _safe_rel(base, path), "size": size, "sha256": digest})
    manifest_digest = hashlib.sha256(_canon(rows)).hexdigest()
    return {"schema_version": 1, "root_digest": manifest_digest, "files": rows, "file_count": len(rows)}


def compare_tree_manifests(base: dict[str, Any], left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    def index(m: dict[str, Any]) -> dict[str, str]:
        return {str(x["path"]): str(x["sha256"]) for x in (m.get("files") or []) if isinstance(x, dict) and x.get("path") and x.get("sha256")}
    b, l, r = index(base), index(left), index(right)
    paths = sorted(set(b) | set(l) | set(r))
    rows: list[dict[str, str]] = []
    conflicts: list[str] = []
    for p in paths:
        bv, lv, rv = b.get(p), l.get(p), r.get(p)
        lc, rc = lv != bv, rv != bv
        if lc and rc and lv != rv:
            relation = "divergent_overlap"; conflicts.append(p)
        elif lc and rc:
            relation = "same_result_overlap"
        elif lc:
            relation = "left_only"
        elif rc:
            relation = "right_only"
        else:
            relation = "unchanged"
        rows.append({"path": p, "relation": relation, "base": bv or "", "left": lv or "", "right": rv or ""})
    return {
        "schema_version": 1,
        "rows": rows,
        "conflicts": conflicts,
        "same_result_overlap": [x["path"] for x in rows if x["relation"] == "same_result_overlap"],
        "left_only": [x["path"] for x in rows if x["relation"] == "left_only"],
        "right_only": [x["path"] for x in rows if x["relation"] == "right_only"],
        "automatic_merge": False,
    }
