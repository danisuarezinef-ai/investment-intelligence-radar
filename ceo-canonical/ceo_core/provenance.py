from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

from .models import ProjectState, Task


class ProvenanceGraph:
    def record(self, state: ProjectState, task: Task, *, sources: list[str] | None = None) -> None:
        graph = state.metadata.setdefault("provenance", {})
        source_ids = list(task.metadata.get("source_ids", []))
        claim_ids = list((state.metadata.get("knowledge", {}).get(task.id, {}) or {}).get("claim_ids", []))
        graph[task.id] = {
            "task": task.title,
            "parent": task.parent_id,
            "dependencies": list(task.dependencies),
            "provider": task.provider_name,
            "conversation_id": task.conversation_id,
            "sources": list(sources or task.metadata.get("sources", [])),
            "source_ids": source_ids,
            "claim_ids": claim_ids,
            "result_digest": sha256((task.result or "").encode()).hexdigest(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        reverse = state.metadata.setdefault("provenance_reverse", {"claims": {}, "sources": {}, "conversations": {}})
        for cid in claim_ids:
            reverse["claims"].setdefault(cid, []).append(task.id)
        for sid in source_ids:
            reverse["sources"].setdefault(sid, []).append(task.id)
        if task.conversation_id:
            reverse["conversations"].setdefault(task.conversation_id, []).append(task.id)


class AuditLog:
    def emit(self, state: ProjectState, event: str, data: dict | None = None) -> None:
        log = state.metadata.setdefault("audit_log", [])
        log.append({"ts": datetime.now(timezone.utc).isoformat(), "event": event, "data": data or {}})
        if len(log) > 10_000:
            del log[:-10_000]
