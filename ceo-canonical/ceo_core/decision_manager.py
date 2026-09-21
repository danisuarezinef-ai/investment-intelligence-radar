from __future__ import annotations

from datetime import datetime, timezone

from ceo_core.models import DecisionStatus, ProjectState, TaskStatus
from ceo_core.continuity_policy import recover_internal_continuity_decisions


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DecisionManager:
    """Resolves timed user decisions automatically so non-critical work never stalls forever."""

    def tick(self, state: ProjectState) -> int:
        if not state.autonomy_enabled:
            return 0
        resolved = recover_internal_continuity_decisions(state)
        now = utcnow()
        for decision in state.decisions.values():
            if decision.status != DecisionStatus.OPEN:
                continue
            if decision.metadata.get("autonomy_class") == "critical":
                # Critical/irreversible choices never auto-resolve by timeout.
                continue
            dependency = decision.metadata.get("depends_on_decision")
            if dependency and dependency in state.decisions and state.decisions[dependency].status == DecisionStatus.OPEN:
                continue
            elapsed = (now - decision.created_at).total_seconds()
            if elapsed < decision.timeout_seconds:
                continue
            selected = decision.recommendation or (decision.options[0] if decision.options else None)
            if not selected:
                continue
            decision.selected = selected
            decision.status = DecisionStatus.AUTO_RESOLVED
            for task in state.tasks.values():
                if task.metadata.get("decision_id") == decision.id and task.status == TaskStatus.NEEDS_REVIEW:
                    task.metadata["next_instruction"] = f"Proceed using the automatically selected decision: {selected}"
                    task.status = TaskStatus.READY
            state.human_interventions_avoided += 1
            state.metadata.setdefault("decision_history", []).append({"id":decision.id,"selected":selected,"source":"auto","recommendation":decision.recommendation})
            resolved += 1
        return resolved
