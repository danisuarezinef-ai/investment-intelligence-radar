from __future__ import annotations

from typing import Any


def qualify_convergence_gate_v2(
    *, receipt_ok: bool, tree_conflicts: int, protected_paths: int, regression_complete: bool,
    android_source_harness_ready: bool, parity_ok: bool, provenance_ok: bool, ledger_ok: bool,
    model_check_ok: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    checks = {
        "receipt_ok": bool(receipt_ok),
        "tree_clean": int(tree_conflicts) == 0,
        "protected_paths_clear": int(protected_paths) == 0,
        "regression_complete": bool(regression_complete),
        "android_source_harness_ready": bool(android_source_harness_ready),
        "parity_ok": bool(parity_ok),
        "provenance_ok": bool(provenance_ok),
        "ledger_ok": bool(ledger_ok),
        "model_check_ok": bool(model_check_ok),
    }
    blockers.extend(k for k, v in checks.items() if not v)
    state = "ELIGIBLE_FOR_ONE_SHOT_PREP" if not blockers else "BLOCKED"
    return {
        "schema_version": 2,
        "state": state,
        "checks": checks,
        "blockers": blockers,
        "eligible_for_one_shot_preparation": not blockers,
        "automatic_merge": False,
        "automatic_promotion": False,
        "automatic_publication": False,
        "automatic_installation": False,
    }
