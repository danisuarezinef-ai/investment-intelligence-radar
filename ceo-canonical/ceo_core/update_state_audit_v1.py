from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


class UpdateStateAuditV1:
    def __init__(self, updates_root: str | Path):
        self.root = Path(updates_root)

    def inspect(self, *, stale_after_seconds: float = 900.0) -> dict[str, Any]:
        now = time.time()
        current = _load(self.root / "current.json")
        previous = _load(self.root / "previous.json")
        operation = _load(self.root / "operation.json")
        progress = _load(self.root / "progress.json")
        restart = _load(self.root / "restart-progress.json")
        lock = _load(self.root / "update.lock")
        problems: list[str] = []
        pending = str(current.get("status") or "") == "pending_health"
        activated_at = float(current.get("activated_at_epoch") or 0.0)
        pending_age = max(0.0, now - activated_at) if pending and activated_at else None
        if pending and pending_age is not None and pending_age >= stale_after_seconds:
            problems.append("stale_pending_health")
        if pending and previous and not Path(str(previous.get("root") or "")).is_dir():
            problems.append("previous_pointer_root_missing")
        if current and current.get("root") and not Path(str(current.get("root"))).is_dir():
            problems.append("current_pointer_root_missing")
        op_age = now - float(operation.get("updated_at_epoch") or now) if operation else 0.0
        if operation and op_age >= stale_after_seconds:
            problems.append("stale_operation")
        lock_age = now - float(lock.get("created_at_epoch") or now) if lock else 0.0
        if lock and lock_age >= stale_after_seconds:
            problems.append("stale_lock")
        newest = max((float(progress.get("updated_at_epoch") or 0), float(restart.get("updated_at_epoch") or 0)))
        dry_seconds = max(0.0, now - newest) if newest else None
        return {
            "ok": not problems,
            "pending_health": pending,
            "pending_age_seconds": pending_age,
            "operation_age_seconds": op_age if operation else None,
            "lock_age_seconds": lock_age if lock else None,
            "progress_dry_seconds": dry_seconds,
            "problems": problems,
            "recommended_action": "recover_interrupted_update" if problems else "none",
            "phase": str((restart if float(restart.get("updated_at_epoch") or 0) >= float(progress.get("updated_at_epoch") or 0) else progress).get("phase") or "idle"),
        }
