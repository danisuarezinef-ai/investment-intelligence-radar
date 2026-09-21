from __future__ import annotations

from typing import Any

FORBIDDEN_UNATTENDED = {
    "automatic_installation", "automatic_publication", "automatic_promotion", "automatic_spending",
    "payments", "real_trading", "credential_export", "destructive_delete", "trust_root_replacement",
}
ALLOWED_BOUNDED = {
    "read_files", "write_sandbox", "run_tests", "run_benchmarks", "local_http_health", "browser_navigation",
    "terminal_bounded", "collect_evidence", "build_debug_artifact", "read_only_mobile_sync",
}


def qualify_authority_boundary_v2(requested: list[str] | tuple[str, ...] | set[str]) -> dict[str, Any]:
    normalized = sorted({str(x).strip() for x in requested if str(x).strip()})
    forbidden = sorted(set(normalized) & FORBIDDEN_UNATTENDED)
    unknown = sorted(set(normalized) - FORBIDDEN_UNATTENDED - ALLOWED_BOUNDED)
    return {
        "ok": not forbidden and not unknown,
        "status": "BOUNDED_AUTHORITY_OK" if not forbidden and not unknown else "BLOCKED",
        "requested": normalized,
        "forbidden_requested": forbidden,
        "unknown_requested": unknown,
        "human_approval_required_for_forbidden": True,
        "spending_authority": False,
        "publication_authority": False,
        "installation_authority": False,
        "real_trading_authority": False,
    }
