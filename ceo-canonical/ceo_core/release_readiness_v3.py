from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from .models import ProjectState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ReadinessGate:
    gate_id: str
    passed: bool
    level: str
    detail: str


class ReleaseReadinessV3:
    """DEV65 qualification: local operational gates and physical gates stay separate."""

    KEY = "release_readiness_v3"

    def assess(self, state: ProjectState, *, local_tests: bool, clean_extract: bool, package_contract: bool, security: bool, stress: bool, checkpoint_integrity: bool, remote_replay: bool, mobile_protocol: bool, canary: bool, incident_recovery: bool, persistent_signer: bool = False, windows_campaign: bool = False) -> dict[str, Any]:
        gates = [
            ReadinessGate("local_tests", local_tests, "local", "DEV56-65 source harness"),
            ReadinessGate("clean_extract", clean_extract, "local", "exact final ZIP harness"),
            ReadinessGate("package_contract", package_contract, "local", "required paths + critical hashes"),
            ReadinessGate("security", security, "local", "secret/safety posture"),
            ReadinessGate("stress", stress, "local", "fault and scale stress"),
            ReadinessGate("checkpoint_integrity", checkpoint_integrity, "local", "state digest/tamper detection"),
            ReadinessGate("remote_replay", remote_replay, "local", "remote mutation replay rejection"),
            ReadinessGate("mobile_protocol", mobile_protocol, "local", "safe compute envelope verification"),
            ReadinessGate("canary", canary, "local", "no automatic candidate promotion"),
            ReadinessGate("incident_recovery", incident_recovery, "local", "circuit breaker recovery"),
            ReadinessGate("persistent_signer", persistent_signer, "physical", "real Windows release authority"),
            ReadinessGate("windows_campaign", windows_campaign, "physical", "DEV47 physical campaign"),
        ]
        local_ready = all(g.passed for g in gates if g.level == "local")
        production_ready = local_ready and all(g.passed for g in gates if g.level == "physical")
        report = {"generated_at":_now(), "local_candidate_ready":local_ready, "production_ready":production_ready, "automatic_publication":False, "automatic_installation":False, "gates":[asdict(g) for g in gates]}
        state.metadata[self.KEY] = report
        return report
