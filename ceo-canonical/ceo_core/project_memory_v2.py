from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from .models import DecisionStatus, ProjectState, Task, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:24]


class StructuredProjectMemory:
    """Durable project memory with explicit epistemic buckets and bounded ledgers."""

    KEY = "structured_project_memory_v2"
    BUCKETS = ("facts", "hypotheses", "decisions", "artifacts", "pending", "errors")

    def ensure(self, state: ProjectState) -> dict[str, list[dict[str, Any]]]:
        root = state.metadata.setdefault(self.KEY, {})
        for name in self.BUCKETS:
            root.setdefault(name, [])
        root.setdefault("schema_version", 2)
        return root

    def add(self, state: ProjectState, bucket: str, *, text: str, source_ref: str | None = None, confidence: float | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if bucket not in self.BUCKETS:
            raise ValueError(f"unknown memory bucket: {bucket}")
        root = self.ensure(state)
        normalized = " ".join(str(text or "").split())
        row = {
            "id": _digest(f"{bucket}|{normalized}|{source_ref or ''}"),
            "ts": _now(),
            "text": normalized,
            "source_ref": source_ref,
            "confidence": confidence,
            "metadata": dict(metadata or {}),
        }
        rows = root[bucket]
        existing = next((x for x in rows if x.get("id") == row["id"]), None)
        if existing is not None:
            existing.update({k: v for k, v in row.items() if v is not None})
            return existing
        rows.append(row)
        default_limit = 10000 if bucket == "pending" else 1500
        limit = int(state.metadata.get(f"structured_memory_{bucket}_limit", state.metadata.get("structured_memory_bucket_limit", default_limit)) or default_limit)
        del rows[:-max(200 if bucket == "pending" else 50, limit)]
        return row

    def capture_task_success(self, state: ProjectState, task: Task) -> None:
        text = (task.result or "").strip()
        if text:
            bucket = "hypotheses" if task.status == TaskStatus.COMPLETE_WITH_UNCERTAINTY or float(task.confidence or 0.0) < 0.65 else "facts"
            self.add(state, bucket, text=f"{task.title}: {text}", source_ref=task.id, confidence=task.confidence, metadata={"quality": task.quality_score, "provider": task.provider_name})
        for artifact in task.metadata.get("artifacts", []) or []:
            self.add(state, "artifacts", text=str(artifact), source_ref=task.id, metadata={"task_title": task.title})
        self.resolve_pending(state, task.id)

    def capture_failure(self, state: ProjectState, task: Task, *, error: str) -> None:
        self.add(state, "errors", text=f"{task.title}: {error}", source_ref=task.id, metadata={"attempts": int(task.attempts), "provider": task.provider_name})

    def sync(self, state: ProjectState) -> dict[str, Any]:
        root = self.ensure(state)
        known_pending = {row.get("source_ref") for row in root["pending"]}
        for task in state.leaf_tasks:
            if task.status in {TaskStatus.WAITING, TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.RETRY, TaskStatus.RUNNING} and task.id not in known_pending:
                self.add(state, "pending", text=task.title, source_ref=task.id, metadata={"status": task.status.value, "priority": int(task.priority)})
        for decision in state.decisions.values():
            if decision.status != DecisionStatus.OPEN:
                self.add(state, "decisions", text=f"{decision.title}: {decision.selected or decision.recommendation or 'resolved'}", source_ref=decision.id, metadata={"status": decision.status.value})
        root["last_sync_at"] = _now()
        root["counts"] = {name: len(root[name]) for name in self.BUCKETS}
        return root["counts"]

    def resolve_pending(self, state: ProjectState, task_id: str) -> int:
        root = self.ensure(state)
        before = len(root["pending"])
        root["pending"][:] = [row for row in root["pending"] if row.get("source_ref") != task_id]
        return before - len(root["pending"])

    def context(self, state: ProjectState, *, per_bucket: int = 8) -> dict[str, list[dict[str, Any]]]:
        root = self.ensure(state)
        return {name: list(root[name][-per_bucket:]) for name in self.BUCKETS}
