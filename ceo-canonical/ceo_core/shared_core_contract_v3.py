from __future__ import annotations

import hashlib
import json
from typing import Any

REQUIRED_FEATURES = {
    "task_exchange",
    "evidence_exchange",
    "update_metadata",
    "capability_manifest",
}
FORBIDDEN_SHARED_FEATURES = {
    "windows_ui",
    "android_ui",
    "windows_installer",
    "android_installer",
    "arbitrary_shell",
    "credential_export",
    "payments",
    "subscriptions",
    "real_trading",
}


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def validate_shared_core_contract_v3(contract: dict[str, Any]) -> dict[str, Any]:
    problems: list[str] = []
    protocol = int(contract.get("shared_core_protocol") or 0)
    if protocol < 2:
        problems.append("shared_core_protocol_too_old")

    platforms = {str(v).strip().lower() for v in contract.get("platforms", []) if str(v).strip()}
    if not {"windows", "android"}.issubset(platforms):
        problems.append("windows_android_required")

    features = {str(v).strip() for v in contract.get("shared_features", []) if str(v).strip()}
    missing = sorted(REQUIRED_FEATURES - features)
    if missing:
        problems.append("missing_features:" + ",".join(missing))
    forbidden = sorted(FORBIDDEN_SHARED_FEATURES & features)
    if forbidden:
        problems.append("forbidden_shared_features:" + ",".join(forbidden))

    ui_independent = contract.get("platform_ui_independent") is True
    packaging_independent = contract.get("platform_packaging_independent") is True
    if not ui_independent:
        problems.append("platform_ui_must_remain_independent")
    if not packaging_independent:
        problems.append("platform_packaging_must_remain_independent")

    schemas = contract.get("schemas") if isinstance(contract.get("schemas"), dict) else {}
    normalized_schemas: dict[str, int] = {}
    for key, value in sorted(schemas.items()):
        name = str(key).strip()
        try:
            version = int(value)
        except (TypeError, ValueError):
            problems.append("schema_version_invalid:" + name)
            continue
        if not name or version <= 0:
            problems.append("schema_version_invalid:" + name)
            continue
        normalized_schemas[name] = version
    if not normalized_schemas:
        problems.append("schemas_required")

    normalized = {
        "shared_core_protocol": protocol,
        "platforms": sorted(platforms),
        "shared_features": sorted(features),
        "schemas": normalized_schemas,
        "platform_ui_independent": ui_independent,
        "platform_packaging_independent": packaging_independent,
    }
    fingerprint = hashlib.sha256(_canon(normalized)).hexdigest()
    return {
        "schema_version": 3,
        "ok": not problems,
        "problems": sorted(set(problems)),
        "normalized": normalized,
        "contract_sha256": fingerprint,
        "automatic_merge": False,
        "automatic_publication": False,
        "automatic_installation": False,
    }
