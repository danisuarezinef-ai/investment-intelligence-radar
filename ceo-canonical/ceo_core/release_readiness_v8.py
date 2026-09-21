from __future__ import annotations

from typing import Any

GATES = (
    "dev100_ready", "receipt_v2", "convergence_plan", "benchmark_arbitrator", "model_checker",
    "mobile_sync_v3", "mobile_offload_planner", "android_contract_v2", "convergence_gate", "soak_guard_v3",
)


def qualify_release_v8(gates: dict[str, bool], *, windows_physical_verified: bool = False, human_release_authorized: bool = False) -> dict[str, Any]:
    local = {k: bool(gates.get(k, False)) for k in GATES}
    ready = all(local.values())
    physical = bool(windows_physical_verified)
    return {
        "schema_version": 8,
        "local_gates": local,
        "local_candidate_ready": ready,
        "windows_physical_verified": physical,
        "production_ready": bool(ready and physical and human_release_authorized),
        "publication_allowed": False,
        "installation_allowed": False,
        "physical_campaign_authorized": False,
        "human_release_authorized": bool(human_release_authorized),
        "windows_update_freeze_respected": True,
        "next_action": "continue_mobile_development" if not physical else "human_release_review",
    }
