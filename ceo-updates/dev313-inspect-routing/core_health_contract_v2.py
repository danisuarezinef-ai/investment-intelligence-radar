from __future__ import annotations

from typing import Any


def build_core_health_v2(*, version: str, activation_id: str | None, storage_ready: bool,
                         runtime_ready: bool, frontend_ready: bool, provider_mode: str,
                         execution_enabled: bool, provider_error: str | None = None,
                         provider_validation_in_progress: bool = False) -> dict[str, Any]:
    """Activation health is core-local; provider availability is reported separately."""
    core_ok = bool(storage_ready and runtime_ready and frontend_ready)
    provider_state = "ready" if execution_enabled else (
        "validating" if provider_validation_in_progress else (
            "degraded" if provider_error else "not_configured_or_unavailable"
        )
    )
    return {
        "ok": core_ok,
        "ready": core_ok,
        "core_health_ok": core_ok,
        "activation_health_ok": core_ok,
        "version": str(version),
        "activation_id": activation_id,
        "storage_ready": bool(storage_ready),
        "scheduler_component_ready": bool(runtime_ready),
        "frontend_ready": bool(frontend_ready),
        "provider": {
            "state": provider_state,
            "mode": str(provider_mode),
            "execution_enabled": bool(execution_enabled),
            "validation_in_progress": bool(provider_validation_in_progress),
            "error": str(provider_error)[:900] if provider_error else None,
            "required_for_activation_health": False,
        },
        # Backward-compatible fields consumed by the current UI.
        "provider_mode": str(provider_mode),
        "execution_enabled": bool(execution_enabled),
        "gemini_validation_error": str(provider_error)[:900] if provider_error else None,
    }
