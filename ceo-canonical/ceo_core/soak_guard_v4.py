from __future__ import annotations

import os
from typing import Any

from .android_packaging_contract_v1 import validate_android_packaging_manifest
from .mobile_sync_v4 import MobileSyncV4
from .update_failure_lab_v3 import UpdateFailureLabV3
from .update_model_checker_v2 import bounded_model_check_v2


def run_soak_guard_v4(*, seeds: int = 1200, steps: int = 200, transfer_rounds: int = 3000) -> dict[str, Any]:
    lab = UpdateFailureLabV3.campaign(seeds=seeds, steps=steps)
    model = bounded_model_check_v2(max_depth=15)
    key = os.urandom(32)
    accepted = 0
    for n in range(max(1, int(transfer_rounds))):
        sender = MobileSyncV4(key); receiver = MobileSyncV4(key)
        envs = sender.issue_transfer([
            {"kind": "status", "payload": {"n": n}},
            {"kind": "test_result", "payload": {"ok": True}},
        ], chunk_size=1)
        verdict = receiver.verify_transfer(envs)
        if verdict["side_effects_allowed"] is False and len(verdict["items"]) == 2:
            accepted += 1
    packaging = validate_android_packaging_manifest({
        "application_id": "com.ceodeias.app", "version_name": "0.1.0", "version_code": 1,
        "single_install_package": True, "in_app_updates": True,
        "manual_post_install_configuration_required": False, "shared_core_protocol": 2,
        "requested_privileged_capabilities": [],
    })
    ok = bool(lab["ok"] and model["ok"] and accepted == max(1, int(transfer_rounds)) and packaging["ok"])
    return {
        "ok": ok,
        "failure_lab": lab,
        "model_checker_v2": model,
        "transfer_rounds": max(1, int(transfer_rounds)),
        "transfers_accepted": accepted,
        "android_packaging_contract": packaging,
        "automatic_publication": False,
        "automatic_installation": False,
    }
