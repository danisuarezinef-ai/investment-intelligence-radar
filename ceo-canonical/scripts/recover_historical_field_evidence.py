from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import zlib
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.project_catalog import ProjectCatalog
from ceo_core.runtime import user_data_root
from ceo_core.self_hosting_field import (
    FIELD_MISSIONS,
    FieldMissionGate,
    UnifiedFieldEvidenceLedger,
)

PROJECT_ID = "windows-self-hosting-field"
LEDGER_KEY = UnifiedFieldEvidenceLedger.KEY
RESULT = "CEO_HISTORICAL_EVIDENCE_RECOVERY_RESULT.json"
MAX_JSON_BYTES = 25 * 1024 * 1024
MAX_DB_BYTES = 512 * 1024 * 1024
MAX_FILES = 50000


def _desktop() -> Path:
    return Path.home() / "Desktop"


def _spec_map():
    return {spec.mission: spec for spec in FIELD_MISSIONS}


def _row_looks_like_field_evidence(value: Any) -> bool:
    return isinstance(value, dict) and {
        "run_id", "mission", "source", "platform", "started_at", "items", "signature"
    }.issubset(value.keys())


def _walk_json_for_rows(value: Any) -> Iterable[dict[str, Any]]:
    if _row_looks_like_field_evidence(value):
        yield value
    if isinstance(value, dict):
        ledger = value.get(LEDGER_KEY)
        if isinstance(ledger, dict):
            for row in ledger.values():
                if _row_looks_like_field_evidence(row):
                    yield row
        for child in value.values():
            yield from _walk_json_for_rows(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json_for_rows(child)


def _read_json_rows(path: Path) -> list[dict[str, Any]]:
    try:
        if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
            return []
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    seen: set[str] = set()
    rows = []
    for row in _walk_json_for_rows(data):
        rid = str(row.get("run_id") or "")
        if rid and rid not in seen:
            rows.append(dict(row)); seen.add(rid)
    return rows


def _safe_sqlite_connect(path: Path):
    # Read-only URI prevents the recovery tool from mutating historical stores.
    uri = path.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row)


