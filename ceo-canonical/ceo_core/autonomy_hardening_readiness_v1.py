from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class AutonomyHardeningReadinessV1:
    recovery_budget_guard: bool
    productive_progress_watchdog: bool
    churn_circuit_breaker: bool
    goal_completion_resolver: bool
    queue_consistency_rebuilder: bool
    productivity_supervisor: bool
    historical_incident_pack: bool
    hardening_soak: bool
    dev212_regression: bool
    clean_package: bool
    local_candidate_ready: bool
    windows_physical_verified: bool = False
    production_verified: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_autonomy_hardening_readiness_v1(**gates: bool) -> AutonomyHardeningReadinessV1:
    names = [
        "recovery_budget_guard", "productive_progress_watchdog", "churn_circuit_breaker",
        "goal_completion_resolver", "queue_consistency_rebuilder", "productivity_supervisor",
        "historical_incident_pack", "hardening_soak", "dev212_regression", "clean_package",
    ]
    vals = {name: bool(gates.get(name)) for name in names}
    return AutonomyHardeningReadinessV1(**vals, local_candidate_ready=all(vals.values()))
