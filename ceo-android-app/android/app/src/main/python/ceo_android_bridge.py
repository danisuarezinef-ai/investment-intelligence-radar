"""CEO Android bridge foundation. M02 does not execute embedded Python yet."""
from __future__ import annotations

def foundation_status() -> dict[str, object]:
    return {
        "schema_version": 1,
        "stage": "M02",
        "shared_core_execution_enabled": False,
        "physical_installation_allowed": False,
        "updater_activation_allowed": False,
    }

def execute_simple_task(_task: dict[str, object]) -> dict[str, object]:
    return {
        "ok": False,
        "status": "BLOCKED_UNTIL_M07",
        "detail": "Task execution is not activated during M02.",
    }
