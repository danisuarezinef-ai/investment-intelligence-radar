from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .models import ProjectState, Task


class WorkerKind(str, Enum):
    """Execution surface used by a worker provider."""

    API = "api"
    BROWSER = "browser"
    LOCAL = "local"
    FILE = "file"
    MOCK = "mock"


class ControllerAction(str, Enum):
    """Stable actions the Conversation Controller can request from the scheduler."""

    COMPLETE = "complete"
    CONTINUE = "continue"
    CORRECT = "correct"
    DEEPEN = "deepen"
    SPAWN = "spawn"
    REVIEW = "review"
    ESCALATE = "escalate"
    RETRY = "retry"


class GoalContract(BaseModel):
    """Locked description of what the project must achieve before autonomous work starts."""

    objective: str = Field(min_length=1)
    definition: str = ""
    success_definition: str = ""
    constraints: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    deadline: str | None = None
    urgency: int = Field(default=50, ge=1, le=100)
    budget_limit: float | None = Field(default=None, ge=0)


class WorkUnit(BaseModel):
    """Immutable execution view of one atomic CEO task."""

    id: str
    title: str
    description: str = ""
    priority: int = 50
    acceptance_criteria: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_task(cls, task: Task) -> "WorkUnit":
        return cls(
            id=task.id,
            title=task.title,
            description=task.description,
            priority=task.priority,
            acceptance_criteria=list(task.acceptance_criteria),
            required_capabilities=list(task.required_capabilities),
            metadata=dict(task.metadata),
        )


class WorkerRequest(BaseModel):
    """The only input a provider receives from CEO Core.

    Keeping this envelope provider-neutral is what allows an API chat, browser chat,
    local model, or future remote node to be interchangeable from the scheduler's
    point of view.
    """

    project_id: str
    goal: GoalContract
    work_unit: WorkUnit
    conversation_id: str | None = None
    turn_index: int = 0
    instruction: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class WorkerResult(BaseModel):
    """Provider-neutral result returned by every worker implementation."""

    provider: str = "unknown"
    kind: WorkerKind = WorkerKind.API
    success: bool = True
    text: str = ""
    conversation_id: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ControllerDecision(BaseModel):
    """Formal decision produced after interpreting one worker turn."""

    action: ControllerAction
    reason: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    next_instruction: str | None = None
    spawned_tasks: list[str] = Field(default_factory=list)
    requires_user: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderHealth(BaseModel):
    provider: str
    available: bool = True
    detail: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerProvider(ABC):
    """Stable boundary implemented by API, browser, local, and mock workers."""

    name: str = "provider"
    kind: WorkerKind = WorkerKind.API
    capabilities: frozenset[str] = frozenset()

    def supports(self, task: Task) -> bool:
        required = set(task.required_capabilities)
        return required.issubset(self.capabilities) if required else True

    @abstractmethod
    async def execute(self, request: WorkerRequest) -> WorkerResult:
        raise NotImplementedError

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)


class WorkerRouter(ABC):
    """Selects the provider that should execute a task."""

    @abstractmethod
    def select(self, task: Task, state: ProjectState) -> WorkerProvider:
        raise NotImplementedError


class FixedWorkerRouter(WorkerRouter):
    """MVP router that always uses one provider.

    The scheduler already depends on the router interface, so multi-provider routing
    can be added later without changing scheduler contracts.
    """

    def __init__(self, provider: WorkerProvider) -> None:
        self.provider = provider

    def select(self, task: Task, state: ProjectState) -> WorkerProvider:
        if not self.provider.supports(task):
            raise RuntimeError(
                f"Provider '{self.provider.name}' lacks capabilities for task '{task.title}'"
            )
        return self.provider


class TaskPlanner(ABC):
    """Async planning boundary used by deterministic and future LLM planners."""

    @abstractmethod
    async def plan(self, goal: GoalContract) -> ProjectState:
        raise NotImplementedError
