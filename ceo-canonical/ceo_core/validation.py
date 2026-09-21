from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any
import json


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Maturity(IntEnum):
    IMPLEMENTED = 1
    TESTED = 2
    VALIDATED = 3
    STABLE = 4


@dataclass(slots=True)
class ValidationEvidence:
    evidence_id: str
    kind: str
    environment: str
    passed: bool
    detail: str
    created_at: str = field(default_factory=utcnow)
    artifact: str | None = None


@dataclass(slots=True)
class CapabilityRecord:
    capability: str
    maturity: str = "IMPLEMENTED"
    last_failure: str | None = None
    evidence: list[ValidationEvidence] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def highest_proven(self) -> str:
        if any(e.passed and e.kind == "stable_run" for e in self.evidence):
            return "STABLE"
        if any(e.passed and e.kind in {"live", "physical", "field_trial", "night_run"} for e in self.evidence):
            return "VALIDATED"
        if any(e.passed and e.kind in {"unit", "integration", "synthetic", "destructive", "endurance"} for e in self.evidence):
            return "TESTED"
        return "IMPLEMENTED"

    def recompute(self) -> str:
        self.maturity = self.highest_proven()
        return self.maturity


class ValidationRegistry:
    """Evidence-backed maturity registry.

    Crucial invariant: synthetic/local tests may raise a capability to TESTED, but never
    to VALIDATED/STABLE. Those require live/physical evidence. Stable requires repeated
    field evidence recorded explicitly as stable_run.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.records: dict[str, CapabilityRecord] = {}
        if self.path and self.path.exists():
            self.load()

    def ensure(self, capability: str, *, notes: list[str] | None = None) -> CapabilityRecord:
        rec = self.records.setdefault(capability, CapabilityRecord(capability=capability))
        if notes:
            rec.notes.extend(x for x in notes if x not in rec.notes)
        return rec

    def record(self, capability: str, evidence: ValidationEvidence) -> CapabilityRecord:
        rec = self.ensure(capability)
        rec.evidence.append(evidence)
        if not evidence.passed:
            rec.last_failure = f"{evidence.created_at}: {evidence.detail}"
        rec.recompute()
        self.save()
        return rec

    def matrix(self) -> list[dict[str, Any]]:
        out=[]
        for key in sorted(self.records):
            rec=self.records[key]
            out.append({
                "capability": rec.capability,
                "maturity": rec.recompute(),
                "implemented": True,
                "tested": Maturity[rec.maturity] >= Maturity.TESTED,
                "validated": Maturity[rec.maturity] >= Maturity.VALIDATED,
                "stable": Maturity[rec.maturity] >= Maturity.STABLE,
                "evidence_count": len(rec.evidence),
                "last_failure": rec.last_failure,
            })
        return out

    def summary(self) -> dict[str, int]:
        counts={m.name:0 for m in Maturity}
        for rec in self.records.values():
            counts[rec.recompute()] += 1
        return counts

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload={
            "schema_version": 1,
            "updated_at": utcnow(),
            "records": {
                k: {
                    "capability": v.capability,
                    "maturity": v.recompute(),
                    "last_failure": v.last_failure,
                    "notes": v.notes,
                    "evidence": [asdict(e) for e in v.evidence],
                } for k,v in self.records.items()
            },
        }
        self.path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    def load(self) -> None:
        raw=json.loads(self.path.read_text(encoding="utf-8"))
        self.records={}
        for k,v in raw.get("records",{}).items():
            self.records[k]=CapabilityRecord(
                capability=v.get("capability",k),
                maturity=v.get("maturity","IMPLEMENTED"),
                last_failure=v.get("last_failure"),
                notes=list(v.get("notes",[])),
                evidence=[ValidationEvidence(**e) for e in v.get("evidence",[])],
            )


@dataclass(slots=True)
class ValidationGateResult:
    channel: str
    passed: bool
    missing: list[str]
    detail: str


class StrictReleaseGates:
    """Strict gates based on evidence maturity, not on the existence of code."""

    CRITICAL = (
        "scheduler",
        "conversation_controller",
        "persistence_recovery",
        "resource_governor",
        "browser_worker",
    )

    def assess(self, registry: ValidationRegistry) -> dict[str, Any]:
        missing_tested=[c for c in self.CRITICAL if c not in registry.records or Maturity[registry.records[c].recompute()] < Maturity.TESTED]
        missing_validated=[c for c in self.CRITICAL if c not in registry.records or Maturity[registry.records[c].recompute()] < Maturity.VALIDATED]
        missing_stable=[c for c in self.CRITICAL if c not in registry.records or Maturity[registry.records[c].recompute()] < Maturity.STABLE]
        gates=[
            ValidationGateResult("RC", not missing_tested, missing_tested, "Critical capabilities must be TESTED."),
            ValidationGateResult("VALIDATED", not missing_validated, missing_validated, "Critical capabilities must have live/physical validation."),
            ValidationGateResult("STABLE", not missing_stable, missing_stable, "Critical capabilities require repeated stable field runs."),
        ]
        return {"gates":[asdict(g) for g in gates],"highest_channel": next((g.channel for g in reversed(gates) if g.passed),"PRE_RC")}
