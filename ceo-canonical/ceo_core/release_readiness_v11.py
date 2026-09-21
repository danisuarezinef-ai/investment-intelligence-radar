from __future__ import annotations

from typing import Any

GATES = (
    "dev130_ready", "physical_evidence_schema", "campaign_checkpoint", "one_shot_preflight_bundle",
    "android_first_build_ready", "fault_matrix", "recovery_proof", "capability_drift_guard", "model_checker_v4",
    "campaign_plan_v5", "soak_guard_v6",
)


def qualify_release_v11(gates: dict[str, bool], *, windows_physical_verified: bool = False,
                         android_runtime_accepted: bool = False, human_release_authorized: bool = False) -> dict[str, Any]:
    local = {k: bool(gates.get(k, False)) for k in GATES}
    ready = all(local.values())
    physical = bool(windows_physical_verified)
    android_runtime = bool(android_runtime_accepted)
    authorized = bool(human_release_authorized)
    return {
        "schema_version": 11,
        "local_gates": local,
        "local_candidate_ready": ready,
        "physical_campaign_package_ready": ready,
        "android_first_debug_apk_build_ready": ready,
        "windows_physical_verified": physical,
        "android_runtime_accepted": android_runtime,
        "human_release_authorized": authorized,
        "production_ready": bool(ready and physical and android_runtime and authorized),
        "publication_allowed": False,
        "installation_allowed": False,
        "physical_campaign_authorized": False,
        "windows_update_freeze_respected": True,
        "next_action": "build_android_debug_apk_or_human_windows_campaign_review" if ready else "continue_local_hardening",
    }
