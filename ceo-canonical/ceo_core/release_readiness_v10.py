from __future__ import annotations

from typing import Any

GATES = (
    "dev120_ready", "shared_core_contract", "android_evidence_import", "cross_platform_provenance",
    "cross_platform_parity", "transaction_ledger", "model_checker_v3", "convergence_gate_v2",
    "campaign_plan_v4", "soak_guard_v5",
)


def qualify_release_v10(
    gates: dict[str, bool], *, windows_physical_verified: bool = False,
    human_release_authorized: bool = False, android_runtime_accepted: bool = False,
) -> dict[str, Any]:
    local = {k: bool(gates.get(k, False)) for k in GATES}
    ready = all(local.values())
    physical = bool(windows_physical_verified)
    authorized = bool(human_release_authorized)
    android_runtime = bool(android_runtime_accepted)
    return {
        "schema_version": 10,
        "local_gates": local,
        "local_candidate_ready": ready,
        "cross_platform_preflight_ready": ready,
        "windows_physical_verified": physical,
        "android_runtime_accepted": android_runtime,
        "human_release_authorized": authorized,
        "windows_production_ready": bool(ready and physical and authorized),
        "android_production_ready": bool(ready and android_runtime and authorized),
        "production_ready": bool(ready and physical and android_runtime and authorized),
        "publication_allowed": False,
        "installation_allowed": False,
        "physical_campaign_authorized": False,
        "windows_update_freeze_respected": True,
        "next_action": "continue_local_preflight" if not physical else "human_release_review",
    }
