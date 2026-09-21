from __future__ import annotations

from typing import Any
from .physical_evidence_schema_v1 import PHYSICAL_GATES

LOCAL_PRECONDITIONS = (
    "dev141_continuity", "android_artifact_identity", "android_build_inputs", "android_runtime_dossier_contract",
    "windows_campaign_bundle", "campaign_resume_guard", "authority_boundary", "model_checker_v5",
)


def build_one_shot_windows_campaign_v6(local_preconditions: dict[str, bool], *, candidate_sha256: str,
                                        campaign_bundle_sha256: str) -> dict[str, Any]:
    local = {key: bool(local_preconditions.get(key, False)) for key in LOCAL_PRECONDITIONS}
    return {
        "schema_version": 6,
        "mode": "plan_only",
        "candidate_sha256": candidate_sha256,
        "campaign_bundle_sha256": campaign_bundle_sha256,
        "local_preconditions": local,
        "ready_for_human_start_review": all(local.values()),
        "physical_gates": [
            {"ordinal": i + 1, "id": gate, "status": "NOT_VERIFIED", "evidence_source_required": "physical_windows"}
            for i, gate in enumerate(PHYSICAL_GATES)
        ],
        "single_physical_session": True,
        "resumable_with_exact_candidate_only": True,
        "resume_cannot_skip_gates": True,
        "requires_explicit_human_start": True,
        "requires_explicit_human_resume": True,
        "stop_on_first_unsafe_failure": True,
        "no_patch_chain": True,
        "setup_repetition_allowed": False,
        "automatic_installation": False,
        "automatic_publication": False,
        "automatic_promotion": False,
        "automatic_spending": False,
    }
