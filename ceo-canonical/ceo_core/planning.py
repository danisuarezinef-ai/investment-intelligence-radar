from __future__ import annotations

from .contracts import GoalContract, TaskPlanner
from .decomposer import TaskDecomposer
from .models import ProjectState


class BaselineTaskPlanner(TaskPlanner):
    """Async adapter around the deterministic MVP decomposer.

    Future LLM planners implement the same contract and can perform network I/O
    without forcing another API change in the application layer.
    """

    def __init__(self, decomposer: TaskDecomposer | None = None) -> None:
        self.decomposer = decomposer or TaskDecomposer()

    async def plan(self, goal: GoalContract) -> ProjectState:
        state = self.decomposer.plan(goal.objective)
        state.goal_definition = goal.definition or goal.objective
        state.goal_success_definition = goal.success_definition
        state.goal_constraints = list(goal.constraints)
        state.goal_deliverables = list(goal.deliverables)
        state.deadline = goal.deadline
        state.urgency = goal.urgency
        state.budget_limit = goal.budget_limit
        state.metadata["forbidden_actions"] = list(goal.forbidden_actions)
        state.metadata["goal_contract_locked"] = True
        if goal.completion_criteria:
            state.completion_criteria = list(goal.completion_criteria)
        return state
