from __future__ import annotations

from typing import Any


SHARED_CORE_CAPABILITIES = (
    "goal_contracts", "task_graph_read", "status_summary", "attention_summary",
    "safe_mobile_compute", "development_receipt", "evidence_digest", "pause_resume_request",
)
ANDROID_FORBIDDEN = (
    "arbitrary_shell", "credential_export", "publication", "installation", "payment",
    "subscription_purchase", "destructive_file_delete", "real_trading",
)


def android_contract_v1() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "shared_core_capabilities": list(SHARED_CORE_CAPABILITIES),
        "forbidden_capabilities": list(ANDROID_FORBIDDEN),
        "windows_ui_independent": True,
        "android_ui_independent": True,
        "packaging_independent": True,
        "manual_post_install_configuration_required": False,
        "first_public_install_goal": "single_validated_package",
        "in_app_update_goal": True,
    }


def validate_android_request(capability: str) -> dict[str, Any]:
    cap=str(capability)
    if cap in ANDROID_FORBIDDEN: return {"allowed":False,"reason":"forbidden_capability"}
    if cap not in SHARED_CORE_CAPABILITIES: return {"allowed":False,"reason":"not_in_frozen_contract"}
    return {"allowed":True,"reason":"shared_safe_capability"}
