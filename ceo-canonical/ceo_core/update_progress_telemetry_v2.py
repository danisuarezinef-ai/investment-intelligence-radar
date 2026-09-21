from __future__ import annotations

from typing import Any

_PHASES = {
    "download": (1, 10, "download"), "downloading": (1, 10, "download"),
    "verify": (2, 10, "verify"), "verifying": (2, 10, "verify"),
    "stage": (3, 10, "stage"), "staged": (4, 10, "stage_complete"),
    "preflight": (5, 10, "preflight"), "preflight_ok": (6, 10, "preflight_complete"),
    "activating": (7, 10, "activate_pointer"), "waiting_old_process": (7, 10, "wait_old_process"),
    "launching_new_version": (8, 10, "launch_candidate"), "health_check": (9, 10, "activation_health"),
    "healthy": (10, 10, "complete"), "rollback": (9, 10, "rollback"), "rolled_back": (10, 10, "rolled_back"),
    "preflight_failed": (10, 10, "blocked_before_activation"),
}


def enrich_update_progress_v2(phase: str, fields: dict[str, Any]) -> dict[str, Any]:
    current, total, label = _PHASES.get(str(phase).lower(), (0, 10, str(phase)))
    percent = fields.get("percent")
    if percent is None:
        percent = round((current / total) * 100) if current else 0
    return {
        **fields,
        "phase_index": current,
        "phase_total": total,
        "phase_label": label,
        "percent": int(max(0, min(100, float(percent)))),
        "terminal": str(phase).lower() in {"healthy", "rolled_back", "preflight_failed"},
    }
