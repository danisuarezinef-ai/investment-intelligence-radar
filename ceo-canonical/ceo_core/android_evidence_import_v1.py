from __future__ import annotations

from typing import Any

ALLOWED_STATUS = {"RUNTIME_HARDENING_HARNESS_READY", "ANDROID_RUNTIME_ACCEPTED"}
HASH_FIELDS = ("source_fingerprint", "sbom_sha256", "build_payload_sha256", "checkpoint_sha256")


def _sha256(value: Any) -> bool:
    s = str(value or "").strip().lower()
    return len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def validate_android_evidence_import_v1(evidence: dict[str, Any]) -> dict[str, Any]:
    problems: list[str] = []
    status = str(evidence.get("status") or "").strip()
    if status not in ALLOWED_STATUS:
        problems.append("status_invalid")

    hashes = {field: str(evidence.get(field) or "").strip().lower() for field in HASH_FIELDS}
    for field, digest in hashes.items():
        if not _sha256(digest):
            problems.append(field + "_invalid")

    source_tests = int(evidence.get("source_tests_passed") or 0)
    source_failures = int(evidence.get("source_tests_failed") or 0)
    if source_tests <= 0 or source_failures != 0:
        problems.append("source_regression_not_clean")

    api35 = evidence.get("runtime_api35_executed") is True
    api36 = evidence.get("runtime_api36_executed") is True
    runtime_accepted_claim = evidence.get("android_runtime_accepted") is True
    production_claim = evidence.get("production_verified") is True
    runtime_accepted = bool(status == "ANDROID_RUNTIME_ACCEPTED" and api35 and api36 and runtime_accepted_claim)

    if runtime_accepted_claim and not (api35 and api36 and status == "ANDROID_RUNTIME_ACCEPTED"):
        problems.append("runtime_acceptance_claim_without_dual_api_evidence")
    if production_claim and not runtime_accepted:
        problems.append("production_claim_without_runtime_acceptance")

    source_harness_ready = bool(not problems and status in ALLOWED_STATUS)
    return {
        "schema_version": 1,
        "ok": not problems,
        "problems": sorted(set(problems)),
        "status": status,
        "hashes": hashes,
        "source_tests_passed": source_tests,
        "source_tests_failed": source_failures,
        "source_harness_ready": source_harness_ready,
        "runtime_api35_executed": api35,
        "runtime_api36_executed": api36,
        "android_runtime_accepted": runtime_accepted,
        "production_verified": bool(production_claim and runtime_accepted),
        "side_effects_allowed": False,
    }
