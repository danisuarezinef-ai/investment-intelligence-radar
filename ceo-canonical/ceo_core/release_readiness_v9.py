from __future__ import annotations

from typing import Any


GATES = (
    "dev110_ready", "receipt_v3", "tree_manifest", "convergence_sandbox", "regression_impact",
    "evidence_matrix", "mobile_sync_v4", "android_packaging", "model_checker_v2", "campaign_plan_v3", "soak_guard_v4",
)


def qualify_release_v9(gates: dict[str, bool], *, windows_physical_verified: bool = False, human_release_authorized: bool = False) -> dict[str, Any]:
    local = {k: bool(gates.get(k, False)) for k in GATES}
    ready = all(local.values())
    physical = bool(windows_physical_verified)
    authorized = bool(human_release_authorized)
    return {
        "schema_version": 9,
        "local_gates": local,
        "local_candidate_ready": ready,
        "windows_physical_verified": physical,
        "human_release_authorized": authorized,
        "production_ready": bool(ready and physical and authorized),
        "publication_allowed": False,
        "installation_allowed": False,
        "physical_campaign_authorized": False,
        "windows_update_freeze_respected": True,
        "next_action": "continue_mobile_development" if not physical else "human_release_review",
    }
