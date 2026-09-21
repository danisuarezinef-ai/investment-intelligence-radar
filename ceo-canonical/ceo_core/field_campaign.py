from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from .models import ProjectState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class FieldGate:
    gate_id: str
    label: str
    physical_required: bool = True


class WindowsFieldCampaign:
    """Evidence-first plan for the next physical Windows campaign.

    A gate is never inferred from local tests. Physical gates require an evidence record
    explicitly marked ``physical_windows``; this prevents local/container PASS values
    from being accidentally promoted to field verification.
    """

    KEY = "windows_field_campaign_v2"
    GATES = (
        FieldGate("trust_rebootstrap", "persistent signer trust rebootstrap"),
        FieldGate("signer_self_test", "Credential Manager/DPAPI signer self-test"),
        FieldGate("signed_update_stage", "signed update download and stage"),
        FieldGate("activation_health", "activation-id health handshake"),
        FieldGate("rollback", "forced rollback to previous healthy version"),
        FieldGate("restart_resume", "restart + durable project resume"),
        FieldGate("worker_recovery", "stale/orphan worker recovery"),
        FieldGate("browser_recovery", "physical Chrome/application recovery"),
        FieldGate("live_provider", "authenticated provider work"),
        FieldGate("observability", "live Activity/operations matches actual work"),
        FieldGate("long_mission", "extended autonomous mission"),
    )

    def initialize(self, state: ProjectState, candidate_version: str) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {})
        row.setdefault("campaign_id", sha256(f"{state.id}:{candidate_version}".encode()).hexdigest()[:16])
        row["candidate_version"] = str(candidate_version)
        row.setdefault("evidence", {})
        row.setdefault("started_at", None)
        row.setdefault("completed_at", None)
        row["updated_at"] = _now()
        return self.snapshot(state)

    def record(
        self,
        state: ProjectState,
        gate_id: str,
        *,
        passed: bool,
        source_kind: str,
        evidence_ref: str,
        detail: str = "",
    ) -> dict[str, Any]:
        known = {g.gate_id: g for g in self.GATES}
        if gate_id not in known:
            raise KeyError(f"unknown field gate: {gate_id}")
        gate = known[gate_id]
        if gate.physical_required and source_kind != "physical_windows":
            raise ValueError("physical gate requires source_kind=physical_windows")
        if not str(evidence_ref).strip():
            raise ValueError("field evidence requires a durable evidence_ref")
        campaign = state.metadata.setdefault(self.KEY, {})
        evidence = campaign.setdefault("evidence", {})
        evidence[gate_id] = {
            "passed": bool(passed), "source_kind": source_kind,
            "evidence_ref": str(evidence_ref), "detail": str(detail), "recorded_at": _now(),
        }
        campaign.setdefault("started_at", _now())
        campaign["updated_at"] = _now()
        snap = self.snapshot(state)
        if snap["all_physical_gates_passed"]:
            campaign["completed_at"] = _now()
        return self.snapshot(state)

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        campaign = state.metadata.get(self.KEY, {}) or {}
        evidence = campaign.get("evidence", {}) or {}
        rows = []
        for gate in self.GATES:
            ev = evidence.get(gate.gate_id)
            passed = bool(ev and ev.get("passed") and (not gate.physical_required or ev.get("source_kind") == "physical_windows"))
            rows.append({**asdict(gate), "passed": passed, "evidence": ev})
        return {
            "campaign_id": campaign.get("campaign_id"),
            "candidate_version": campaign.get("candidate_version"),
            "gates": rows,
            "passed": sum(1 for row in rows if row["passed"]),
            "total": len(rows),
            "all_physical_gates_passed": bool(rows) and all(row["passed"] for row in rows),
            "completed_at": campaign.get("completed_at"),
        }
