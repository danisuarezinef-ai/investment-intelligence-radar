from __future__ import annotations

from typing import Any, Iterable


SUITES = {
    "core": ("tests/core", "scripts/static_check.py", "scripts/security_audit.py"),
    "persistence": ("tests/persistence",),
    "scheduler": ("tests/scheduler",),
    "updater": ("tests/updater", "scripts/update_candidate_preflight.py"),
    "security": ("tests/security", "scripts/security_audit.py"),
    "mobile": ("tests/mobile",),
    "android": ("tests/android_contract",),
    "ui": ("tests/ui",),
    "full": ("FULL_REGRESSION",),
}


def select_regression_scope(changed_files: Iterable[str]) -> dict[str, Any]:
    paths = sorted({str(p).replace("\\", "/").lstrip("./") for p in changed_files if str(p).strip()})
    domains: set[str] = {"core"}
    high_risk = False
    reasons: list[str] = []
    for p in paths:
        q = p.lower()
        if any(x in q for x in ("update", "release", "bootstrap", "relaunch", "launch_current", "credential", "security_", "capability_policy", "update_trust")):
            domains.update({"updater", "security", "full"}); high_risk = True; reasons.append(f"release_or_security:{p}")
        if any(x in q for x in ("scheduler", "routing", "worker", "mission")):
            domains.add("scheduler")
        if any(x in q for x in ("sqlite", "store", "checkpoint", "memory")):
            domains.add("persistence")
        if "mobile" in q or "remote" in q or "sync" in q:
            domains.add("mobile")
        if "android" in q:
            domains.add("android")
        if p.startswith("scripts/ceo_stdlib_work_mode") or p.startswith("ceo_app/"):
            domains.add("ui")
    suites = sorted({suite for domain in domains for suite in SUITES[domain]})
    return {
        "schema_version": 2,
        "changed_files": paths,
        "domains": sorted(domains),
        "required_suites": suites,
        "full_regression_required": high_risk,
        "high_risk_reasons": sorted(set(reasons)),
        "test_omission_allowed": False if high_risk else True,
        "automatic_promotion": False,
    }
