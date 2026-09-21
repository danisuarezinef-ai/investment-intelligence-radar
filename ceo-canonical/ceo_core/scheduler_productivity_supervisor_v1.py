from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .control_churn_circuit_breaker_v1 import ControlChurnCircuitBreakerV1
from .goal_completion_resolver_v1 import GoalCompletionResolverV1
from .productive_progress_guard_v1 import ProductiveProgressGuardV1
from .queue_consistency_rebuilder_v1 import QueueConsistencyRebuilderV1
from .recovery_budget_guard_v1 import RecoveryBudgetGuardV1
from .models import ProjectState, TaskStatus
from .task_roles_v2 import is_productive


@dataclass(slots=True)
class ProductivitySupervisorReport:
    status: str
    productive_completed: int
    productive_running: int
    productive_ready: int
    recovery_budget_exhausted: bool
    circuit_open: bool
    queue_repairs: int
    completion_action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SchedulerProductivitySupervisorV1:
    """Single hardening pass used every scheduler cycle.

    The supervisor is deliberately conservative: it can repair internal control
    state, recover queue consistency and open a control-plane circuit breaker, but
    it cannot approve protected human gates or invent productive completion.
    """

    KEY = "scheduler_productivity_supervisor_v1"

    def __init__(self) -> None:
        self.queue = QueueConsistencyRebuilderV1()
        self.progress = ProductiveProgressGuardV1()
        self.budget = RecoveryBudgetGuardV1()
        self.circuit = ControlChurnCircuitBreakerV1()
        self.completion = GoalCompletionResolverV1()

    def tick(self, state: ProjectState, *, active_task_ids: set[str] | None = None) -> ProductivitySupervisorReport:
        q = self.queue.rebuild(state, active_task_ids=active_task_ids)
        p = self.progress.assess(state)
        b = self.budget.apply(state)
        c = self.circuit.apply(state, productive_stalled=p.stalled or b.budget_exhausted)
        g = self.completion.resolve(state)

        # If the control plane is burning budget while productive work is already
        # ready, leave those productive tasks alone and suppress only further
        # internal churn.  The normal scheduler will dispatch the productive work.
        status = "healthy"
        if c.open or b.budget_exhausted:
            status = "control_churn_contained"
            state.metadata["suppress_new_internal_recovery"] = True
        elif p.stalled:
            status = "productive_stall_detected"
            state.metadata["productivity_kick_requested"] = True
        else:
            state.metadata.pop("suppress_new_internal_recovery", None)
            state.metadata.pop("productivity_kick_requested", None)

        # A hard guarantee for operator semantics: if runnable productive work
        # exists, a stale project-level stall marker may not claim global blockage.
        if any(is_productive(t, state) and t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING} for t in state.leaf_tasks):
            state.metadata.pop("autonomy_stalled", None)

        repairs = q.internal_review_recovered + q.orphan_running_requeued + q.dependencies_unblocked + q.duplicate_roots_removed + b.retired_excess + c.duplicate_internal_retired
        report = ProductivitySupervisorReport(
            status=status,
            productive_completed=p.productive_completed,
            productive_running=p.productive_running,
            productive_ready=p.productive_ready,
            recovery_budget_exhausted=b.budget_exhausted,
            circuit_open=c.open,
            queue_repairs=repairs,
            completion_action=g.action,
        )
        state.metadata[self.KEY] = report.to_dict()
        return report
