from __future__ import annotations

import itertools
from typing import Any

from .update_recovery_planner_v2 import plan_update_recovery


def bounded_recovery_proof_v1() -> dict[str, Any]:
    phases = ("idle", "preflight_failed", "pending", "rolled_back", "unknown")
    checked = 0
    violations: list[dict[str, Any]] = []
    high_risk = {"restore_journal_checkpoint", "reconcile_receipt_from_signed_evidence", "rollback_to_last_known_good", "finish_health_decision_only"}
    for phase, journal_ok, receipt_ok, healthy, pending in itertools.product(phases, (False, True), (False, True), (False, True), (False, True)):
        snap = {"phase": phase, "journal_ok": journal_ok, "receipt_ok": receipt_ok, "current_healthy": healthy, "pending_health": pending}
        verdict = plan_update_recovery(snap)
        checked += 1
        if verdict.get("allows_cutover") or verdict.get("allows_publication") or verdict.get("allows_installation"):
            violations.append({"snapshot": snap, "reason": "planner_granted_forbidden_effect", "verdict": verdict})
        if verdict.get("recommended_action") in high_risk and verdict.get("safe_to_execute_autonomously"):
            violations.append({"snapshot": snap, "reason": "high_risk_marked_autonomous", "verdict": verdict})
    return {
        "schema_version": 1,
        "ok": not violations,
        "cases_checked": checked,
        "violations": violations[:5],
        "cutover_proved_absent": not violations,
    }
