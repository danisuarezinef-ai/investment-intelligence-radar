from __future__ import annotations

import os
from typing import Any

from .android_contract_v2 import validate_android_request_v2
from .mobile_offload_planner_v1 import plan_mobile_offload
from .mobile_sync_v3 import MobileSyncV3
from .update_failure_lab_v3 import UpdateFailureLabV3
from .update_model_checker_v1 import bounded_model_check


def run_soak_guard_v3(*, seeds: int = 1000, steps: int = 200, sync_rounds: int = 5000) -> dict[str, Any]:
    lab = UpdateFailureLabV3.campaign(seeds=seeds, steps=steps)
    model = bounded_model_check(max_depth=14)
    sync = MobileSyncV3(os.urandom(32))
    transcript = "0" * 64
    accepted = 0
    for seq in range(1, max(1, int(sync_rounds)) + 1):
        env = sync.issue_batch([{"kind": "status", "payload": {"seq": seq}}])
        # verifier instance deliberately has its own replay ledger.
        verifier = MobileSyncV3(sync.key)
        verdict = verifier.verify_batch(env, expected_sequence=seq, expected_previous_transcript=transcript)
        if verdict["side_effects_allowed"] is False:
            accepted += 1
        transcript = str(env["batch_transcript"])
    offload = plan_mobile_offload(
        [{"kind": "summarize", "estimated_ram_gb": 1.0}, {"kind": "publication", "estimated_ram_gb": 0.1}],
        {"ram_total_gb": 24, "ram_free_gb": 18, "battery_percent": 80, "charging": False, "thermal": "normal"},
    )
    android_block = not validate_android_request_v2("in_app_update_install", explicit_install_confirmation=False)["allowed"]
    return {
        "ok": bool(lab["ok"] and model["ok"] and accepted == max(1, int(sync_rounds)) and len(offload["admitted"]) == 1 and len(offload["deferred"]) == 1 and android_block),
        "failure_lab": lab,
        "model_checker": model,
        "sync_rounds": max(1, int(sync_rounds)),
        "sync_rounds_accepted": accepted,
        "mobile_offload_safe": len(offload["admitted"]) == 1 and len(offload["deferred"]) == 1,
        "android_install_without_confirmation_rejected": android_block,
        "automatic_publication": False,
        "automatic_installation": False,
    }
