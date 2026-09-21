from __future__ import annotations

from typing import Any


LOCAL_GATES = (
    "compileall", "package_contract", "security_audit", "fault_lab", "diagnostics",
    "update_state_machine", "transaction_journal", "mobile_dev_queue", "self_dev_handoff",
)


def qualify_release_v5(gates: dict[str, bool], *, windows_physical_verified: bool = False) -> dict[str, Any]:
    local = {name: bool(gates.get(name, False)) for name in LOCAL_GATES}
    local_ready = all(local.values())
    physical = bool(windows_physical_verified)
    return {
        "schema_version": 5,
        "local_gates": local,
        "local_candidate_ready": local_ready,
        "windows_physical_verified": physical,
        "production_ready": bool(local_ready and physical),
        "publication_allowed": False,
        "installation_allowed": False,
        "automatic_publication": False,
        "automatic_installation": False,
        "next_physical_action": "none_during_mobile_reliability_sprint" if not physical else "human_release_decision",
    }
