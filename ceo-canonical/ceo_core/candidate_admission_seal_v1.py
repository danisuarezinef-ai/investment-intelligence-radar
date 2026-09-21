from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_candidate_admission_seal_v1(
    candidate_root: str | Path,
    *,
    expected_version: str,
    campaign_id: str,
) -> dict[str, Any]:
    root = Path(candidate_root)
    contract_path = root / "CEO_UPDATE_PACKAGE.json"
    problems: list[str] = []
    contract: dict[str, Any] = {}
    if not contract_path.is_file():
        problems.append("package_contract_missing")
    else:
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
        except Exception:
            problems.append("package_contract_invalid_json")
    if contract and str(contract.get("app_version") or "") != str(expected_version):
        problems.append("candidate_version_mismatch")
    required = list(contract.get("required_paths") or []) if contract else []
    hashes = dict(contract.get("file_hashes") or {}) if contract else {}
    verified = 0
    for rel in required:
        p = root / str(rel)
        if not p.is_file():
            problems.append("missing:" + str(rel)); continue
        if str(rel) == "CEO_UPDATE_PACKAGE.json":
            continue
        got = _sha_bytes(p.read_bytes())
        if got != str(hashes.get(str(rel)) or ""):
            problems.append("hash:" + str(rel))
        else:
            verified += 1
    contract_sha = _sha_bytes(contract_path.read_bytes()) if contract_path.is_file() else ""
    evidence = {
        "schema_version": 1,
        "campaign_id": str(campaign_id),
        "candidate_version": str(expected_version),
        "contract_sha256": contract_sha,
        "required_paths": len(required),
        "hashes_verified": verified,
        "admitted": not problems,
        "problems": problems[:50],
        "automatic_activation": False,
        "physical_side_effects_executed": False,
    }
    evidence["seal_sha256"] = _sha_bytes(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return evidence
