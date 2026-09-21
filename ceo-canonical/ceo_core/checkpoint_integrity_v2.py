from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
import json

from .models import ProjectState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class IntegrityReport:
    ok: bool
    expected: str | None
    actual: str
    sequence: int
    checked_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CheckpointIntegrityV2:
    KEY = "checkpoint_integrity_v2"
    VOLATILE_META = {KEY, "activity_snapshot", "activity_timeline", "operations_dashboard_v1"}

    def canonical(self, state: ProjectState) -> dict[str, Any]:
        tasks = {}
        for tid, t in sorted(state.tasks.items()):
            tasks[tid] = {
                "status": t.status.value, "attempts": int(t.attempts), "parent_id": t.parent_id,
                "dependencies": list(t.dependencies), "provider": t.provider_name,
                "result_sha": sha256((t.result or "").encode()).hexdigest() if t.result else None,
                "dispatch_token": t.metadata.get("dispatch_token"),
            }
        decisions = {did: {"status": d.status.value, "selected": d.selected} for did, d in sorted(state.decisions.items())}
        metadata = {
            k: v for k, v in state.metadata.items()
            if k not in self.VOLATILE_META and not str(k).startswith("telemetry") and k in {
                "goal_contract_hash", "forbidden_actions", "goal_audit_passed", "accepted_release_sequence",
                "runtime_session", "structured_project_memory_v2", "dependency_manager_last", "mission_supervisor_v2"
            }
        }
        return {"id": state.id, "goal": state.goal, "paused": state.paused, "tasks": tasks, "decisions": decisions, "metadata": metadata}

    def digest(self, state: ProjectState) -> str:
        payload = json.dumps(self.canonical(state), sort_keys=True, separators=(",", ":"), default=str).encode()
        return sha256(payload).hexdigest()

    def verify(self, state: ProjectState) -> IntegrityReport:
        row = state.metadata.get(self.KEY) or {}
        expected = row.get("digest")
        actual = self.digest(state)
        report = IntegrityReport(expected in {None, actual}, expected, actual, int(row.get("sequence", 0) or 0), _now())
        state.metadata.setdefault("checkpoint_integrity_checks_v2", []).append(report.to_dict())
        del state.metadata["checkpoint_integrity_checks_v2"][:-100]
        return report

    def stamp(self, state: ProjectState) -> IntegrityReport:
        old = state.metadata.get(self.KEY) or {}
        sequence = int(old.get("sequence", 0) or 0) + 1
        digest = self.digest(state)
        row = {"schema_version": 2, "sequence": sequence, "digest": digest, "stamped_at": _now(), "task_count": len(state.tasks)}
        state.metadata[self.KEY] = row
        return IntegrityReport(True, digest, digest, sequence, row["stamped_at"])

    def compact(self, state: ProjectState) -> dict[str, int]:
        limits = {"activity_timeline": 500, "recovery_events": 500, "dispatch_ledger": 1000, "evidence_ledger_v2": 5000, "incident_history_v1": 1000}
        removed: dict[str, int] = {}
        for key, limit in limits.items():
            rows = state.metadata.get(key)
            if isinstance(rows, list) and len(rows) > limit:
                removed[key] = len(rows) - limit
                state.metadata[key] = rows[-limit:]
        return removed
