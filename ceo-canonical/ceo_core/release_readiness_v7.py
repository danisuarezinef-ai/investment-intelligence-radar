from __future__ import annotations

from typing import Any


GATES=(
    "dev90_ready","self_dev_reconciler","failure_lab_v3","recovery_planner_v2","mobile_queue_v2",
    "android_contract_v1","evidence_bridge_v1","executive_snapshot_v2","compatibility_matrix_v1","soak_guard_v2",
)


def qualify_release_v7(gates: dict[str,bool], *, windows_physical_verified: bool=False, human_release_authorized: bool=False) -> dict[str,Any]:
    local={k:bool(gates.get(k,False)) for k in GATES}; ready=all(local.values())
    physical=bool(windows_physical_verified)
    return {
        "schema_version":7,"local_gates":local,"local_candidate_ready":ready,"windows_physical_verified":physical,
        "production_ready":bool(ready and physical and human_release_authorized),
        "publication_allowed":False,"installation_allowed":False,"physical_campaign_authorized":False,
        "human_release_authorized":bool(human_release_authorized),
        "windows_update_freeze_respected":True,
        "next_action":"continue_mobile_development" if not physical else "human_release_review",
    }
