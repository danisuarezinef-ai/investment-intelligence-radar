from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .models import ProjectState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Gate:
    gate_id: str
    passed: bool
    level: str
    detail: str


class ReleaseReadinessV4:
    """DEV70 fail-closed qualification including portfolio/governance/soak gates."""

    KEY = "release_readiness_v4"

    def assess(
        self,
        state: ProjectState,
        *,
        local_tests: bool,
        clean_extract: bool,
        package_contract: bool,
        security: bool,
        portfolio: bool,
        quota: bool,
        decision_trace: bool,
        delegation: bool,
        soak: bool,
        freeze: bool,
        persistent_signer: bool = False,
        windows_campaign: bool = False,
    ) -> dict[str, Any]:
        gates = [
            Gate("local_tests", local_tests, "local", "DEV66-70 source harness"),
            Gate("clean_extract", clean_extract, "local", "exact final ZIP harness"),
            Gate("package_contract", package_contract, "local", "required paths + critical hashes"),
            Gate("security", security, "local", "secret/safety posture"),
            Gate("portfolio", portfolio, "local", "cross-project fairness and pause gates"),
            Gate("quota", quota, "local", "renewable hard resource quotas"),
            Gate("decision_trace", decision_trace, "local", "tamper-evident decision provenance"),
            Gate("delegation", delegation, "local", "least-privilege delegation contracts"),
            Gate("soak", soak, "local", "logical soak invariants"),
            Gate("freeze", freeze, "local", "exact required-file freeze receipt"),
            Gate("persistent_signer", persistent_signer, "physical", "real Windows release authority"),
            Gate("windows_campaign", windows_campaign, "physical", "DEV47 evidence-first physical campaign"),
        ]
        local_ready = all(g.passed for g in gates if g.level == "local")
        production_ready = local_ready and all(g.passed for g in gates if g.level == "physical")
        report = {
            "generated_at": _now(),
            "local_candidate_ready": local_ready,
            "production_ready": production_ready,
            "automatic_publication": False,
            "automatic_installation": False,
            "gates": [asdict(g) for g in gates],
        }
        state.metadata[self.KEY] = report
        return report
