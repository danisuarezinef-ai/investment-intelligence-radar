from __future__ import annotations

import hashlib
import json
from typing import Any

from .self_dev_receipt_v2 import validate_self_development_receipt_v2


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_text(value: str) -> bool:
    s = str(value or "").strip().lower()
    return len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def validate_self_development_receipt_v3(
    receipt: dict[str, Any], *, expected_base_version: str | None = None
) -> dict[str, Any]:
    """Validate a self-development receipt for evidence exchange, never promotion.

    v3 adds whole-tree provenance, bounded evidence objects and explicit authority
    declarations. Missing strong provenance does not mutate anything; it simply
    prevents a receipt from qualifying for unattended convergence.
    """
    v2 = validate_self_development_receipt_v2(receipt, expected_base_version=expected_base_version)
    problems = list(v2["problems"])
    warnings: list[str] = []

    base_tree = str(receipt.get("base_tree_sha256") or "").lower().strip()
    candidate_tree = str(receipt.get("candidate_tree_sha256") or "").lower().strip()
    if not _sha256_text(base_tree):
        warnings.append("base_tree_sha256_missing_or_invalid")
    if not _sha256_text(candidate_tree):
        warnings.append("candidate_tree_sha256_missing_or_invalid")
    if base_tree and candidate_tree and base_tree == candidate_tree and v2["changed_files"]:
        problems.append("tree_digest_unchanged_despite_changed_files")

    evidence_rows = receipt.get("evidence") if isinstance(receipt.get("evidence"), list) else []
    if len(evidence_rows) > 1000:
        problems.append("evidence_unbounded")
    normalized_evidence: list[dict[str, str]] = []
    for row in evidence_rows[:1000]:
        if not isinstance(row, dict):
            problems.append("evidence_row_not_object")
            continue
        kind = str(row.get("kind") or "").strip()
        digest = str(row.get("sha256") or "").lower().strip()
        ref = str(row.get("ref") or "").strip()
        if not kind or not ref or not _sha256_text(digest):
            problems.append("evidence_row_invalid")
            continue
        normalized_evidence.append({"kind": kind[:80], "ref": ref[:500], "sha256": digest})

    authority = receipt.get("authority") if isinstance(receipt.get("authority"), dict) else {}
    prohibited = {
        "automatic_merge": bool(authority.get("automatic_merge", False)),
        "automatic_promotion": bool(authority.get("automatic_promotion", False)),
        "automatic_publication": bool(authority.get("automatic_publication", False)),
        "automatic_installation": bool(authority.get("automatic_installation", False)),
        "automatic_spending": bool(authority.get("automatic_spending", False)),
    }
    if any(prohibited.values()):
        problems.append("receipt_claims_forbidden_authority")

    strong = bool(v2["ok"] and _sha256_text(base_tree) and _sha256_text(candidate_tree) and normalized_evidence)
    signed_payload = {
        "candidate_id": v2["candidate_id"],
        "base_version": v2["base_version"],
        "candidate_version": v2["candidate_version"],
        "change_set_sha256": v2["change_set_sha256"],
        "base_tree_sha256": base_tree,
        "candidate_tree_sha256": candidate_tree,
        "evidence": normalized_evidence,
    }
    return {
        **v2,
        "schema_version": 3,
        "ok": not problems,
        "problems": sorted(set(problems)),
        "warnings": sorted(set(warnings)),
        "base_tree_sha256": base_tree,
        "candidate_tree_sha256": candidate_tree,
        "evidence": normalized_evidence,
        "strong_attestation": strong and not problems,
        "attestation_sha256": hashlib.sha256(_canon(signed_payload)).hexdigest(),
        "eligible_for_unattended_convergence": False,
        "requires_independent_validation": True,
        "automatic_merge": False,
        "automatic_promotion": False,
        "automatic_publication": False,
        "automatic_installation": False,
        "automatic_spending": False,
    }
