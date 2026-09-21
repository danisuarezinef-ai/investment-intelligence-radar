from __future__ import annotations

from dataclasses import asdict, dataclass
from uuid import uuid4

from .models import ProjectState, Task, TaskStatus


@dataclass(slots=True)
class ReplanResult:
    action: str
    source_task_id: str
    replacement_task_ids: list[str]
    preserved_dependencies: list[str]
    bounded: bool

    def to_dict(self) -> dict:
        return asdict(self)


class AutonomousReplanV2:
    MAX_GENERATIONS = 3

    def replan_failed(self, state: ProjectState, task: Task, alternatives: list[str]) -> ReplanResult:
        generation = int(task.metadata.get("replan_generation_v2", 0))
        if generation >= self.MAX_GENERATIONS or not alternatives:
            task.metadata["replan_v2_bounded"] = True
            return ReplanResult("bounded_stall", task.id, [], list(task.dependencies), True)
        replacements: list[str] = []
        for i, title in enumerate(alternatives[:3]):
            child = Task(
                title=str(title),
                description=f"Autonomous replan of: {task.title}",
                parent_id=task.parent_id,
                depth=task.depth,
                priority=max(1, task.priority - i),
                status=TaskStatus.WAITING,
                dependencies=list(task.dependencies),
                required_capabilities=list(task.required_capabilities),
                acceptance_criteria=list(task.acceptance_criteria),
                metadata={**dict(task.metadata), "replan_generation_v2": generation + 1, "replanned_from": task.id},
            )
            state.tasks[child.id] = child
            if child.parent_id and child.parent_id in state.tasks:
                parent = state.tasks[child.parent_id]
                if child.id not in parent.children:
                    parent.children.append(child.id)
            elif child.id not in state.root_task_ids:
                state.root_task_ids.append(child.id)
            replacements.append(child.id)
        task.status = TaskStatus.SUPERSEDED
        task.metadata["replanned_to_v2"] = replacements
        return ReplanResult("replanned", task.id, replacements, list(task.dependencies), False)
