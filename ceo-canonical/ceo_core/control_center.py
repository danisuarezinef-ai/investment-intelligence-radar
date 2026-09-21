from __future__ import annotations

from dataclasses import asdict

from .directors import ProjectDirector
from .eta_v2 import MonteCarloETAEngine
from .models import ProjectState, TaskStatus
from .project_map import ProjectMapBuilder


class ProjectControlCenter:
    """Produces the simple surface CEO's UI needs without exposing internal complexity."""
    def __init__(self) -> None:
        self.director = ProjectDirector()
        self.eta = MonteCarloETAEngine()
        self.map_builder = ProjectMapBuilder()

    def snapshot(self, state: ProjectState) -> dict:
        directors = self.director.rebuild(state)
        eta = asdict(self.eta.estimate(state, simulations=80))
        exceptions = []
        for t in state.leaf_tasks:
            if t.status in {TaskStatus.FAILED, TaskStatus.NEEDS_REVIEW, TaskStatus.BLOCKED}:
                exceptions.append({"task_id": t.id, "title": t.title, "status": t.status.value})
        return {
            "goal": {
                "title": state.goal, "definition": state.goal_definition,
                "success_definition": state.goal_success_definition,
                "deliverables": list(state.goal_deliverables),
                "deadline": state.deadline, "urgency": state.urgency,
                "progress": state.progress,
            },
            "controls": {
                "power_percent": state.power_percent,
                "autonomy_enabled": state.autonomy_enabled,
                "notifications_enabled": state.notifications_enabled,
                "verification_percent": state.verification_percent,
                "depth_percent": state.depth_percent,
                "exploration_percent": state.exploration_percent,
                "autonomy_level": state.metadata.get("autonomy_level", "balanced"),
                "resource_preset": state.metadata.get("resource_preset", "custom"),
            },
            "scheduler": {"eta": eta, "absence_mode": state.absence_mode, "paused": state.paused},
            "activity": state.metadata.get("activity_snapshot", {}),
            "budget": state.metadata.get("budget_snapshot", {}),
            "directors": directors,
            "decisions": [d.model_dump(mode="json") for d in state.decisions.values() if d.status.value == "open"],
            "exceptions": exceptions[:100],
            "project_map": self.map_builder.build(state),
            "strategic_v07": state.metadata.get("strategic_loop_v07", {"enabled": False}),
            "browser_session_health": state.metadata.get("browser_session_health", {}),
            "distributed_nodes": state.metadata.get("nodes", {}),
            "retrospective": state.metadata.get("autonomous_retrospective"),
            "continuity": state.metadata.get("continuity_snapshot", {}),
        }
