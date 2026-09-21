from __future__ import annotations

from typing import Any

GATES = (
    "dev141_ready", "android_artifact_identity", "android_build_inputs", "android_runtime_dossier_contract",
    "windows_campaign_bundle", "campaign_resume_guard", "authority_boundary", "model_checker_v5",
    "campaign_plan_v6", "soak_guard_v7",
)


def qualify_release_v12(gates: dict[str, bool], *, windows_physical_verified: bool = False,
                         android_debug_apk_built: bool = False, android_debug_apk_reproducible: bool = False,
                         android_runtime_accepted: bool = False, human_release_authorized: bool = False) -> dict[str, Any]:
    local = {key: bool(gates.get(key, False)) for key in GATES}
    ready = all(local.values())
    physical = bool(windows_physical_verified)
    built = bool(android_debug_apk_built)
    reproducible = bool(android_debug_apk_reproducible)
    runtime = bool(android_runtime_accepted)
    authorized = bool(human_release_authorized)
    return {
        "schema_version": 12,
        "local_gates": local,
        "local_candidate_ready": ready,
        "windows_campaign_bundle_ready": ready,
        "android_first_debug_apk_build_kit_ready": ready,
        "android_debug_apk_built": built,
        "android_debug_apk_reproducible": reproducible,
        "windows_physical_verified": physical,
        "android_runtime_accepted": runtime,
        "human_release_authorized": authorized,
        "production_ready": bool(ready and physical and built and reproducible and runtime and authorized),
        "publication_allowed": False,
        "installation_allowed": False,
        "physical_campaign_authorized": False,
        "windows_update_freeze_respected": True,
        "next_action": "build_first_android_debug_apk_or_human_windows_campaign_review" if ready else "continue_local_hardening",
    }
