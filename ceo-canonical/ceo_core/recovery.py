from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .graph import TaskGraph
from .models import ProjectState, TaskStatus
from .blocked_safe_state_v1 import preserve_blocked_safe


@dataclass(slots=True)
class RecoveryAssessment:
    consistent: bool
    recovered_running: int
    graph_valid: bool
    problems: list[str]


class RecoveryManager:
    """Idempotent restart preparation and integrity verification."""

    def __init__(self) -> None:
        self.graph = TaskGraph()

    def audit(self, state: ProjectState) -> RecoveryAssessment:
        """Inspect restart integrity without mutating live execution state."""
        problems: list[str] = []
        for task in state.tasks.values():
            if task.status == TaskStatus.COMPLETE and not task.result and not task.children:
                problems.append(f"complete_without_result:{task.id}")
        audit = self.graph.audit(state)
        if not audit["valid"]:
            problems.append("invalid_graph")
        # recovered_running is deliberately zero: audit is observational only.
        return RecoveryAssessment(not problems, 0, bool(audit["valid"]), problems)

    def prepare(self, state: ProjectState) -> RecoveryAssessment:
        recovered = 0
        problems: list[str] = []
        for task in state.tasks.values():
            if preserve_blocked_safe(task, source="recovery_manager"):
                continue
            if task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.RETRY
                task.metadata["recovered_after_restart"] = True
                recovered += 1
            if task.status == TaskStatus.COMPLETE and not task.result and not task.children:
                problems.append(f"complete_without_result:{task.id}")
        audit = self.graph.audit(state)
        if not audit["valid"]:
            problems.append("invalid_graph")
        state.metadata["last_recovery"] = {"ts": datetime.now(timezone.utc).isoformat(), "recovered_running": recovered, "problems": problems}
        return RecoveryAssessment(not problems, recovered, bool(audit["valid"]), problems)

    def idempotency_key(self, state: ProjectState, task_id: str) -> str:
        task = state.tasks[task_id]
        return f"{state.id}:{task.id}:{task.attempts}:{task.conversation_turns}"


class WriteAheadEventLog:
    """Append-only JSONL recovery journal; contains state events, never credentials."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, payload: dict[str, Any]) -> None:
        row = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, "payload": payload}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
