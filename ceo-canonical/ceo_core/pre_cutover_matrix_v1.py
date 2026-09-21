from __future__ import annotations
from typing import Any

REQUIRED = (
    "runtime_gate", "candidate_identity", "admission_seal", "isolated_staging",
    "isolated_preflight", "recovery_point", "core_health", "productive_smoke",
)


def build_pre_cutover_matrix_v1(checks: dict[str, bool], *, provider_available: bool | None = None) -> dict[str, Any]:
    normalized = {name: bool(checks.get(name, False)) for name in REQUIRED}
    blocking_failures = [name for name, ok in normalized.items() if not ok]
    return {
        "schema_version": 1,
        "checks": normalized,
        "blocking_failures": blocking_failures,
        "provider_available": provider_available,
        "provider_is_activation_gate": False,
        "ready_for_human_cutover": not blocking_failures,
        "automatic_cutover": False,
        "human_confirmation_required": True,
    }
