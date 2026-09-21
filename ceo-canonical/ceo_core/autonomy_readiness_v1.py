from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class AutonomyReadinessV1:
    productive_contract: bool
    worker_lifecycle: bool
    multi_worker: bool
    provider_resilience: bool
    evidence_engine: bool
    self_dev_sandbox: bool
    autonomous_replan: bool
    mission_continuity: bool
    mission_soak: bool
    clean_package: bool
    local_autonomy_candidate_ready: bool
    windows_install_candidate_ready: bool
    windows_physical_verified: bool = False
    production_ready: bool = False
    automatic_publication: bool = False
    automatic_installation: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_autonomy_readiness_v1(**gates: bool) -> AutonomyReadinessV1:
    names = [
        "productive_contract", "worker_lifecycle", "multi_worker", "provider_resilience",
        "evidence_engine", "self_dev_sandbox", "autonomous_replan", "mission_continuity",
        "mission_soak", "clean_package",
    ]
    values = {name: bool(gates.get(name)) for name in names}
    ready = all(values.values())
    return AutonomyReadinessV1(**values, local_autonomy_candidate_ready=ready, windows_install_candidate_ready=ready)
