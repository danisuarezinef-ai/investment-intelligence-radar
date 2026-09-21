from __future__ import annotations

import hashlib
import json
from typing import Any


def _sha(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_android_artifact_identity_v1(*, source_fingerprint: str, build_payload_sha256: str,
                                       build_manifest_sha256: str, toolchain_lock_sha256: str,
                                       version_code: int, package_name: str = "ai.ceo.android.dev") -> dict[str, Any]:
    problems: list[str] = []
    values = {
        "source_fingerprint": source_fingerprint,
        "build_payload_sha256": build_payload_sha256,
        "build_manifest_sha256": build_manifest_sha256,
        "toolchain_lock_sha256": toolchain_lock_sha256,
    }
    for key, value in values.items():
        if not _sha(value):
            problems.append(key + "_invalid")
    if int(version_code) <= 0:
        problems.append("version_code_invalid")
    package = str(package_name or "").strip()
    if not package or " " in package:
        problems.append("package_name_invalid")
    row = {
        "schema_version": 1,
        **{key: str(value or "").strip().lower() for key, value in values.items()},
        "version_code": int(version_code),
        "package_name": package,
        "expected_build_type": "debug",
        "apk_sha256": None,
        "apk_built": False,
        "runtime_api35_executed": False,
        "runtime_api36_executed": False,
        "android_runtime_accepted": False,
        "production_verified": False,
    }
    row["identity_sha256"] = hashlib.sha256(_canon(row)).hexdigest()
    return {"ok": not problems, "status": "AWAITING_FIRST_DEBUG_APK" if not problems else "BLOCKED", "problems": sorted(set(problems)), **row}


def bind_built_apk_v1(identity: dict[str, Any], *, apk_sha256: str, build_receipt_sha256: str) -> dict[str, Any]:
    problems: list[str] = []
    if not identity.get("ok"):
        problems.append("identity_not_ready")
    if not _sha(apk_sha256):
        problems.append("apk_sha256_invalid")
    if not _sha(build_receipt_sha256):
        problems.append("build_receipt_sha256_invalid")
    return {
        "ok": not problems,
        "status": "DEBUG_APK_IDENTITY_BOUND" if not problems else "BLOCKED",
        "problems": sorted(set(problems)),
        "identity_sha256": identity.get("identity_sha256"),
        "apk_sha256": str(apk_sha256 or "").strip().lower(),
        "build_receipt_sha256": str(build_receipt_sha256 or "").strip().lower(),
        "same_apk_required_on_api35_api36": True,
        "automatic_installation": False,
        "production_verified": False,
    }
