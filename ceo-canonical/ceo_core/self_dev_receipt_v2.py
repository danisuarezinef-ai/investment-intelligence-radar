from __future__ import annotations

import hashlib
import json
from typing import Any

from .self_dev_handoff import validate_self_development_receipt

PROTECTED_PREFIXES = (
    "ceo_core/update_trust",
    "ceo_core/release_signing_authority",
    "ceo_core/credentials",
    "ceo_core/capability_policy",
    "ceo_core/security_",
    "scripts/bootstrap_release_signer",
    "scripts/sign_update",
)


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _norm(path: str) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def _is_protected(path: str) -> bool:
    p = _norm(path)
    return any(p.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def validate_self_development_receipt_v2(
    receipt: dict[str, Any],
    *,
    expected_base_version: str | None = None,
) -> dict[str, Any]:
    """Strict, side-effect-free validator for CEO self-development receipts.

    The validator deliberately proves only eligibility for comparison.  It never
    grants merge, publication, installation or Stable-promotion authority.
    """
    legacy = validate_self_development_receipt(receipt)
    problems = list(legacy.get("problems") or [])
    changed = sorted({_norm(x) for x in (receipt.get("changed_files") or []) if str(x).strip()})
    if not changed:
        problems.append("changed_files_empty")
    if len(changed) > 5000:
        problems.append("changed_files_unbounded")

    if expected_base_version is not None and str(receipt.get("base_version") or "") != str(expected_base_version):
        problems.append("base_version_mismatch")

    candidate_id = str(receipt.get("candidate_id") or "").strip()
    if not candidate_id or len(candidate_id) > 160:
        problems.append("candidate_id_invalid")

    tests = receipt.get("tests") if isinstance(receipt.get("tests"), dict) else {}
    passed = int(tests.get("passed") or 0)
    failed = int(tests.get("failed") or 0)
    if passed <= 0:
        problems.append("no_passing_tests")
    if failed:
        problems.append("tests_failed")

    file_hashes = receipt.get("file_hashes") if isinstance(receipt.get("file_hashes"), dict) else {}
    normalized_hashes: dict[str, str] = {}
    if file_hashes:
        for raw_path, raw_digest in file_hashes.items():
            path = _norm(str(raw_path))
            digest = str(raw_digest).lower().strip()
            if path not in changed:
                problems.append(f"hash_for_unchanged_path:{path}")
                continue
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                problems.append(f"invalid_sha256:{path}")
                continue
            normalized_hashes[path] = digest

    evidence = receipt.get("evidence_refs") or []
    if evidence and not isinstance(evidence, list):
        problems.append("evidence_refs_not_list")
        evidence = []

    protected = [p for p in changed if _is_protected(p)]
    receipt_digest = hashlib.sha256(_canon(receipt)).hexdigest()
    change_set_digest = hashlib.sha256(_canon({"files": changed, "hashes": normalized_hashes})).hexdigest()
    return {
        "schema_version": 2,
        "ok": not problems,
        "problems": sorted(set(problems)),
        "receipt_sha256": receipt_digest,
        "change_set_sha256": change_set_digest,
        "candidate_id": candidate_id,
        "base_version": str(receipt.get("base_version") or ""),
        "candidate_version": str(receipt.get("candidate_version") or ""),
        "changed_files": changed,
        "file_hashes": normalized_hashes,
        "protected_files": protected,
        "tests": {"passed": passed, "failed": failed},
        "evidence_refs": [str(x) for x in evidence if str(x).strip()][:500],
        "eligible_for_comparison": not problems,
        "eligible_for_automatic_merge": False,
        "eligible_for_automatic_promotion": False,
        "automatic_publication": False,
        "automatic_installation": False,
        "protected_changes_require_privileged_review": bool(protected),
    }
