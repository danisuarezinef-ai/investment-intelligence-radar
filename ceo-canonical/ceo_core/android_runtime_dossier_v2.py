from __future__ import annotations

from typing import Any


def _sha(v: Any) -> bool:
    s = str(v or "").strip().lower()
    return len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def qualify_runtime_dossier_v2(api35: dict[str, Any], api36: dict[str, Any], *, expected_apk_sha256: str | None = None) -> dict[str, Any]:
    problems: list[str] = []
    rows = ((35, api35), (36, api36))
    for api, row in rows:
        if int(row.get("api") or 0) != api:
            problems.append(f"api{api}_identity_mismatch")
        if row.get("runtime_pass") is not True or row.get("status") != "RUNTIME_API_PASS":
            problems.append(f"api{api}_not_passed")
        if not _sha(row.get("debug_apk_sha256")):
            problems.append(f"api{api}_apk_hash_invalid")
        if row.get("production_verified") is True:
            problems.append(f"api{api}_production_overclaim")
    same = bool(api35.get("debug_apk_sha256")) and api35.get("debug_apk_sha256") == api36.get("debug_apk_sha256")
    if not same:
        problems.append("same_apk_requirement_failed")
    if expected_apk_sha256:
        if not _sha(expected_apk_sha256) or api35.get("debug_apk_sha256") != expected_apk_sha256:
            problems.append("expected_apk_identity_mismatch")
    accepted = not problems
    return {
        "ok": accepted,
        "status": "ANDROID_RUNTIME_ACCEPTED" if accepted else "ANDROID_RUNTIME_PENDING",
        "problems": sorted(set(problems)),
        "api35_pass": api35.get("runtime_pass") is True,
        "api36_pass": api36.get("runtime_pass") is True,
        "same_debug_apk": same,
        "debug_apk_sha256": api35.get("debug_apk_sha256") if accepted else None,
        "physical_phone_still_required": True,
        "production_verified": False,
        "automatic_publication": False,
    }
