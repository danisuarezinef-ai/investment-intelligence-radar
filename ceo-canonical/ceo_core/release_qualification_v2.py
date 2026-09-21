from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .models import ProjectState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class QualificationGate:
    gate_id: str
    passed: bool
    level: str  # local | physical | production
    detail: str


class ReleaseQualificationV2:
    """Fail-closed aggregation of DEV46–DEV55 and historical physical gates."""

    def assess(
        self,
        state: ProjectState,
        *,
        local_tests_passed: bool,
        clean_extract_tests_passed: bool,
        package_contract_passed: bool,
        security_passed: bool,
        stress_passed: bool,
        benchmark_passed: bool,
        backup_restore_passed: bool,
        field_campaign_passed: bool,
        signed_with_persistent_authority: bool,
        remote_published: bool = False,
    ) -> dict[str, Any]:
        gates = [
            QualificationGate("local_tests", bool(local_tests_passed), "local", "source regression/new suite"),
            QualificationGate("clean_extract", bool(clean_extract_tests_passed), "local", "exact ZIP external harness"),
            QualificationGate("package_contract", bool(package_contract_passed), "local", "required paths + critical hashes"),
            QualificationGate("security", bool(security_passed), "local", "security posture gate"),
            QualificationGate("stress_lab", bool(stress_passed), "local", "fault injection + invariant stress"),
            QualificationGate("benchmarks", bool(benchmark_passed), "local", "holdout regression budget"),
            QualificationGate("backup_restore", bool(backup_restore_passed), "local", "verified non-destructive restore"),
            QualificationGate("persistent_signer", bool(signed_with_persistent_authority), "physical", "real Windows persistent release authority"),
            QualificationGate("windows_field_campaign", bool(field_campaign_passed), "physical", "DEV47 evidence-first campaign"),
        ]
        local_ready = all(g.passed for g in gates if g.level == "local")
        physical_ready = local_ready and all(g.passed for g in gates if g.level == "physical")
        production_ready = physical_ready  # publication is not required to qualify; it is a separate human action.
        report = {
            "generated_at": _now(),
            "local_candidate_ready": local_ready,
            "physical_campaign_verified": bool(field_campaign_passed),
            "persistent_signer_verified": bool(signed_with_persistent_authority),
            "production_ready": production_ready,
            "remote_published": bool(remote_published),
            "publication_authorized": False,
            "automatic_installation": False,
            "automatic_publication": False,
            "gates": [asdict(g) for g in gates],
        }
        state.metadata["release_qualification_v2"] = report
        return report
