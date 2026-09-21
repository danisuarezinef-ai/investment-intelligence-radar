from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED = {"candidate_id", "base_version", "candidate_version", "changed_files", "tests", "safety"}


def validate_self_development_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(REQUIRED - set(receipt))
    problems: list[str] = []
    if missing:
        problems.append("missing:" + ",".join(missing))
    if receipt.get("published") is True or receipt.get("installed") is True or receipt.get("auto_promoted") is True:
        problems.append("side_effect_claim_not_allowed")
    safety = receipt.get("safety") if isinstance(receipt.get("safety"), dict) else {}
    for key in ("stable_unchanged", "automatic_spending_false", "automatic_publication_false", "automatic_installation_false"):
        if safety.get(key) is not True:
            problems.append(f"safety:{key}")
    tests = receipt.get("tests") if isinstance(receipt.get("tests"), dict) else {}
    if int(tests.get("failed") or 0) > 0:
        problems.append("tests_failed")
    canonical = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "ok": not problems,
        "problems": problems,
        "receipt_sha256": hashlib.sha256(canonical).hexdigest(),
        "eligible_for_comparison": not problems,
        "eligible_for_promotion": False,
        "promotion_requires_human": True,
    }


def compare_self_development_receipts(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    va, vb = validate_self_development_receipt(a), validate_self_development_receipt(b)
    af = set(map(str, a.get("changed_files") or [])); bf = set(map(str, b.get("changed_files") or []))
    return {
        "a_valid": va["ok"], "b_valid": vb["ok"],
        "overlap_files": sorted(af & bf),
        "only_a_files": sorted(af - bf),
        "only_b_files": sorted(bf - af),
        "both_require_human_promotion": True,
    }


def write_receipt(path: str | Path, receipt: dict[str, Any]) -> dict[str, Any]:
    verdict = validate_self_development_receipt(receipt)
    payload = {"receipt": receipt, "validation": verdict}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