def _rows_from_payload_text(payload: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(payload)
    except Exception:
        return []
    return list(_walk_json_for_rows(data))


def _read_sqlite_rows(path: Path) -> list[dict[str, Any]]:
    try:
        if not path.is_file() or path.stat().st_size > MAX_DB_BYTES:
            return []
        conn = _safe_sqlite_connect(path)
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        if _table_exists(conn, "project"):
            for (payload,) in conn.execute("SELECT payload FROM project"):
                for row in _rows_from_payload_text(payload):
                    rid = str(row.get("run_id") or "")
                    if rid and rid not in seen:
                        rows.append(dict(row)); seen.add(rid)
        if _table_exists(conn, "snapshots"):
            for (payload,) in conn.execute("SELECT project_payload FROM snapshots ORDER BY seq DESC LIMIT 500"):
                for row in _rows_from_payload_text(payload):
                    rid = str(row.get("run_id") or "")
                    if rid and rid not in seen:
                        rows.append(dict(row)); seen.add(rid)
        if _table_exists(conn, "full_snapshots"):
            for (blob,) in conn.execute("SELECT payload FROM full_snapshots ORDER BY seq DESC LIMIT 250"):
                try:
                    data = json.loads(zlib.decompress(blob).decode("utf-8"))
                except Exception:
                    continue
                for row in _walk_json_for_rows(data):
                    rid = str(row.get("run_id") or "")
                    if rid and rid not in seen:
                        rows.append(dict(row)); seen.add(rid)
    except Exception:
        return rows
    finally:
        conn.close()
    return rows


def _likely_roots() -> list[Path]:
    home = Path.home()
    roots: list[Path] = [user_data_root(), home / "Desktop", home / "Downloads", home / "Documents"]
    local = os.getenv("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "CEO de IAs")
    # Older restricted/fallback runs may have used a temp root.
    roots.append(Path(tempfile.gettempdir()))
    out = []
    seen = set()
    for root in roots:
        try:
            key = str(root.resolve()).lower()
        except Exception:
            key = str(root).lower()
        if key not in seen and root.exists():
            out.append(root); seen.add(key)
    return out


def _interesting_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in {".db", ".sqlite", ".sqlite3"}:
        return True
    if suffix == ".json":
        tokens = ("ceo", "field", "alpha", "self_host", "recovery", "snapshot", "result", "windows")
        return any(t in name for t in tokens)
    return False


def discover_candidate_files(roots: Iterable[Path], *, limit: int = MAX_FILES) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    visited = 0
    skip_dirs = {"node_modules", ".git", "cache", "caches", "packages", "pip", "npm-cache"}
    for root in roots:
        for current, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() not in skip_dirs]
            for filename in files:
                visited += 1
                if visited > limit:
                    return found
                p = Path(current) / filename
                if not _interesting_file(p):
                    continue
                try:
                    key = str(p.resolve()).lower()
                except Exception:
                    key = str(p).lower()
                if key not in seen:
                    found.append(p); seen.add(key)
    return found


def collect_verified_rows(paths: Iterable[Path], ledger: UnifiedFieldEvidenceLedger) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    specs = _spec_map()
    verified: dict[str, dict[str, Any]] = {}
    source_summary: list[dict[str, Any]] = []
    for path in paths:
        suffix = path.suffix.lower()
        raw_rows = _read_sqlite_rows(path) if suffix in {".db", ".sqlite", ".sqlite3"} else _read_json_rows(path)
        good = []
        for row in raw_rows:
            mission = str(row.get("mission") or "")
            spec = specs.get(mission)
            if spec is None:
                continue
            verdict = ledger.verify(row, require_windows=spec.require_windows)
            if verdict.get("verified") is not True:
                continue
            rid = str(row.get("run_id") or "")
            if rid:
                verified[rid] = dict(row)
                good.append(mission)
        if good:
            source_summary.append({
                "path": str(path),
                "verified_rows": len(set(good)),
                "missions": sorted(set(good)),
            })
    return verified, source_summary


def _compact_statuses(state) -> dict[str, Any]:
    gate = FieldMissionGate()
    return {name: {"status": row.get("status"), "verified": bool(row.get("verified")), "claims_present": row.get("claims_present", [])}
            for name, row in gate.all(state).items()}


def main() -> int:
    if os.name != "nt":
        print(json.dumps({"status": "NOT_RUN", "reason": "windows_required"}, indent=2))
        return 2

    root = user_data_root()
    catalog = ProjectCatalog(root / "projects")
    store = catalog.store(PROJECT_ID)
    state = store.load()
    out_path = _desktop() / RESULT
    if state is None:
        payload = {"status": "BLOCKED", "reason": "canonical_project_missing", "store": str(store.path), "production_verified": False}
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2)); return 3

    ledger = UnifiedFieldEvidenceLedger()
    before = _compact_statuses(state)
    canonical = store.path.resolve()
    candidates = discover_candidate_files(_likely_roots())
    candidates = [p for p in candidates if p.resolve() != canonical]
    verified_rows, source_summary = collect_verified_rows(candidates, ledger)

    current = state.metadata.setdefault(LEDGER_KEY, {})
    added = []
    for run_id, row in verified_rows.items():
        if run_id not in current:
            current[run_id] = row
            added.append({"run_id": run_id, "mission": row.get("mission")})

    after = _compact_statuses(state)
    alpha_ok = bool(after.get("alpha_certification", {}).get("verified"))
    # Genuine signed rows are safe to retain even if Alpha is not yet complete: they reduce
    # the minimal rerun set and cannot satisfy a gate unless current prerequisites/claims pass.
    if added:
        store.save(state)
        catalog.register(state, make_active=True)

    earliest_missing = None
    for spec in FIELD_MISSIONS:
        if not after[spec.mission]["verified"]:
            earliest_missing = spec.mission
            break

    payload = {
        "status": "PASS" if alpha_ok else "PARTIAL" if added else "BLOCKED",
        "action": "restored_verified_rows_from_historical_stores" if added else "no_verified_historical_rows_found",
        "project_id": PROJECT_ID,
        "canonical_store": str(store.path),
        "roots_scanned": [str(x) for x in _likely_roots()],
        "candidate_files_scanned": len(candidates),
        "sources_with_verified_rows": source_summary,
        "verified_rows_found": len(verified_rows),
        "rows_added": len(added),
        "missions_added": sorted({str(x.get("mission")) for x in added}),
        "alpha_verified": alpha_ok,
        "earliest_missing_mission": earliest_missing,
        "before": before,
        "after": after,
        "next": "run_first_work_session" if alpha_ok else f"rerun_only_{earliest_missing}" if earliest_missing else "inspect",
        "production_verified": False,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if alpha_ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
