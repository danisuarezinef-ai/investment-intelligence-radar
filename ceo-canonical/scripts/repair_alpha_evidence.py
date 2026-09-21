from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.project_catalog import ProjectCatalog
from ceo_core.runtime import user_data_root
from ceo_core.self_hosting_field import (
    FIELD_MISSIONS,
    FieldEvidenceAuthority,
    FieldMissionGate,
    UnifiedFieldEvidenceLedger,
)

PROJECT_ID = "windows-self-hosting-field"
LEDGER_KEY = UnifiedFieldEvidenceLedger.KEY
RESULT = "CEO_ALPHA_RECOVERY_RESULT.json"


def _desktop() -> Path:
    return Path.home() / "Desktop"


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _mission_statuses(state):
    gate = FieldMissionGate()
    return {spec.mission: gate.status(state, spec) for spec in FIELD_MISSIONS}


def _compact(statuses: dict) -> dict:
    return {
        name: {
            "status": row.get("status"),
            "verified": bool(row.get("verified")),
            "claims_present": row.get("claims_present", []),
            "prerequisites_ok": row.get("prerequisites_ok"),
            "attestation": row.get("attestation", {}),
        }
        for name, row in statuses.items()
    }


def _row_valid(ledger: UnifiedFieldEvidenceLedger, row: dict, require_windows: bool) -> bool:
    verdict = ledger.verify(row, require_windows=require_windows)
    return bool(verdict.get("verified"))


def _merge_valid_rows(current, source) -> tuple[int, list[str]]:
    ledger = UnifiedFieldEvidenceLedger()
    by_spec = {x.mission: x for x in FIELD_MISSIONS}
    cur = current.metadata.setdefault(LEDGER_KEY, {})
    src = source.metadata.get(LEDGER_KEY, {})
    added = 0
    missions: list[str] = []
    for run_id, row in src.items():
        mission = str(row.get("mission") or "")
        spec = by_spec.get(mission)
        if spec is None:
            continue
        if run_id in cur:
            continue
        if not _row_valid(ledger, row, require_windows=spec.require_windows):
            continue
        cur[run_id] = row
        added += 1
        missions.append(mission)
    return added, sorted(set(missions))


def main() -> int:
    if os.name != "nt":
        print(json.dumps({"status": "NOT_RUN", "reason": "windows_required"}, indent=2))
        return 2

    root = user_data_root()
    catalog = ProjectCatalog(root / "projects")
    store = catalog.store(PROJECT_ID)
    state = store.load()
    key_path = FieldEvidenceAuthority().key_path
    out_path = _desktop() / RESULT

    if state is None:
        payload = {
            "status": "BLOCKED",
            "reason": "canonical_project_missing",
            "project_id": PROJECT_ID,
            "store": str(store.path),
            "production_verified": False,
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 3

    before = _mission_statuses(state)
    if before["alpha_certification"].get("verified") is True:
        payload = {
            "status": "PASS",
            "action": "no_repair_needed",
            "project_id": PROJECT_ID,
            "alpha": before["alpha_certification"],
            "key_exists": key_path.is_file(),
            "key_sha256": _sha256(key_path),
            "production_verified": False,
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        catalog.register(state, make_active=True)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0

    snapshots = store.list_full_snapshots(limit=100)
    recovered_from = None
    total_added = 0
    recovered_missions: list[str] = []

    # Only copy rows whose original signature still verifies with the current local authority key.
    for snap in snapshots:
        snap_state = store.restore_full_snapshot(snap["seq"])
        if snap_state is None:
            continue
        snap_status = _mission_statuses(snap_state)
        if snap_status["alpha_certification"].get("verified") is not True:
            continue
        added, missions = _merge_valid_rows(state, snap_state)
        total_added += added
        recovered_missions.extend(missions)
        recovered_from = snap["seq"]
        after_try = _mission_statuses(state)
        if after_try["alpha_certification"].get("verified") is True:
            break

    after = _mission_statuses(state)
    repaired = after["alpha_certification"].get("verified") is True

    if repaired:
        store.save(state)
        catalog.register(state, make_active=True)
        payload = {
            "status": "PASS",
            "action": "restored_only_cryptographically_valid_signed_rows",
            "project_id": PROJECT_ID,
            "snapshot_seq": recovered_from,
            "rows_added": total_added,
            "missions_recovered": sorted(set(recovered_missions)),
            "alpha_verified": True,
            "key_exists": key_path.is_file(),
            "key_sha256": _sha256(key_path),
            "before": _compact(before),
            "after": _compact(after),
            "production_verified": False,
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0

    ledger_rows = list(state.metadata.get(LEDGER_KEY, {}).values())
    ledger = UnifiedFieldEvidenceLedger()
    mission_diag = {}
    for spec in FIELD_MISSIONS:
        rows = [r for r in ledger_rows if r.get("mission") == spec.mission]
        verified_rows = [r for r in rows if _row_valid(ledger, r, spec.require_windows)]
        mission_diag[spec.mission] = {
            "rows": len(rows),
            "verified_signed_rows": len(verified_rows),
            "gate_status": after[spec.mission].get("status"),
        }

    missing = [name for name, row in after.items() if not row.get("verified")]
    payload = {
        "status": "BLOCKED",
        "action": "no_safe_automatic_repair_available",
        "project_id": PROJECT_ID,
        "key_exists": key_path.is_file(),
        "key_sha256": _sha256(key_path),
        "snapshots_checked": len(snapshots),
        "valid_rows_restored": total_added,
        "missing_or_unverified_missions": missing,
        "mission_diagnostics": mission_diag,
        "before": _compact(before),
        "after": _compact(after),
        "next": "Rerun only the earliest missing field mission(s); do not bypass the signed evidence gate.",
        "production_verified": False,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
