from __future__ import annotations

from typing import Any


def qualify_convergence_evidence(
    *, receipt_ok: bool, strong_attestation: bool, tree_conflicts: int, protected_paths: int,
    tests_passed: int, tests_failed: int, benchmark_complete: bool, regression_scope_complete: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    review: list[str] = []
    if not receipt_ok: blockers.append("receipt_invalid")
    if tests_passed <= 0 or tests_failed > 0: blockers.append("tests_not_clean")
    if tree_conflicts: blockers.append("tree_conflicts")
    if protected_paths: blockers.append("protected_paths")
    if not regression_scope_complete: blockers.append("regression_scope_incomplete")
    if not strong_attestation: review.append("strong_attestation_missing")
    if not benchmark_complete: review.append("benchmark_evidence_incomplete")
    if blockers:
        state = "BLOCKED"
    elif review:
        state = "REVIEW"
    else:
        state = "ELIGIBLE_FOR_SANDBOX_COMPARISON"
    return {
        "schema_version": 1,
        "state": state,
        "blockers": blockers,
        "review_items": review,
        "eligible_for_sandbox_comparison": state == "ELIGIBLE_FOR_SANDBOX_COMPARISON",
        "eligible_for_automatic_merge": False,
        "automatic_promotion": False,
        "automatic_publication": False,
        "automatic_installation": False,
    }
