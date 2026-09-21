from __future__ import annotations

from typing import Any


GATES = (
    "dev85_ready", "failure_lab_v2", "physical_campaign_plan", "self_dev_inbox",
    "mobile_sync_v2", "operator_update_summary",
)


def qualify_release_v6(gates: dict[str, bool], *, windows_physical_verified: bool = False) -> dict[str, Any]:
    local = {k: bool(gates.get(k, False)) for k in GATES}
    local_ready = all(local.values())
    return {
        "schema_version": 6,
        "local_gates": local,
        "local_candidate_ready": local_ready,
        "windows_physical_verified": bool(windows_physical_verified),
        "production_ready": bool(local_ready and windows_physical_verified),
        "publication_allowed": False,
        "installation_allowed": False,
        "physical_campaign_authorized": False,
        "next_action": "continue_mobile_development" if not windows_physical_verified else "human_release_review",
    }
