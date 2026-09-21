from __future__ import annotations

import hashlib
import json
from typing import Any


def _sha256(value: Any) -> bool:
    s = str(value or "").strip().lower()
    return len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_cross_platform_provenance_v1(
    *, windows_artifact_sha256: str, windows_tree_sha256: str, android_source_sha256: str,
    android_sbom_sha256: str, shared_core_contract_sha256: str, base_version: str,
) -> dict[str, Any]:
    payload = {
        "base_version": str(base_version).strip(),
        "windows_artifact_sha256": str(windows_artifact_sha256).strip().lower(),
        "windows_tree_sha256": str(windows_tree_sha256).strip().lower(),
        "android_source_sha256": str(android_source_sha256).strip().lower(),
        "android_sbom_sha256": str(android_sbom_sha256).strip().lower(),
        "shared_core_contract_sha256": str(shared_core_contract_sha256).strip().lower(),
    }
    invalid = sorted(k for k, v in payload.items() if k != "base_version" and not _sha256(v))
    if not payload["base_version"]:
        invalid.append("base_version")
    root = hashlib.sha256(_canon(payload)).hexdigest() if not invalid else ""
    return {
        "schema_version": 1,
        "ok": not invalid,
        "invalid_fields": invalid,
        "payload": payload,
        "provenance_root_sha256": root,
        "binds_windows_and_android": not invalid,
        "promotion_authority": False,
    }
