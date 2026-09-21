from __future__ import annotations

from typing import Any

from .benchmark_arbitrator_v1 import arbitrate_candidate_metrics
from .convergence_merge_plan_v1 import build_convergence_plan


def evaluate_convergence(
    windows_receipt: dict[str, Any], mobile_receipt: dict[str, Any], *, common_base_version: str,
    baseline_metrics: dict[str, list[float]], windows_metrics: dict[str, list[float]], mobile_metrics: dict[str, list[float]],
    directions: dict[str, str],
) -> dict[str, Any]:
    plan = build_convergence_plan(windows_receipt, mobile_receipt, common_base_version=common_base_version)
    bench = arbitrate_candidate_metrics(baseline_metrics, windows_metrics, mobile_metrics, directions)
    blocked = bool(plan["protected_overlap"] or plan["divergent_overlap"] or not plan["windows_validation"]["ok"] or not plan["mobile_validation"]["ok"])
    return {
        "schema_version": 1,
        "merge_plan": plan,
        "benchmark": bench,
        "convergence_candidate_ready_for_sandbox": bool(not blocked and bench["benchmark_preferred_candidate"]),
        "sandbox_only": True,
        "requires_human_merge_decision": bool(plan["requires_human_merge_decision"]),
        "automatic_merge": False,
        "automatic_stable_promotion": False,
        "automatic_publication": False,
        "automatic_installation": False,
    }
