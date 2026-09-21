from __future__ import annotations

from typing import Any

HASHES = ("source_fingerprint", "sbom_sha256", "build_payload_sha256", "checkpoint_sha256")


def _sha(v: Any) -> bool:
    s = str(v or "").strip().lower()
    return len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def qualify_android_build_readiness_v1(evidence: dict[str, Any]) -> dict[str, Any]:
    problems: list[str] = []
    for key in HASHES:
        if not _sha(evidence.get(key)):
            problems.append(key + "_invalid")
    tests = int(evidence.get("source_tests_passed") or 0)
    failed = int(evidence.get("source_tests_failed") or 0)
    if tests < 194 or failed:
        problems.append("source_regression_incomplete")
    if str(evidence.get("status") or "") != "RUNTIME_HARDENING_HARNESS_READY":
        problems.append("runtime_harness_not_ready")
    if evidence.get("runtime_api35_executed") is True or evidence.get("runtime_api36_executed") is True:
        problems.append("unexpected_runtime_claim_for_build_readiness")
    if evidence.get("android_runtime_accepted") is True or evidence.get("production_verified") is True:
        problems.append("runtime_or_production_overclaim")
    ready = not problems
    return {
        "schema_version": 1,
        "ok": ready,
        "status": "READY_FOR_FIRST_DEBUG_APK_BUILD" if ready else "BLOCKED",
        "problems": sorted(set(problems)),
        "source_tests_passed": tests,
        "build_payload_sha256": str(evidence.get("build_payload_sha256") or "").lower(),
        "requires_same_apk_sha256_on_api35_api36": True,
        "runtime_api35_executed": False,
        "runtime_api36_executed": False,
        "android_runtime_accepted": False,
        "production_verified": False,
        "automatic_installation": False,
        "manual_post_install_configuration_required": False,
    }
