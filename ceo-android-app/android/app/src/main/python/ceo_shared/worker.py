from __future__ import annotations
from typing import Any

def run_task(task: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "status": "BLOCKED_UNTIL_M07", "task": dict(task)}
