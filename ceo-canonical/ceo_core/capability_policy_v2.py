from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from .models import ProjectState, Task


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class CapabilityDecision:
    allowed: bool
    sensitive: list[str]
    reason: str
    checked_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CapabilityPolicyV2:
    """Least-privilege policy for task dispatch. Safe compute defaults to allowed."""

    KEY = "capability_policy_v2"
    SENSITIVE = {
        "spending", "payment", "purchase", "publication", "git_push", "remote_publish",
        "destructive", "delete", "external_write", "install", "credential_change", "auth_change",
        "account_change", "trade_real", "real_trading",
    }

    def assess(self, state: ProjectState, task: Task) -> CapabilityDecision:
        declared = {str(x).strip().lower() for x in task.required_capabilities if str(x).strip()}
        action_class = str(task.metadata.get("action_class") or "").strip().lower()
        if action_class:
            declared.add(action_class)
        sensitive = sorted(x for x in declared if x in self.SENSITIVE)
        approval = task.metadata.get("human_gate_approved") is True
        allowed = not sensitive or approval
        reason = "safe_capabilities" if not sensitive else ("explicit_human_gate_approval" if approval else "sensitive_capability_requires_human_gate")
        row = CapabilityDecision(allowed, sensitive, reason, _now())
        task.metadata["capability_policy"] = row.to_dict()
        state.metadata.setdefault("capability_policy_events_v2", []).append({"task_id": task.id, **row.to_dict()})
        del state.metadata["capability_policy_events_v2"][:-1000]
        return row
