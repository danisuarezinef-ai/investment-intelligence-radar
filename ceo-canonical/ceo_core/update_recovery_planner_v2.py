from __future__ import annotations

from typing import Any


def plan_update_recovery(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return the safest next recovery action without performing it."""
    phase = str(snapshot.get("phase") or snapshot.get("state") or "unknown").lower()
    journal_ok = bool(snapshot.get("journal_ok", True))
    receipt_ok = bool(snapshot.get("receipt_ok", True))
    current_healthy = bool(snapshot.get("current_healthy", True))
    pending = bool(snapshot.get("pending_health", False))

    if not journal_ok:
        action, severity = "restore_journal_checkpoint", "high"
    elif not receipt_ok:
        action, severity = "reconcile_receipt_from_signed_evidence", "high"
    elif pending and not current_healthy:
        action, severity = "rollback_to_last_known_good", "high"
    elif pending:
        action, severity = "finish_health_decision_only", "medium"
    elif phase in {"preflight_failed", "blocked", "quarantined"}:
        action, severity = "keep_current_and_diagnose_candidate", "low"
    elif phase in {"rolled_back", "rollback"}:
        action, severity = "keep_current_and_wait_for_newer_candidate", "low"
    elif phase in {"healthy", "idle", "current"}:
        action, severity = "none", "none"
    else:
        action, severity = "collect_diagnostics_without_cutover", "medium"
    return {
        "schema_version": 2,
        "phase": phase,
        "recommended_action": action,
        "severity": severity,
        "safe_to_execute_autonomously": action in {"none", "keep_current_and_diagnose_candidate", "keep_current_and_wait_for_newer_candidate", "collect_diagnostics_without_cutover"},
        "allows_cutover": False,
        "allows_publication": False,
        "allows_installation": False,
        "requires_human_for_irreversible_effects": True,
    }
