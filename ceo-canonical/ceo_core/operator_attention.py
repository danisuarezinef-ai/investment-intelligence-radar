from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import DecisionStatus, ProjectState, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OperatorAttentionBroker:
    """Surfaces only real human gates and supports explicit decision actions."""

    ACTIONS = {"approve", "reject", "postpone"}

    def cards(self, state: ProjectState, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = []
        for decision in state.decisions.values():
            if decision.status != DecisionStatus.OPEN:
                continue
            # Internal continuity/control-plane decisions are intentionally hidden.
            if decision.metadata.get("autonomy_class") != "critical" and decision.metadata.get("internal_control_plane"):
                continue
            rows.append({
                "kind": "decision", "id": decision.id, "title": decision.title,
                "body": decision.description, "options": list(decision.options),
                "recommendation": decision.recommendation,
                "critical": decision.metadata.get("autonomy_class") == "critical",
                "created_at": decision.created_at.isoformat(),
                "actions": ["approve", "reject", "postpone"],
            })
        for task in state.leaf_tasks:
            if task.status != TaskStatus.NEEDS_REVIEW or not task.metadata.get("explicit_human_gate"):
                continue
            rows.append({
                "kind": "task_gate", "id": task.id, "title": task.title,
                "body": str(task.result or task.metadata.get("last_provider_error") or "Human confirmation required")[:1000],
                "critical": True, "created_at": task.created_at.isoformat(),
                "actions": ["approve", "reject", "postpone"],
            })
        rows.sort(key=lambda x: x.get("created_at", ""))
        return rows[:limit]

    def act(self, state: ProjectState, item_id: str, action: str, *, selection: str | None = None) -> dict[str, Any]:
        action = str(action).lower().strip()
        if action not in self.ACTIONS:
            raise ValueError("Unsupported attention action")
        if item_id in state.decisions:
            d = state.decisions[item_id]
            if d.status != DecisionStatus.OPEN:
                return {"changed": False, "reason": "decision already resolved"}
            if action == "postpone":
                d.metadata["postponed_at"] = _now()
                d.timeout_seconds = max(int(d.timeout_seconds), 3600)
                return {"changed": True, "status": "postponed"}
            if action == "approve":
                selected = selection or d.recommendation or (d.options[0] if d.options else None)
            else:
                alternatives = [x for x in d.options if x != d.recommendation]
                selected = selection or (alternatives[0] if alternatives else "rejected")
            d.selected = selected
            d.status = DecisionStatus.USER_RESOLVED
            d.metadata["resolved_by"] = "human"
            d.metadata["resolved_at"] = _now()
            for task in state.tasks.values():
                if task.metadata.get("decision_id") == d.id and task.status == TaskStatus.NEEDS_REVIEW:
                    if action == "approve":
                        task.status = TaskStatus.READY
                        task.metadata["next_instruction"] = f"Proceed with human-approved decision: {selected}"
                    else:
                        task.status = TaskStatus.FAILED
                        task.result = "Human rejected the gated action."
            state.human_interventions_required += 1
            return {"changed": True, "status": "resolved", "selected": selected}
        task = state.tasks.get(item_id)
        if task is None or task.status != TaskStatus.NEEDS_REVIEW or not task.metadata.get("explicit_human_gate"):
            raise KeyError(item_id)
        if action == "postpone":
            task.metadata["human_gate_postponed_at"] = _now()
            return {"changed": True, "status": "postponed"}
        if action == "approve":
            task.metadata["human_gate_approved_at"] = _now()
            task.metadata["explicit_human_gate"] = False
            task.metadata["next_instruction"] = "Proceed once with explicit human approval for this gated task."
            task.status = TaskStatus.READY
            state.human_interventions_required += 1
            return {"changed": True, "status": "approved"}
        task.metadata["human_gate_rejected_at"] = _now()
        task.status = TaskStatus.FAILED
        task.result = "Human rejected the gated action."
        state.human_interventions_required += 1
        return {"changed": True, "status": "rejected"}
