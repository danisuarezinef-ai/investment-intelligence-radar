from __future__ import annotations

from typing import Any
from .physical_evidence_schema_v1 import PHYSICAL_GATES

LOCAL_PRECONDITIONS = (
    "dev130_continuity", "physical_evidence_schema", "campaign_checkpoint", "one_shot_preflight_bundle",
    "android_first_build_ready", "fault_matrix", "recovery_proof", "capability_drift_guard", "model_checker_v4",
)


def build_one_shot_windows_campaign_v5(local_preconditions: dict[str, bool], *, candidate_sha256: str) -> dict[str, Any]:
    local = {k: bool(local_preconditions.get(k, False)) for k in LOCAL_PRECONDITIONS}
    return {
        "schema_version": 5,
        "mode": "plan_only",
        "candidate_sha256": candidate_sha256,
        "local_preconditions": local,
        "ready_for_human_start_review": all(local.values()),
        "physical_gates": [{"id": g, "status": "NOT_VERIFIED", "evidence_schema": 1, "evidence_source_required": "physical_windows"} for g in PHYSICAL_GATES],
        "single_physical_session": True,
        "resumable_with_checkpoint": True,
        "checkpoint_must_preserve_order": True,
        "requires_explicit_human_start": True,
        "stop_on_first_unsafe_failure": True,
        "no_patch_chain": True,
        "setup_repetition_allowed": False,
        "automatic_installation": False,
        "automatic_publication": False,
        "automatic_promotion": False,
    }
