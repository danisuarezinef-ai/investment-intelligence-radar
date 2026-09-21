from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from .models import ProjectState, TaskStatus
from .continuity_policy import is_internal_continuity_task, protected_human_gate
from .task_roles_v2 import is_productive


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class MissionSnapshot:
    phase: str
    productive_open: int
    running: int
    blocked: int
    retrying: int
    needs_review: int
    completed: int
    progress: float
    action: str
    digest: str
    stalled_cycles: int
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MissionSupervisorV2:
    """Long-horizon supervisor that keeps mission state explicit and restart durable.

    It never resolves human gates itself. Its job is to identify whether the mission can
    continue, is paused, has only dependency trouble, or has reached a terminal state.
    """

    KEY = "mission_supervisor_v2"

    @staticmethod
    def _productive(state: ProjectState):
        for task in state.leaf_tasks:
            if is_productive(task, state):
                yield task

    def tick(self, state: ProjectState) -> MissionSnapshot:
        tasks = list(self._productive(state))
        counts = {status.value: 0 for status in TaskStatus}
        for task in tasks:
            counts[task.status.value] = counts.get(task.status.value, 0) + 1
        terminal = {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.SUPERSEDED, TaskStatus.FAILED}
        open_tasks = [t for t in tasks if t.status not in terminal]
        if state.completed_at is not None or (tasks and not open_tasks and bool(state.metadata.get("goal_audit_passed"))):
            phase, action = "complete", "none"
        elif state.paused:
            phase, action = "paused", "wait_for_operator"
        elif any(
            t.status == TaskStatus.NEEDS_REVIEW and (not is_internal_continuity_task(state, t) or protected_human_gate(t))
            for t in open_tasks
        ) and not any(t.status in {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.RETRY} for t in open_tasks):
            phase, action = "human_gate", "wait_for_operator"
        elif open_tasks and all(t.status == TaskStatus.BLOCKED for t in open_tasks):
            phase, action = "dependency_recovery", "reconcile_dependencies"
        elif any(t.status == TaskStatus.RUNNING for t in open_tasks):
            phase, action = "execution", "continue"
        elif open_tasks:
            phase, action = "planning", "dispatch_or_replan"
        else:
            phase, action = "continuity", "ensure_progress"

        digest_src = "|".join(f"{t.id}:{t.status.value}:{t.attempts}" for t in sorted(tasks, key=lambda x: x.id))
        digest = sha256(digest_src.encode()).hexdigest()[:20]
        meta = state.metadata.setdefault(self.KEY, {})
        previous = meta.get("last_digest")
        stalled = int(meta.get("stalled_cycles", 0) or 0) + 1 if previous == digest and phase not in {"paused", "human_gate", "complete"} else 0
        snap = MissionSnapshot(
            phase=phase,
            productive_open=len(open_tasks),
            running=counts.get(TaskStatus.RUNNING.value, 0),
            blocked=counts.get(TaskStatus.BLOCKED.value, 0),
            retrying=counts.get(TaskStatus.RETRY.value, 0),
            needs_review=counts.get(TaskStatus.NEEDS_REVIEW.value, 0),
            completed=sum(counts.get(x.value, 0) for x in (TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY)),
            progress=float(state.progress),
            action=action,
            digest=digest,
            stalled_cycles=stalled,
            updated_at=_now(),
        )
        meta.update(snap.to_dict())
        meta["last_digest"] = digest
        meta["history"] = (list(meta.get("history", [])) + [{"ts": snap.updated_at, "phase": phase, "action": action, "progress": snap.progress}])[-200:]
        return snap
