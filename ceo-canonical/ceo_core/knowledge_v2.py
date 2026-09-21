from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Any

from .claims import ClaimRegistry, SourceRegistry
from .models import ProjectState, Task, TaskStatus


@dataclass(slots=True)
class KnowledgeStatus:
    facts: int
    claims: int
    sources: int
    conflicts: int
    open_questions: int
    uncertainty: float


class KnowledgeIntegrationEngine:
    """Maintains a compact project knowledge layer independent from raw conversations."""

    def __init__(self) -> None:
        self.claims = ClaimRegistry()
        self.sources = SourceRegistry()

    def rebuild_indexes(self, state: ProjectState) -> KnowledgeStatus:
        knowledge = state.metadata.get("knowledge", {})
        open_questions = 0
        uncertain = 0
        facts = 0
        by_parent: dict[str, list[str]] = defaultdict(list)
        for tid, item in knowledge.items():
            facts += 1
            parent = str(item.get("parent_id") or "root")
            by_parent[parent].append(tid)
            task = state.tasks.get(tid)
            if task and (task.status in {TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY} or (task.confidence is not None and task.confidence < .6)):
                uncertain += 1
        for task in state.leaf_tasks:
            if task.status in {TaskStatus.NEEDS_REVIEW, TaskStatus.FAILED, TaskStatus.BLOCKED}:
                open_questions += 1
        conflicts = len(state.metadata.get("conflict_reviews", {}))
        state.metadata["knowledge_index"] = {k: v[-200:] for k, v in by_parent.items()}
        status = KnowledgeStatus(facts, len(state.metadata.get("claims", {})), len(state.metadata.get("sources", {})), conflicts, open_questions, round(uncertain / max(1, facts), 4))
        state.metadata["knowledge_status"] = asdict(status)
        return status

    def briefing(self, state: ProjectState, max_chars: int = 12000) -> str:
        rows: list[str] = []
        for tid in state.metadata.get("result_order", [])[-100:]:
            item = state.metadata.get("knowledge", {}).get(tid)
            if not item:
                continue
            rows.append(f"[{item.get('title')}] {str(item.get('result', ''))[:700]}")
            if sum(len(x) for x in rows) >= max_chars:
                break
        return "\n".join(rows)[:max_chars]

    def unresolved(self, state: ProjectState) -> list[dict[str, Any]]:
        return list(self.claims.unresolved(state))
