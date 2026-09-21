from __future__ import annotations

from typing import Any

REQUIRED_LOCK = {
    "jdk": "17",
    "gradle": "9.4.1",
    "android_gradle_plugin": "9.2.1",
    "compile_sdk": 37,
    "target_sdk": 37,
    "min_sdk": 26,
    "chaquopy": "17.0.0",
    "python_runtime": "3.13",
    "kotlin_compose_plugin": "2.3.21",
}


def _sha(v: Any) -> bool:
    s = str(v or "").strip().lower()
    return len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def qualify_android_build_inputs_v1(lock: dict[str, Any], manifest: dict[str, Any], *, expected_payload_sha256: str) -> dict[str, Any]:
    problems: list[str] = []
    for key, expected in REQUIRED_LOCK.items():
        if lock.get(key) != expected:
            problems.append(f"toolchain_{key}_mismatch")
    apis = list(lock.get("ci_emulator_api_levels") or [])
    if apis != [35, 36]:
        problems.append("runtime_api_matrix_mismatch")
    if sorted(lock.get("abis") or []) != ["arm64-v8a", "x86_64"]:
        problems.append("abi_matrix_mismatch")
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    if len(files) != 45:
        problems.append("build_payload_file_count_mismatch")
    paths = set()
    for row in files:
        path = str(row.get("path") or "")
        if not path or path in paths:
            problems.append("manifest_path_invalid_or_duplicate")
        paths.add(path)
        if not _sha(row.get("sha256")):
            problems.append("manifest_file_hash_invalid")
        if int(row.get("size") or -1) < 0:
            problems.append("manifest_file_size_invalid")
    if not _sha(manifest.get("minimal_source_sha256")):
        problems.append("minimal_source_sha256_invalid")
    if not _sha(expected_payload_sha256):
        problems.append("expected_payload_sha256_invalid")
    if manifest.get("production_verified") is True:
        problems.append("production_overclaim")
    return {
        "ok": not problems,
        "status": "READY_FOR_DUAL_DEBUG_BUILD" if not problems else "BLOCKED",
        "problems": sorted(set(problems)),
        "input_files": len(files),
        "expected_payload_sha256": str(expected_payload_sha256 or "").lower(),
        "minimal_source_sha256": str(manifest.get("minimal_source_sha256") or "").lower(),
        "toolchain_pinned": not any(p.startswith("toolchain_") for p in problems),
        "requires_two_clean_builds": True,
        "apk_built": False,
        "reproducibility_verified": False,
        "production_verified": False,
    }


def compare_debug_build_receipts_v1(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    problems: list[str] = []
    for label, row in (("first", first), ("second", second)):
        if str(row.get("status") or "") != "DEBUG_APK_BUILT":
            problems.append(label + "_build_not_complete")
        if not _sha(row.get("apk_sha256")):
            problems.append(label + "_apk_sha256_invalid")
        if not _sha(row.get("input_identity_sha256")):
            problems.append(label + "_input_identity_invalid")
    if not problems:
        if first.get("input_identity_sha256") != second.get("input_identity_sha256"):
            problems.append("input_identity_mismatch")
        if first.get("apk_sha256") != second.get("apk_sha256"):
            problems.append("apk_sha256_mismatch")
    return {
        "ok": not problems,
        "status": "DEBUG_APK_REPRODUCIBLE" if not problems else "NOT_REPRODUCIBLE_OR_INCOMPLETE",
        "problems": sorted(set(problems)),
        "apk_sha256": first.get("apk_sha256") if not problems else None,
        "reproducibility_verified": not problems,
        "production_verified": False,
    }
