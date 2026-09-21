from __future__ import annotations

from typing import Any

SENSITIVE = {
    "spending", "payment", "purchase", "publication", "git_push", "remote_publish", "destructive", "delete",
    "external_write", "install", "credential_change", "auth_change", "account_change", "trade_real", "real_trading",
    "credential_export", "arbitrary_shell", "auto_promote", "auto_publish", "auto_install",
}


def compare_capability_manifests_v1(baseline: list[str], candidate: list[str]) -> dict[str, Any]:
    base = {str(x).strip().lower() for x in baseline if str(x).strip()}
    cand = {str(x).strip().lower() for x in candidate if str(x).strip()}
    added = sorted(cand - base)
    removed = sorted(base - cand)
    sensitive_added = sorted(set(added) & SENSITIVE)
    return {
        "schema_version": 1,
        "ok": not sensitive_added,
        "added": added,
        "removed": removed,
        "sensitive_added": sensitive_added,
        "human_review_required": bool(sensitive_added),
        "automatic_grant_allowed": False,
        "baseline_count": len(base),
        "candidate_count": len(cand),
    }
