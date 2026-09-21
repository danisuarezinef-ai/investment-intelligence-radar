from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class ReleaseReadinessV16Result:
    dev189_regression: bool
    task_role_unification: bool
    scheduler_reconciliation: bool
    productive_progress_v2: bool
    restart_recovery: bool
    liveness_guard: bool
    goal_audit_timing: bool
    mission_soak: bool
    clean_package: bool
    local_candidate_ready: bool
    windows_physical_verified: bool = False
    production_ready: bool = False
    installation_allowed: bool = False
    publication_allowed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_release_readiness_v16(**gates: bool) -> ReleaseReadinessV16Result:
    required = [
        bool(gates.get("dev189_regression")),
        bool(gates.get("task_role_unification")),
        bool(gates.get("scheduler_reconciliation")),
        bool(gates.get("productive_progress_v2")),
        bool(gates.get("restart_recovery")),
        bool(gates.get("liveness_guard")),
        bool(gates.get("goal_audit_timing")),
        bool(gates.get("mission_soak")),
        bool(gates.get("clean_package")),
    ]
    ready = all(required)
    return ReleaseReadinessV16Result(
        dev189_regression=required[0],
        task_role_unification=required[1],
        scheduler_reconciliation=required[2],
        productive_progress_v2=required[3],
        restart_recovery=required[4],
        liveness_guard=required[5],
        goal_audit_timing=required[6],
        mission_soak=required[7],
        clean_package=required[8],
        local_candidate_ready=ready,
    )
