from __future__ import annotations

import hashlib
import json
from typing import Any


def _sha(v: Any) -> bool:
    s = str(v or "").lower().strip()
    return len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def _canon(v: Any) -> bytes:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_one_shot_preflight_bundle_v1(**parts: Any) -> dict[str, Any]:
    required = (
        "base_artifact_sha256", "candidate_tree_sha256", "android_source_sha256", "android_sbom_sha256",
        "shared_contract_sha256", "physical_schema_sha256", "campaign_checkpoint_sha256",
    )
    problems = [f"{k}_invalid" for k in required if not _sha(parts.get(k))]
    payload = {"schema_version": 1, **{k: str(parts.get(k) or "").strip().lower() for k in required}}
    payload.update({
        "windows_package_kind": "windows_zip",
        "android_package_kind": "android_apk",
        "ui_independent": True,
        "packaging_independent": True,
        "physical_side_effects_executed": False,
    })
    payload["bundle_sha256"] = hashlib.sha256(_canon(payload)).hexdigest()
    return {"ok": not problems, "problems": problems, **payload}
