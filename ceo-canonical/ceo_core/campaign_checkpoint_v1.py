from __future__ import annotations

import hashlib
import json
from typing import Any

from .physical_evidence_schema_v1 import PHYSICAL_GATES, validate_physical_evidence_v1


def _canon(v: Any) -> bytes:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_campaign_checkpoint_v1(*, campaign_id: str, candidate_sha256: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    verified: list[str] = []
    problems: list[str] = []
    normalized: list[dict[str, Any]] = []
    by_gate = {str(x.get("gate") or ""): x for x in evidence}
    stopped = False
    for gate in PHYSICAL_GATES:
        row = by_gate.get(gate) or {"gate": gate, "status": "NOT_VERIFIED", "source": "plan_only", "candidate_sha256": candidate_sha256}
        verdict = validate_physical_evidence_v1(row, gate=gate)
        normalized.append(verdict["record"])
        if not verdict["ok"]:
            problems.extend(f"{gate}:{p}" for p in verdict["problems"])
            stopped = True
            continue
        status = verdict["record"]["status"]
        if stopped and status == "PASS":
            problems.append(f"{gate}:pass_after_gap_or_failure")
        if status == "PASS" and not stopped:
            verified.append(gate)
        elif status == "FAIL":
            stopped = True
        else:
            stopped = True
    payload = {
        "schema_version": 1,
        "campaign_id": str(campaign_id).strip(),
        "candidate_sha256": str(candidate_sha256).strip().lower(),
        "verified": verified,
        "verified_count": len(verified),
        "total": len(PHYSICAL_GATES),
        "next_gate": PHYSICAL_GATES[len(verified)] if len(verified) < len(PHYSICAL_GATES) else None,
        "evidence_head": hashlib.sha256(_canon(normalized)).hexdigest(),
        "physical_windows_required": True,
        "complete": len(verified) == len(PHYSICAL_GATES),
    }
    payload["checkpoint_sha256"] = hashlib.sha256(_canon(payload)).hexdigest()
    return {"ok": bool(str(campaign_id).strip()) and not problems, "problems": sorted(set(problems)), **payload}


def verify_campaign_checkpoint_v1(checkpoint: dict[str, Any]) -> dict[str, Any]:
    claimed = str(checkpoint.get("checkpoint_sha256") or "")
    payload = {k: v for k, v in checkpoint.items() if k not in {"ok", "problems", "checkpoint_sha256"}}
    expected = hashlib.sha256(_canon(payload)).hexdigest()
    verified = list(checkpoint.get("verified") or [])
    prefix_ok = verified == list(PHYSICAL_GATES[:len(verified)])
    return {
        "ok": bool(claimed and claimed == expected and prefix_ok and checkpoint.get("physical_windows_required") is True),
        "digest_ok": claimed == expected,
        "ordered_prefix_ok": prefix_ok,
        "resume_gate": checkpoint.get("next_gate"),
        "side_effects_allowed": False,
    }
