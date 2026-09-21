from __future__ import annotations

from pathlib import Path
from typing import Any

from .update_state_audit_v1 import UpdateStateAuditV1


class DeadUpdateRecoveryV2:
    """Audit first, then invoke only the updater's fail-closed recovery primitive."""
    def __init__(self, updater: Any):
        self.updater = updater

    def recover(self, *, stale_after_seconds: float = 900.0) -> dict[str, Any]:
        before = UpdateStateAuditV1(self.updater.root).inspect(stale_after_seconds=stale_after_seconds)
        recovery = self.updater.recover_interrupted_update(stale_after_seconds=stale_after_seconds)
        after = UpdateStateAuditV1(self.updater.root).inspect(stale_after_seconds=stale_after_seconds)
        return {"before": before, "recovery": recovery, "after": after, "safe": bool(after.get("ok"))}
