from __future__ import annotations

from typing import Any, Iterable


SAFE_KINDS = {"summarize", "classify", "extract", "compare", "verify_text", "transform_json", "local_benchmark", "code_review"}


def plan_mobile_offload(
    tasks: Iterable[dict[str, Any]],
    telemetry: dict[str, Any],
    *,
    max_ram_fraction: float = 0.70,
) -> dict[str, Any]:
    """Plan safe phone compute without granting command or side-effect authority."""
    total_ram_gb = max(0.0, float(telemetry.get("ram_total_gb") or 0.0))
    free_ram_gb = max(0.0, float(telemetry.get("ram_free_gb") or 0.0))
    battery = float(telemetry.get("battery_percent") or 0.0)
    charging = bool(telemetry.get("charging", False))
    thermal = str(telemetry.get("thermal") or "normal").lower()
    available_cap = min(free_ram_gb, total_ram_gb * max(0.1, min(float(max_ram_fraction), 0.85)))
    admitted, deferred = [], []
    if thermal in {"hot", "critical"}:
        return {"admitted": [], "deferred": list(tasks), "reason": f"thermal_{thermal}", "ram_budget_gb": 0.0, **_safety()}
    if battery < 20 and not charging:
        return {"admitted": [], "deferred": list(tasks), "reason": "low_battery", "ram_budget_gb": 0.0, **_safety()}
    used = 0.0
    for task in tasks:
        row = dict(task); kind = str(row.get("kind") or "")
        need = max(0.05, float(row.get("estimated_ram_gb") or 0.25))
        if kind not in SAFE_KINDS:
            row["defer_reason"] = "unsafe_kind"; deferred.append(row); continue
        if used + need > available_cap:
            row["defer_reason"] = "ram_budget"; deferred.append(row); continue
        used += need; admitted.append(row)
    return {
        "admitted": admitted, "deferred": deferred, "reason": "capacity_planned",
        "ram_budget_gb": round(available_cap, 3), "ram_reserved_gb": round(used, 3),
        **_safety(),
    }


def _safety() -> dict[str, bool]:
    return {
        "arbitrary_shell_allowed": False,
        "publication_allowed": False,
        "installation_allowed": False,
        "spending_allowed": False,
        "credential_export_allowed": False,
        "destructive_actions_allowed": False,
    }
