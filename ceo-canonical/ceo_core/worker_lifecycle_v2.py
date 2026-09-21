from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .models import ProjectState, Task, TaskStatus
from .blocked_safe_state_v1 import preserve_blocked_safe


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class WorkerLease:
    task_id: str
    worker_id: str
    lease_id: str
    claimed_at: str
    heartbeat_at: str
    expires_at: str
    released: bool = False
    release_reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class WorkerLifecycleV2:
    KEY = "worker_leases_v2"

    def _rows(self, state: ProjectState) -> dict[str, dict]:
        return state.metadata.setdefault(self.KEY, {})

    @staticmethod
    def _parse(text: str | None) -> datetime | None:
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def claim(self, state: ProjectState, task: Task, worker_id: str, *, ttl_seconds: int = 120, now: datetime | None = None) -> WorkerLease:
        now = now or _now()
        current = self._rows(state).get(task.id)
        if current and not current.get("released"):
            expiry = self._parse(current.get("expires_at"))
            if expiry and expiry > now:
                raise RuntimeError(f"task_already_leased:{task.id}")
        lease = WorkerLease(
            task_id=task.id,
            worker_id=str(worker_id),
            lease_id=uuid4().hex,
            claimed_at=now.isoformat(),
            heartbeat_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=max(5, int(ttl_seconds)))).isoformat(),
        )
        self._rows(state)[task.id] = lease.to_dict()
        task.worker_id = str(worker_id)
        task.metadata["worker_lease_id"] = lease.lease_id
        return lease

    def heartbeat(self, state: ProjectState, task_id: str, *, ttl_seconds: int = 120, now: datetime | None = None) -> bool:
        now = now or _now()
        row = self._rows(state).get(task_id)
        if not row or row.get("released"):
            return False
        row["heartbeat_at"] = now.isoformat()
        row["expires_at"] = (now + timedelta(seconds=max(5, int(ttl_seconds)))).isoformat()
        return True

    def release(self, state: ProjectState, task: Task, *, reason: str = "complete", now: datetime | None = None) -> bool:
        now = now or _now()
        row = self._rows(state).get(task.id)
        if not row:
            task.worker_id = None
            return False
        row["released"] = True
        row["release_reason"] = str(reason)
        row["released_at"] = now.isoformat()
        task.worker_id = None
        return True

    def reconcile(self, state: ProjectState, *, active_task_ids: set[str], now: datetime | None = None) -> dict:
        now = now or _now()
        recovered: list[str] = []
        expired: list[str] = []
        rows = self._rows(state)
        for task_id, row in list(rows.items()):
            if row.get("released"):
                continue
            expiry = self._parse(row.get("expires_at"))
            task = state.tasks.get(task_id)
            stale = task_id not in active_task_ids and (expiry is None or expiry <= now)
            if stale:
                row["released"] = True
                row["release_reason"] = "stale_orphan_recovered"
                row["released_at"] = now.isoformat()
                expired.append(task_id)
                if task and preserve_blocked_safe(task, source="worker_lifecycle"):
                    pass
                elif task and task.status == TaskStatus.RUNNING:
                    task.status = TaskStatus.RETRY
                    task.worker_id = None
                    task.metadata["worker_lease_recovered_v2"] = True
                    recovered.append(task_id)
        return {"expired_leases": expired, "tasks_recovered": recovered, "active_leases": sum(1 for x in rows.values() if not x.get("released"))}
