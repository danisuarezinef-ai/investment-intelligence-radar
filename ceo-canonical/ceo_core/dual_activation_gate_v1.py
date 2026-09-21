from __future__ import annotations
from typing import Any


def evaluate_dual_activation_gate_v1(*, core_health: dict[str, Any] | None,
                                     productive_smoke: dict[str, Any] | None,
                                     provider_status: dict[str, Any] | None = None) -> dict[str, Any]:
    core_ok = bool((core_health or {}).get("ok"))
    productive_ok = bool((productive_smoke or {}).get("ok"))
    provider_ok = bool((provider_status or {}).get("ok")) if provider_status is not None else None
    return {
        "ok": core_ok and productive_ok,
        "core_health": core_ok,
        "productive_smoke": productive_ok,
        "provider_available": provider_ok,
        "provider_required": False,
        "commit_activation": core_ok and productive_ok,
        "rollback_required": not (core_ok and productive_ok),
    }
