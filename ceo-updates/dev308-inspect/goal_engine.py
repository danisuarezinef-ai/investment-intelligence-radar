from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json

from .contracts import GoalContract
from .models import ProjectState


DEFAULT_COMPLETION_CRITERIA = [
    "All planned deliverables are produced or explicitly marked out of scope.",
    "No blocking tasks or unresolved critical decisions remain.",
    "The final completion and quality audit passes.",
]


class GoalEngine:
    """Builds and applies the locked goal contract used by every downstream module.

    The UI may keep the common path as a single objective, while the contract can carry
    enough structure for long autonomous projects: explicit success, deliverables,
    constraints, deadline/urgency and budget.
    """

    def lock(
        self,
        objective: str,
        *,
        definition: str | None = None,
        success_definition: str | None = None,
        constraints: list[str] | None = None,
        completion_criteria: list[str] | None = None,
        deliverables: list[str] | None = None,
        forbidden_actions: list[str] | None = None,
        deadline: str | None = None,
        urgency: int = 50,
        budget_limit: float | None = None,
    ) -> GoalContract:
        objective = objective.strip()
        if not objective:
            raise ValueError("Goal objective cannot be empty")
        clean_deadline = (deadline or "").strip() or None
        if clean_deadline:
            # Keep the representation provider-neutral but reject obviously invalid input.
            try:
                datetime.fromisoformat(clean_deadline.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("deadline must be an ISO-8601 date/time string") from exc
        criteria = [x.strip() for x in (completion_criteria or []) if x and x.strip()]
        if not criteria:
            criteria = list(DEFAULT_COMPLETION_CRITERIA)
        return GoalContract(
            objective=objective,
            definition=(definition or objective).strip(),
            success_definition=(success_definition or "").strip(),
            constraints=[x.strip() for x in (constraints or []) if x and x.strip()],
            completion_criteria=criteria,
            deliverables=[x.strip() for x in (deliverables or []) if x and x.strip()],
            forbidden_actions=[x.strip() for x in (forbidden_actions or []) if x and x.strip()],
            deadline=clean_deadline,
            urgency=max(1, min(100, int(urgency))),
            budget_limit=None if budget_limit is None else max(0.0, float(budget_limit)),
        )

    def apply(self, state: ProjectState, goal: GoalContract) -> ProjectState:
        state.goal = goal.objective
        state.goal_definition = goal.definition or goal.objective
        state.goal_success_definition = goal.success_definition
        state.goal_constraints = list(goal.constraints)
        state.completion_criteria = list(goal.completion_criteria)
        state.goal_deliverables = list(goal.deliverables)
        state.deadline = goal.deadline
        state.urgency = goal.urgency
        state.budget_limit = goal.budget_limit
        state.metadata["goal_contract_locked"] = True
        contract_payload = goal.model_dump(mode="json")
        state.metadata["goal_contract_hash"] = sha256(
            json.dumps(contract_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        state.metadata["forbidden_actions"] = list(goal.forbidden_actions)
        if goal.forbidden_actions:
            policy = state.metadata.setdefault("safety_policy", {})
            policy["forbidden_actions"] = list(goal.forbidden_actions)
        return state

    def status(self, state: ProjectState) -> dict:
        completion = state.metadata.get("completion_assessment", {})
        evidence = state.metadata.get("deliverable_evidence", {})
        deliverable_status = [
            {"deliverable": item, "satisfied": bool(evidence.get(item)), "evidence": evidence.get(item)}
            for item in state.goal_deliverables
        ]
        return {
            "objective": state.goal,
            "definition": state.goal_definition,
            "success_definition": state.goal_success_definition,
            "deliverables": list(state.goal_deliverables),
            "deliverable_status": deliverable_status,
            "constraints": list(state.goal_constraints),
            "completion_criteria": list(state.completion_criteria),
            "deadline": state.deadline,
            "urgency": state.urgency,
            "budget_limit": state.budget_limit,
            "progress": state.progress,
            "completion": completion,
            "contract_hash": state.metadata.get("goal_contract_hash"),
        }
