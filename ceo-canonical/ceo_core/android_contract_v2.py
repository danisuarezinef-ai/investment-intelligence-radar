from __future__ import annotations

from typing import Any

from .android_contract_v1 import android_contract_v1, validate_android_request


def android_contract_v2() -> dict[str, Any]:
    base = android_contract_v1()
    return {
        "schema_version": 2,
        "shared_core": base.get("shared_core"),
        "independent_ui": True,
        "independent_packaging": True,
        "single_public_install_package": True,
        "manual_post_install_configuration_required": False,
        "in_app_updates_after_first_install": True,
        "update_requires_explicit_human_install_confirmation": True,
        "background_safe_compute_supported": True,
        "battery_thermal_admission_required": True,
        "forbidden_capabilities": sorted(set(base.get("forbidden_capabilities") or []) | {
            "arbitrary_shell", "credential_export", "publication", "installation_without_confirmation",
            "payment", "subscription_purchase", "destructive_delete", "real_trading",
        }),
        "windows_interface_reused": False,
        "windows_packaging_reused": False,
    }


def validate_android_request_v2(kind: str, *, explicit_install_confirmation: bool = False) -> dict[str, Any]:
    if kind == "in_app_update_install":
        return {
            "allowed": bool(explicit_install_confirmation),
            "reason": "explicit_human_install_confirmation" if explicit_install_confirmation else "human_confirmation_required",
            "side_effects_allowed": bool(explicit_install_confirmation),
        }
    legacy = validate_android_request(kind)
    return {**legacy, "schema_version": 2}
