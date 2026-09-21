from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Iterable

from .models import ProjectState, Task, TaskStatus
from .task_roles_v2 import is_productive

_TERMINAL = {
    TaskStatus.COMPLETE,
    TaskStatus.PARTIAL_COMPLETE,
    TaskStatus.COMPLETE_WITH_UNCERTAINTY,
    TaskStatus.SUPERSEDED,
}


@dataclass(slots=True)
class ProductiveTaskReceipt:
    task_id: str
    productive: bool
    terminal: bool
    result_present: bool
    acceptance_evidence_present: bool
    artifact_count: int
    dependency_count: int
    unresolved_dependencies: list[str]
    definition_of_done_met: bool
    receipt_sha256: str

    def to_dict(self) -> dict:
        return asdict(self)


class ProductiveTaskContractV1:
    """Strict, deterministic definition of done for productive work.

    Internal control/verification tasks are deliberately outside this contract; they
    retain their dedicated gates.  A productive task only becomes a deliverable when
    it is terminal, has a substantive result, has no unresolved dependencies and has
    either explicit acceptance evidence or a concrete artifact/evidence reference.
    """

    def unresolved_dependencies(self, state: ProjectState, task: Task) -> list[str]:
        unresolved: list[str] = []
        for dep_id in task.dependencies:
            dep = state.tasks.get(dep_id)
            if dep is None or dep.status not in _TERMINAL:
                unresolved.append(dep_id)
        return unresolved

    @staticmethod
    def _refs(task: Task) -> list[str]:
        refs: list[str] = []
        for key in ("artifacts", "evidence_refs", "implementation_refs", "source_ids"):
            raw = task.metadata.get(key, [])
            if isinstance(raw, (list, tuple, set)):
                refs.extend(str(x) for x in raw if str(x).strip())
        for key in ("test_ref", "evidence_ref", "receipt_ref"):
            value = task.metadata.get(key)
            if value:
                refs.append(str(value))
        return refs

    def evaluate(self, state: ProjectState, task: Task) -> ProductiveTaskReceipt:
        productive = is_productive(task, state)
        terminal = task.status in _TERMINAL
        result_present = bool((task.result or "").strip())
        refs = self._refs(task)
        acceptance = bool(task.metadata.get("acceptance_evidence")) or bool(refs)
        unresolved = self.unresolved_dependencies(state, task)
        met = bool(productive and terminal and result_present and acceptance and not unresolved)
        canonical = "|".join([
            task.id,
            str(productive),
            str(terminal),
            str(result_present),
            str(acceptance),
            ",".join(sorted(unresolved)),
            ",".join(sorted(refs)),
        ])
        digest = sha256(canonical.encode("utf-8")).hexdigest()
        return ProductiveTaskReceipt(
            task_id=task.id,
            productive=productive,
            terminal=terminal,
            result_present=result_present,
            acceptance_evidence_present=acceptance,
            artifact_count=len(refs),
            dependency_count=len(task.dependencies),
            unresolved_dependencies=unresolved,
            definition_of_done_met=met,
            receipt_sha256=digest,
        )

    def validate_batch(self, state: ProjectState, tasks: Iterable[Task]) -> list[ProductiveTaskReceipt]:
        return [self.evaluate(state, task) for task in tasks]
