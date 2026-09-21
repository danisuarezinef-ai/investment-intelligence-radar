from __future__ import annotations

from typing import Any


GATES = (
    "baseline_health", "signer_self_test", "signed_stage", "isolated_preflight",
    "activation", "health_confirmation", "rollback_drill", "restart_resume",
    "worker_recovery", "browser_recovery", "live_provider", "observability_crosscheck",
)


def build_one_shot_windows_campaign() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "mode": "plan_only",
        "gates": [{"id": g, "status": "NOT_VERIFIED"} for g in GATES],
        "requires_physical_windows": True,
        "requires_explicit_human_start": True,
        "automatic_installation": False,
        "automatic_publication": False,
        "setup_repetition_allowed": False,
        "stop_on_first_unsafe_failure": True,
    }


def authorize_campaign(*, physical_windows: bool, human_confirmed: bool) -> dict[str, Any]:
    allowed = bool(physical_windows and human_confirmed)
    return {
        "allowed": allowed,
        "reason": "authorized" if allowed else "physical Windows + explicit human confirmation required",
        "automatic_installation": False,
        "automatic_publication": False,
    }
