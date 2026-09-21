from __future__ import annotations

import json
import re
from typing import Any

from ceo_core.ai_worker import AITransport, AITransportRequest
from ceo_core.contracts import GoalContract, TaskPlanner
from ceo_core.graph import TaskGraph
from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.decomposition_v3 import AdaptiveTaskDecomposer


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class LLMTaskPlanner(TaskPlanner):
    """AI-driven decomposer that maximizes safe parallelism while encoding true dependencies."""

    def __init__(self, transport: AITransport, *, fallback: TaskPlanner | None = None) -> None:
        self.transport = transport
        self.fallback = fallback

    async def plan(self, goal: GoalContract) -> ProjectState:
        prompt = self._prompt(goal)
        try:
            response = await self.transport.send(AITransportRequest(prompt=prompt))
            payload = self._parse(response.text)
            state = self._state_from_payload(goal, payload)
            AdaptiveTaskDecomposer().refine_state(state)
            TaskGraph().refresh(state)
            return state
        except Exception:
            if self.fallback:
                return await self.fallback.plan(goal)
            raise

    @staticmethod
    def _prompt(goal: GoalContract) -> str:
        return f"""You are the Task Decomposer of CEO de IAs.
Decompose the locked goal into a compact hierarchical project plan whose leaf tasks are individually executable by one AI chat. Maximize parallel execution, but add dependencies whenever a task genuinely needs an earlier result. Do not add fake work.

GOAL: {goal.objective}
DEFINITION: {goal.definition}
SUCCESS DEFINITION: {goal.success_definition}
DELIVERABLES: {json.dumps(goal.deliverables, ensure_ascii=False)}
CONSTRAINTS: {json.dumps(goal.constraints, ensure_ascii=False)}
FORBIDDEN ACTIONS: {json.dumps(goal.forbidden_actions, ensure_ascii=False)}
DEADLINE: {goal.deadline or "none"}
URGENCY (1-100): {goal.urgency}
BUDGET LIMIT: {goal.budget_limit if goal.budget_limit is not None else "none"}
COMPLETION CRITERIA: {json.dumps(goal.completion_criteria, ensure_ascii=False)}

Return ONLY valid JSON with this exact shape:
{{
  "phases": [
    {{"key":"research","title":"Research","description":"...","priority":90,
      "tasks":[
        {{"key":"r1","title":"...","description":"...","priority":90,
          "depends_on":[],"capabilities":["general"],"preferred_kind":"api",
          "acceptance_criteria":["..."],
          "subtasks":[{{"key":"r1a","title":"optional deeper unit","depends_on":[],"capabilities":["general"],"acceptance_criteria":["..."]}}]}}
      ]}}
  ]
}}
subtasks is optional and may recurse when a unit is still too large for one chat. Keep hierarchy compact; split only when useful. Keys must be unique. depends_on references task keys, not phase keys. Keep leaf tasks small enough for one chat response or a short multi-turn conversation. For capabilities use only general, analysis, writing, coding, reasoning, chat, or browser; only require browser when a web UI is genuinely necessary."""

    @staticmethod
    def _parse(text: str) -> dict[str, Any]:
        match = _JSON_RE.search(text.strip())
        if not match:
            raise ValueError("Planner returned no JSON object")
        return json.loads(match.group(0))

    @staticmethod
    def _state_from_payload(goal: GoalContract, payload: dict[str, Any]) -> ProjectState:
        state = ProjectState(
            goal=goal.objective,
            goal_definition=goal.definition or goal.objective,
            goal_success_definition=goal.success_definition,
            goal_constraints=list(goal.constraints),
            completion_criteria=list(goal.completion_criteria),
            goal_deliverables=list(goal.deliverables),
            deadline=goal.deadline,
            urgency=goal.urgency,
            budget_limit=goal.budget_limit,
            metadata={"forbidden_actions": list(goal.forbidden_actions), "goal_contract_locked": True},
        )
        key_to_id: dict[str, str] = {}
        pending_deps: list[tuple[Task, list[str]]] = []

        def add_task(raw: dict[str, Any], parent: Task, depth: int, fallback_priority: int) -> Task:
            key = str(raw.get("key") or f"task-{len(key_to_id)+1}")
            if key in key_to_id:
                key = f"{key}-{len(key_to_id)+1}"
            task = Task(
                title=str(raw.get("title") or key),
                description=str(raw.get("description") or ""),
                parent_id=parent.id, depth=depth,
                priority=max(1, min(100, int(raw.get("priority", fallback_priority)))),
                estimated_seconds=float(raw.get("estimated_seconds", 30.0)),
                required_capabilities=[str(v) for v in raw.get("capabilities") or ["general"]],
                acceptance_criteria=[str(v) for v in raw.get("acceptance_criteria") or []],
                metadata={"planner_key": key, "preferred_kind": raw.get("preferred_kind", "api")},
            )
            state.tasks[task.id] = task; parent.children.append(task.id); key_to_id[key] = task.id
            pending_deps.append((task, [str(v) for v in raw.get("depends_on") or []]))
            for child in raw.get("subtasks") or []:
                add_task(child, task, depth + 1, task.priority)
            return task

        for phase in payload.get("phases") or []:
            root = Task(
                title=str(phase.get("title") or phase.get("key") or "Phase"),
                description=str(phase.get("description") or ""), depth=0,
                priority=int(phase.get("priority", 50)), status=TaskStatus.WAITING,
            )
            state.tasks[root.id] = root; state.root_task_ids.append(root.id)
            for raw in phase.get("tasks") or []:
                add_task(raw, root, 1, root.priority)
        for task, dep_keys in pending_deps:
            task.dependencies = [key_to_id[k] for k in dep_keys if k in key_to_id]
        if not state.leaf_tasks:
            raise ValueError("Planner generated no executable leaf tasks")
        return state
