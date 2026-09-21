from __future__ import annotations

from typing import Any

FAULTS: tuple[tuple[str, str, bool], ...] = (
    ("downgrade", "reject_candidate", False),
    ("receipt_tamper", "quarantine_candidate", False),
    ("provenance_break", "quarantine_candidate", False),
    ("parity_break", "block_cutover", False),
    ("ledger_break", "restore_or_rebuild_evidence", False),
    ("snapshot_missing", "block_activation", False),
    ("candidate_hash_mismatch", "reject_candidate", False),
    ("physical_evidence_gap", "stop_campaign", False),
    ("capability_drift", "human_review_required", False),
    ("android_runtime_overclaim", "reject_android_evidence", False),
    ("power_loss_pending_health", "rollback_to_stable", False),
    ("concurrent_stage", "reject_competing_stage", False),
)


def build_update_fault_matrix_v1() -> dict[str, Any]:
    rows = [{"fault": f, "safe_response": r, "cutover_allowed": c} for f, r, c in FAULTS]
    return {
        "schema_version": 1,
        "ok": all(not row["cutover_allowed"] for row in rows),
        "rows": rows,
        "faults": len(rows),
        "unsafe_cutover_rows": sum(1 for row in rows if row["cutover_allowed"]),
        "automatic_publication": False,
        "automatic_installation": False,
    }
