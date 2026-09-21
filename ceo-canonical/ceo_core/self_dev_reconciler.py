from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any, Iterable


PROTECTED_PREFIXES = (
    "ceo_core/update_trust.json",
    "ceo_core/release_signing_authority.py",
    "ceo_core/credentials.py",
    "scripts/sign_update_with_local_authority.py",
)


@dataclass(slots=True)
class ReconcileFinding:
    path: str
    relation: str
    risk: str
    reason: str


def _files(receipt: dict[str, Any]) -> set[str]:
    return {str(x).replace("\\", "/").lstrip("./") for x in (receipt.get("changed_files") or []) if str(x).strip()}


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _risk(path: str) -> tuple[str, str]:
    p = path.lower()
    if any(path == x or path.startswith(x.rstrip(".jsonpy") + "/") for x in PROTECTED_PREFIXES):
        return "protected", "trust/signing/credential path"
    if any(token in p for token in ("updater", "update_", "release_", "installer", "bootstrap", "relaunch", "launch_current")):
        return "high", "release/update execution path"
    if any(token in p for token in ("scheduler", "runtime", "store", "sqlite", "remote", "mobile_sync", "capability")):
        return "medium", "runtime/governance path"
    return "normal", "ordinary application path"


def reconcile_self_development(
    external_receipt: dict[str, Any],
    mobile_candidate_files: Iterable[str],
    *,
    mobile_candidate_id: str = "mobile-candidate",
) -> dict[str, Any]:
    """Build a conflict/risk map between Windows self-development and mobile work.

    This function is intentionally advisory.  It never edits, merges, promotes,
    publishes, signs or installs anything.
    """
    external = _files(external_receipt)
    mobile = {str(x).replace("\\", "/").lstrip("./") for x in mobile_candidate_files if str(x).strip()}
    findings: list[ReconcileFinding] = []
    for path in sorted(external | mobile):
        relation = "overlap" if path in external and path in mobile else ("external_only" if path in external else "mobile_only")
        risk, reason = _risk(path)
        findings.append(ReconcileFinding(path, relation, risk, reason))

    overlap = sorted(external & mobile)
    protected_overlap = [f.path for f in findings if f.relation == "overlap" and f.risk == "protected"]
    high_overlap = [f.path for f in findings if f.relation == "overlap" and f.risk == "high"]
    requires_human = bool(overlap)
    recommended = "independent_review" if overlap else "parallel_candidates_safe_to_compare"
    if protected_overlap:
        recommended = "privileged_human_review_required"
    elif high_overlap:
        recommended = "adversarial_merge_review_required"

    return {
        "schema_version": 1,
        "external_candidate_id": str(external_receipt.get("candidate_id") or "unknown"),
        "mobile_candidate_id": str(mobile_candidate_id),
        "external_receipt_digest": _digest(external_receipt),
        "external_files": sorted(external),
        "mobile_files": sorted(mobile),
        "overlap_files": overlap,
        "protected_overlap": protected_overlap,
        "high_risk_overlap": high_overlap,
        "findings": [asdict(x) for x in findings],
        "requires_human_merge_decision": requires_human,
        "recommended_next_step": recommended,
        "automatic_merge": False,
        "automatic_promotion": False,
        "automatic_publication": False,
        "automatic_installation": False,
    }
