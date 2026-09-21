from __future__ import annotations

from datetime import datetime, timezone
from hashlib import blake2b
import json
from typing import Any

from .models import DecisionStatus, ProjectState, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


TERMINAL = {
    TaskStatus.COMPLETE,
    TaskStatus.PARTIAL_COMPLETE,
    TaskStatus.COMPLETE_WITH_UNCERTAINTY,
    TaskStatus.SUPERSEDED,
}


class ContinuityManager:
    """Builds the minimum durable context needed to resume a project exactly.

    The continuity snapshot is intentionally compact and JSON-safe. It complements the
    full SQLite checkpoint rather than replacing it: the database stores every task,
    while this snapshot answers the operational question "where were we and what is next?".
    """

    def capture(self, state: ProjectState, *, reason: str = "checkpoint") -> dict[str, Any]:
        active = []
        next_tasks = []
        problems = []
        recent_results = []

        leaves = list(state.leaf_tasks)
        for task in leaves:
            if task.status == TaskStatus.RUNNING:
                active.append(self._task_row(task))
            elif task.status in {TaskStatus.READY, TaskStatus.RETRY}:
                next_tasks.append(self._task_row(task))
            elif task.status in {TaskStatus.FAILED, TaskStatus.NEEDS_REVIEW, TaskStatus.BLOCKED}:
                problems.append(self._task_row(task))

        next_tasks.sort(key=lambda row: (-int(row.get("priority", 0)), str(row.get("created_at", ""))))
        result_order = list(state.metadata.get("result_order", []))[-10:]
        for task_id in reversed(result_order):
            task = state.tasks.get(str(task_id))
            if task and task.result:
                recent_results.append({
                    "task_id": task.id,
                    "title": task.title,
                    "status": task.status.value,
                    "provider": task.provider_name,
                    "result_excerpt": task.result[:500],
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                })

        decisions = []
        for decision in state.decisions.values():
            if decision.status == DecisionStatus.OPEN:
                decisions.append({
                    "id": decision.id,
                    "title": decision.title,
                    "recommendation": decision.recommendation,
                    "options": list(decision.options),
                    "autonomy_class": decision.metadata.get("autonomy_class"),
                })

        artifacts: list[str] = []
        for task in state.tasks.values():
            for artifact in task.metadata.get("artifacts", []):
                text = str(artifact)
                if text and text not in artifacts:
                    artifacts.append(text)

        status = "completed" if state.completed_at else "paused" if state.paused else "working"
        snapshot: dict[str, Any] = {
            "schema": 1,
            "captured_at": _now(),
            "reason": reason,
            "project_id": state.id,
            "project_name": state.project_name or state.goal[:80],
            "goal": state.goal,
            "status": status,
            "progress": state.progress,
            "active": active[:20],
            "next": next_tasks[:20],
            "open_decisions": decisions[:20],
            "problems": problems[:20],
            "recent_results": recent_results[:10],
            "artifacts": artifacts[-50:],
            "last_plan_revision": state.metadata.get("replanning", {}).get("last_revision"),
            "activity": state.metadata.get("activity_snapshot", {}),
            "budget": state.metadata.get("budget_snapshot", {}),
            "resource_preset": state.metadata.get("resource_preset", "custom"),
            "autonomy_level": state.metadata.get("autonomy_level", "balanced"),
            "resume_count": int(state.metadata.get("resume_count", 0)),
            "last_resumed_at": state.metadata.get("last_resumed_at"),
        }
        stable = dict(snapshot)
        stable.pop("captured_at", None)
        stable.pop("reason", None)
        snapshot["digest"] = blake2b(
            json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"),
            digest_size=12,
        ).hexdigest()
        state.metadata["continuity_snapshot"] = snapshot
        return snapshot

    def mark_resume(self, state: ProjectState, *, source: str = "restart") -> dict[str, Any]:
        state.metadata["resume_count"] = int(state.metadata.get("resume_count", 0)) + 1
        state.metadata["last_resumed_at"] = _now()
        state.metadata["last_resume_source"] = source
        return self.capture(state, reason=f"resume:{source}")

    def next_action_text(self, state: ProjectState) -> str:
        snap = self.capture(state, reason="next_action")
        if snap["problems"]:
            return f"Resolver: {snap['problems'][0]['title']}"
        if snap["active"]:
            return f"Continuar: {snap['active'][0]['title']}"
        if snap["next"]:
            return f"Ejecutar: {snap['next'][0]['title']}"
        if state.completed_at:
            return "Proyecto completado"
        return "Reevaluar el plan y generar el siguiente trabajo ejecutable"

    @staticmethod
    def _task_row(task) -> dict[str, Any]:
        return {
            "task_id": task.id,
            "title": task.title,
            "status": task.status.value,
            "priority": task.priority,
            "provider": task.provider_name,
            "stage": task.metadata.get("provider_stage"),
            "attempts": task.attempts,
            "created_at": task.created_at.isoformat(),
            "last_error": task.metadata.get("last_provider_error") or (task.result if task.status == TaskStatus.FAILED else None),
        }
