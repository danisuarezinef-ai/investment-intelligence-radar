from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .models import ProjectState
from .production_intelligence import MissionControl
from .security_governance_v2 import SecurityThreatModel
from .long_horizon import LongHorizonMemoryAuditor


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class GateCheck:
    id: str
    status: str
    required_for: str
    evidence: str
    deferred_reason: str | None = None


class PreProductionGate:
    """Local certification gate that never upgrades deferred field evidence.

    It deliberately distinguishes LOCAL_RC_READY from PRODUCTION_VERIFIED.
    Windows/live gates can remain deferred indefinitely without weakening them.
    """

    EXTERNAL_DEFERRED = {
        "windows_install": "Physical Windows installation is deferred by operator order.",
        "windows_restart": "Physical Windows restart/recovery is deferred by operator order.",
        "live_provider": "Authenticated external-provider validation has not been executed in this environment.",
        "production_proof": "End-to-end field production proof requires real external execution.",
    }

    def evaluate(self, state: ProjectState, *, local_test_passed: bool, compile_passed: bool, static_passed: bool, security_scan_passed: bool) -> dict[str, Any]:
        mission = MissionControl().snapshot(state, persist=False)
        memory = LongHorizonMemoryAuditor().audit(state)
        threats = SecurityThreatModel().snapshot(state)
        checks = [
            GateCheck("local_tests", "PASS" if local_test_passed else "FAIL", "local_rc", "automated test suite"),
            GateCheck("compile", "PASS" if compile_passed else "FAIL", "local_rc", "compileall"),
            GateCheck("static", "PASS" if static_passed else "FAIL", "local_rc", "AST/static checks"),
            GateCheck("security_scan", "PASS" if security_scan_passed else "FAIL", "local_rc", "secret/security scan"),
            GateCheck("graph_integrity", "PASS" if mission["blueprint"]["graph_valid"] else "FAIL", "local_rc", "TaskGraph audit"),
            GateCheck("long_horizon_memory", "PASS" if memory["pass"] else "FAIL", "local_rc", "memory invariant audit"),
            GateCheck("critical_security_gates", "PASS" if not threats["critical_unmitigated"] else "FAIL", "local_rc", "threat model"),
        ]
        for gate_id, reason in self.EXTERNAL_DEFERRED.items():
            checks.append(GateCheck(gate_id, "DEFERRED", "production", "field evidence required", reason))
        local_ok = all(c.status == "PASS" for c in checks if c.required_for == "local_rc")
        production_ok = local_ok and all(c.status == "PASS" for c in checks if c.required_for == "production")
        report = {
            "generated_at": _now(),
            "local_rc_ready": local_ok,
            "production_verified": production_ok,
            "checks": [asdict(x) for x in checks],
            "deferred_external": [c.id for c in checks if c.status == "DEFERRED"],
            "health": mission["health"],
        }
        state.metadata["preproduction_gate_v1"] = report
        return report
