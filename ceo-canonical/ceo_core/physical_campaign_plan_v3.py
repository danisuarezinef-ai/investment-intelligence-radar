from __future__ import annotations

from typing import Any


GATES = (
    ("baseline_health", ()),
    ("persistent_signer_self_test", ("baseline_health",)),
    ("signed_candidate_stage", ("persistent_signer_self_test",)),
    ("isolated_preflight", ("signed_candidate_stage",)),
    ("pre_cutover_snapshot", ("isolated_preflight",)),
    ("activation", ("pre_cutover_snapshot",)),
    ("health_confirmation", ("activation",)),
    ("rollback_drill", ("health_confirmation",)),
    ("restart_resume", ("rollback_drill",)),
    ("worker_recovery", ("restart_resume",)),
    ("browser_recovery", ("restart_resume",)),
    ("live_provider", ("worker_recovery",)),
    ("executive_ui_crosscheck", ("live_provider",)),
    ("self_dev_handoff", ("executive_ui_crosscheck",)),
    ("mobile_sync_read_only", ("self_dev_handoff",)),
)


def build_one_shot_windows_campaign_v3() -> dict[str, Any]:
    return {
        "schema_version": 3,
        "mode": "plan_only",
        "gates": [{"id": gate, "requires": list(req), "status": "NOT_VERIFIED", "evidence_source_required": "physical_windows"} for gate, req in GATES],
        "single_physical_session": True,
        "requires_explicit_human_start": True,
        "stop_on_first_unsafe_failure": True,
        "no_patch_chain": True,
        "setup_repetition_allowed": False,
        "automatic_installation": False,
        "automatic_publication": False,
        "automatic_promotion": False,
    }


def campaign_progress(evidence: dict[str, bool]) -> dict[str, Any]:
    verified: list[str] = []
    next_gate = None
    for gate, req in GATES:
        if all(r in verified for r in req) and bool(evidence.get(gate, False)):
            verified.append(gate); continue
        if all(r in verified for r in req): next_gate = gate
        break
    return {
        "verified": verified,
        "verified_count": len(verified),
        "total": len(GATES),
        "next_gate": next_gate,
        "complete": len(verified) == len(GATES),
        "physical_windows_required": True,
        "automatic_installation": False,
    }
