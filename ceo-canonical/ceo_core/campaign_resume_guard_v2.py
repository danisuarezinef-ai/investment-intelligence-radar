from __future__ import annotations

from typing import Any
from .physical_evidence_schema_v1 import PHYSICAL_GATES, validate_physical_evidence_v1


def qualify_campaign_resume_v2(*, candidate_sha256: str, evidence: list[dict[str, Any]], expected_candidate_sha256: str) -> dict[str, Any]:
    problems: list[str] = []
    if candidate_sha256 != expected_candidate_sha256:
        problems.append("candidate_identity_mismatch")
    by_gate: dict[str, dict[str, Any]] = {}
    for row in evidence:
        gate = str(row.get("gate") or "")
        if gate in by_gate:
            problems.append("duplicate_gate_evidence")
            continue
        verdict = validate_physical_evidence_v1(row, gate=gate)
        if not verdict["ok"]:
            problems.extend("invalid_" + p for p in verdict["problems"])
        by_gate[gate] = verdict["record"]
    completed: list[str] = []
    failed_gate: str | None = None
    gap_seen = False
    for gate in PHYSICAL_GATES:
        row = by_gate.get(gate)
        status = row.get("status") if row else "NOT_VERIFIED"
        if status == "PASS":
            if gap_seen:
                problems.append("passed_gate_after_gap")
            completed.append(gate)
        elif status == "FAIL":
            failed_gate = gate
            gap_seen = True
        else:
            gap_seen = True
    next_gate = None
    if not failed_gate:
        for gate in PHYSICAL_GATES:
            if gate not in completed:
                next_gate = gate
                break
    if failed_gate:
        problems.append("campaign_has_failed_gate")
    return {
        "ok": not problems,
        "status": "RESUME_READY" if not problems else "BLOCKED",
        "problems": sorted(set(problems)),
        "completed_prefix": completed,
        "completed_count": len(completed),
        "next_gate": next_gate,
        "all_physical_gates_passed": len(completed) == len(PHYSICAL_GATES) and not problems,
        "automatic_execution": False,
        "requires_explicit_human_start_or_resume": True,
    }
