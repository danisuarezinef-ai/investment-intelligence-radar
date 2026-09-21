from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    WAITING = "waiting"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    NEEDS_REVIEW = "needs_review"
    RETRY = "retry"
    FAILED = "failed"
    COMPLETE = "complete"
    PARTIAL_COMPLETE = "partial_complete"
    COMPLETE_WITH_UNCERTAINTY = "complete_with_uncertainty"
    SUPERSEDED = "superseded"


class DecisionStatus(str, Enum):
    OPEN = "open"
    AUTO_RESOLVED = "auto_resolved"
    USER_RESOLVED = "user_resolved"


class Task(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str
    description: str = ""
    parent_id: str | None = None
    depth: int = 0
    priority: int = 50
    status: TaskStatus = TaskStatus.WAITING
    dependencies: list[str] = Field(default_factory=list)
    children: list[str] = Field(default_factory=list)
    estimated_seconds: float = 2.0
    actual_seconds: float | None = None
    worker_id: str | None = None
    provider_name: str | None = None
    conversation_id: str | None = None
    conversation_turns: int = 0
    required_capabilities: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    attempts: int = 0
    max_attempts: int = 3
    result: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    cost_estimate: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class Decision(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str
    description: str
    options: list[str]
    recommendation: str | None = None
    confidence: float | None = None
    timeout_seconds: int = 60
    status: DecisionStatus = DecisionStatus.OPEN
    selected: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class ProjectState(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    project_name: str = ""
    goal: str = ""
    goal_definition: str = ""
    goal_success_definition: str = ""
    completion_criteria: list[str] = Field(default_factory=list)
    goal_constraints: list[str] = Field(default_factory=list)
    goal_deliverables: list[str] = Field(default_factory=list)
    deadline: str | None = None
    urgency: int = Field(default=50, ge=1, le=100)
    archived: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    tasks: dict[str, Task] = Field(default_factory=dict)
    root_task_ids: list[str] = Field(default_factory=list)
    decisions: dict[str, Decision] = Field(default_factory=dict)
    power_percent: int = 30
    autonomy_enabled: bool = True
    notifications_enabled: bool = True
    verification_percent: int = 50
    exploration_percent: int = 35
    depth_percent: int = 60
    budget_limit: float | None = None
    priority_mode: str = "balanced"
    absence_mode: bool = False
    schema_version: int = 3
    human_interventions_avoided: int = 0
    human_interventions_required: int = 0
    paused: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancelled_reason: str | None = None
    created_at: datetime = Field(default_factory=utcnow)

    @property
    def leaf_tasks(self) -> list[Task]:
        return [t for t in self.tasks.values() if not t.children]

    @property
    def completed_leaf_tasks(self) -> list[Task]:
        return [t for t in self.leaf_tasks if t.status == TaskStatus.COMPLETE]

    @property
    def progress(self) -> float:
        leaves = self.leaf_tasks
        if not leaves:
            return 0.0
        return round(100 * len(self.completed_leaf_tasks) / len(leaves), 1)
