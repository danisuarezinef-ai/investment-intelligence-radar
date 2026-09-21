from __future__ import annotations

from enum import Enum

from .models import ProjectState, Task


class TaskRole(str, Enum):
    PRODUCTIVE = "productive"
    CONTROL = "control"
    VERIFICATION = "verification"
    HUMAN_GATE = "human_gate"


def task_role(task: Task, state: ProjectState | None = None) -> TaskRole:
    """Single source of truth for operator/scheduler task semantics.

    Explicit metadata wins. Legacy tasks are inferred conservatively so persisted
    projects created by DEV15-DEV191 can be upgraded without being recreated.
    """
    md = task.metadata or {}
    explicit = str(md.get("task_role") or "").strip().lower()
    if explicit in {r.value for r in TaskRole}:
        return TaskRole(explicit)

    if md.get("explicit_human_gate") or md.get("human_only") or md.get("requires_explicit_human"):
        return TaskRole.HUMAN_GATE

    title = str(task.title or "")
    if md.get("verification_task") or md.get("independently_verifies") or title.startswith("Independent verification"):
        return TaskRole.VERIFICATION

    if md.get("continuity_gap_recovery"):
        # DEV189 fallback batches contain three different semantic roles. The middle
        # execution step is real domain work; map/audit steps are control/verification.
        kind = str(md.get("task_kind") or "").lower()
        if md.get("productive_recovery_work") or kind in {"general", "implementation", "execution"}:
            return TaskRole.PRODUCTIVE
        if kind in {"code_review", "verification", "review"} or "verify" in title.lower():
            return TaskRole.VERIFICATION
        return TaskRole.CONTROL

    if any(bool(md.get(k)) for k in (
        "goal_continuity_audit", "autonomy_recovery", "control_plane_atomic",
        "continuity_control", "controller_internal", "recovery_wrapper",
    )):
        return TaskRole.CONTROL

    if title.startswith("Goal continuity audit #") or title.startswith("Autonomous recovery") or title.startswith("Retry blocked work"):
        return TaskRole.CONTROL

    return TaskRole.PRODUCTIVE


def is_productive(task: Task, state: ProjectState | None = None) -> bool:
    return task_role(task, state) == TaskRole.PRODUCTIVE


def is_control(task: Task, state: ProjectState | None = None) -> bool:
    return task_role(task, state) == TaskRole.CONTROL


def is_verification(task: Task, state: ProjectState | None = None) -> bool:
    return task_role(task, state) == TaskRole.VERIFICATION


def is_internal(task: Task, state: ProjectState | None = None) -> bool:
    return task_role(task, state) in {TaskRole.CONTROL, TaskRole.VERIFICATION}
