from __future__ import annotations

from .models import ProjectState


class AbsenceMode:
    def enter(self, state: ProjectState) -> None:
        state.metadata.setdefault("pre_absence", {"power_percent": state.power_percent, "autonomy_enabled": state.autonomy_enabled})
        state.absence_mode = True
        state.autonomy_enabled = True
        state.power_percent = max(state.power_percent, int(state.metadata.get("absence_power", 90)))

    def leave(self, state: ProjectState) -> dict:
        before = state.metadata.pop("pre_absence", {})
        state.power_percent = int(before.get("power_percent", state.power_percent))
        state.autonomy_enabled = bool(before.get("autonomy_enabled", state.autonomy_enabled))
        state.absence_mode = False
        return self.return_report(state)

    def return_report(self, state: ProjectState) -> dict:
        return {
            "progress": state.progress,
            "completed": len(state.completed_leaf_tasks),
            "decisions": len(state.decisions),
            "problems": len([t for t in state.leaf_tasks if t.status.value in {"failed", "needs_review"}]),
            "remaining": len([t for t in state.leaf_tasks if t.status.value not in {"complete", "superseded"}]),
        }
