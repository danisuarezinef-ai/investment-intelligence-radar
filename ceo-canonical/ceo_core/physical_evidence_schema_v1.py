from __future__ import annotations

import hashlib
import json
from typing import Any

PHYSICAL_GATES = (
    "baseline_health", "persistent_signer_self_test", "signed_candidate_stage", "isolated_preflight",
    "pre_cutover_snapshot", "activation", "health_confirmation", "rollback_drill", "restart_resume",
    "worker_recovery", "browser_recovery", "live_provider", "executive_ui_crosscheck", "self_dev_handoff",
    "mobile_sync_read_only",
)
ALLOWED_STATUS = {"NOT_VERIFIED", "PASS", "FAIL"}


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def evidence_digest(record: dict[str, Any]) -> str:
    row = {k: v for k, v in record.items() if k != "evidence_sha256"}
    return hashlib.sha256(_canon(row)).hexdigest()


def validate_physical_evidence_v1(record: dict[str, Any], *, gate: str | None = None) -> dict[str, Any]:
    problems: list[str] = []
    gate_id = str(record.get("gate") or gate or "").strip()
    status = str(record.get("status") or "NOT_VERIFIED").strip().upper()
    source = str(record.get("source") or "").strip()
    candidate_sha256 = str(record.get("candidate_sha256") or "").strip().lower()
    observed_at = str(record.get("observed_at") or "").strip()
    notes = str(record.get("notes") or "")[:2000]
    if gate_id not in PHYSICAL_GATES:
        problems.append("gate_invalid")
    if status not in ALLOWED_STATUS:
        problems.append("status_invalid")
    if len(candidate_sha256) != 64 or any(c not in "0123456789abcdef" for c in candidate_sha256):
        problems.append("candidate_sha256_invalid")
    if status in {"PASS", "FAIL"}:
        if source != "physical_windows":
            problems.append("verified_status_requires_physical_windows")
        if not observed_at:
            problems.append("verified_status_requires_observed_at")
    elif source not in {"", "plan_only"}:
        problems.append("not_verified_source_must_be_plan_only")
    normalized = {
        "schema_version": 1,
        "gate": gate_id,
        "status": status,
        "source": source or "plan_only",
        "candidate_sha256": candidate_sha256,
        "observed_at": observed_at,
        "notes": notes,
    }
    normalized["evidence_sha256"] = evidence_digest(normalized)
    claimed = str(record.get("evidence_sha256") or "").strip().lower()
    if claimed and claimed != normalized["evidence_sha256"]:
        problems.append("evidence_digest_mismatch")
    return {
        "ok": not problems,
        "problems": sorted(set(problems)),
        "record": normalized,
        "physical_verification_claimed": status in {"PASS", "FAIL"},
        "side_effects_allowed": False,
    }


def blank_physical_evidence_set_v1(candidate_sha256: str) -> list[dict[str, Any]]:
    return [validate_physical_evidence_v1({
        "gate": gate, "status": "NOT_VERIFIED", "source": "plan_only", "candidate_sha256": candidate_sha256,
    })["record"] for gate in PHYSICAL_GATES]
