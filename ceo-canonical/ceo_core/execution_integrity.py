from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from random import Random
from typing import Any, Iterable

from .cost import CostEngine
from .graph import TaskGraph
from .models import ProjectState, TaskStatus
from .recovery import RecoveryManager


@dataclass(slots=True)
class IdempotencyRecord:
    key: str
    status: str
    operation: str
    result_digest: str | None = None
    attempts: int = 1


class IdempotencyRegistry:
    """State-backed exactly-once guard for consequential external operations."""

    KEY = "idempotency_registry_v1"

    def begin(self, state: ProjectState, *, key: str, operation: str) -> dict[str, Any]:
        rows = state.metadata.setdefault(self.KEY, {})
        row = rows.get(key)
        if row:
            row["attempts"] = int(row.get("attempts", 1)) + 1
            return {"execute": False, "record": dict(row), "reason": "duplicate_key"}
        record = IdempotencyRecord(key, "in_progress", operation)
        rows[key] = asdict(record)
        return {"execute": True, "record": dict(rows[key]), "reason": "new_key"}

    def complete(self, state: ProjectState, key: str, result: Any) -> bool:
        row = state.metadata.setdefault(self.KEY, {}).get(key)
        if not row:
            return False
        row["status"] = "complete"
        row["result_digest"] = sha256(repr(result).encode()).hexdigest()
        return True

    def fail(self, state: ProjectState, key: str, *, retryable: bool) -> bool:
        row = state.metadata.setdefault(self.KEY, {}).get(key)
        if not row:
            return False
        row["status"] = "retryable_failure" if retryable else "failed"
        return True

    def recover_in_progress(self, state: ProjectState) -> list[str]:
        recovered = []
        for key, row in state.metadata.setdefault(self.KEY, {}).items():
            if row.get("status") == "in_progress":
                row["status"] = "needs_reconciliation"; recovered.append(key)
        return recovered


class WorkspaceGuard:
    """Enforces path containment without relying on string-prefix comparisons."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def resolve(self, candidate: str | Path) -> Path:
        raw = Path(candidate)
        path = (self.root / raw).resolve() if not raw.is_absolute() else raw.resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise PermissionError("path escapes project workspace") from exc
        return path

    def allowed(self, candidate: str | Path) -> bool:
        try:
            self.resolve(candidate); return True
        except PermissionError:
            return False


@dataclass(slots=True)
class ChaosFault:
    task_id: str
    kind: str
    occurrence: int


class ChaosPlanner:
    FAULTS = ("timeout", "provider_outage", "rate_limit", "malformed_response", "transient_io")

    def plan(self, task_ids: Iterable[str], *, seed: int = 1, rate: float = .1) -> list[ChaosFault]:
        rng = Random(seed); faults = []
        rate = max(0.0, min(1.0, float(rate)))
        for tid in task_ids:
            if rng.random() < rate:
                faults.append(ChaosFault(str(tid), rng.choice(self.FAULTS), 1))
        return faults

    @staticmethod
    def expected_recovery(fault: str) -> str:
        return {
            "timeout": "fallback_provider",
            "provider_outage": "fallback_provider",
            "rate_limit": "fallback_provider",
            "malformed_response": "retry",
            "transient_io": "retry",
        }.get(fault, "escalate")


class CrashConsistencyAuditor:
    def __init__(self) -> None:
        self.recovery = RecoveryManager(); self.graph = TaskGraph(); self.cost = CostEngine(); self.idempotency = IdempotencyRegistry()

    def prepare_and_audit(self, state: ProjectState) -> dict[str, Any]:
        stale_reservations = self.cost.clear_reservations(state, reason="crash_recovery")
        in_progress_keys = self.idempotency.recover_in_progress(state)
        recovery = self.recovery.prepare(state)
        graph = self.graph.audit(state)
        impossible = []
        for t in state.leaf_tasks:
            if t.status == TaskStatus.COMPLETE and not t.result:
                impossible.append(f"complete_without_result:{t.id}")
            if t.status == TaskStatus.RUNNING:
                impossible.append(f"running_after_recovery:{t.id}")
        return {
            "consistent": recovery.consistent and graph["valid"] and not impossible,
            "recovered_running": recovery.recovered_running,
            "released_cost_reservations": len(stale_reservations),
            "idempotency_reconciliation": in_progress_keys,
            "impossible_states": impossible,
            "graph_valid": graph["valid"],
        }


class ConcurrencyInvariantAuditor:
    def __init__(self) -> None:
        self.cost = CostEngine(); self.graph = TaskGraph()

    def audit(self, state: ProjectState) -> dict[str, Any]:
        reservations = self.cost.reservations(state)
        budget_ok = state.budget_limit is None or self.cost.committed(state) <= float(state.budget_limit) + 1e-9
        negative = [k for k, v in reservations.items() if float(v) < 0]
        duplicate_running_conversations = []
        seen: dict[str, str] = {}
        for t in state.leaf_tasks:
            if t.status != TaskStatus.RUNNING or not t.conversation_id:
                continue
            if t.conversation_id in seen:
                duplicate_running_conversations.append((seen[t.conversation_id], t.id))
            else:
                seen[t.conversation_id] = t.id
        graph = self.graph.audit(state)
        return {
            "pass": budget_ok and not negative and not duplicate_running_conversations and graph["valid"],
            "budget_ok": budget_ok,
            "negative_reservations": negative,
            "duplicate_running_conversations": duplicate_running_conversations,
            "graph_valid": graph["valid"],
        }


class LocalAcceptanceHarnessV2:
    """Aggregates execution-integrity gates without pretending to run field tests."""

    def run(self, state: ProjectState, workspace_root: str | Path) -> dict[str, Any]:
        workspace = WorkspaceGuard(workspace_root)
        concurrency = ConcurrencyInvariantAuditor().audit(state)
        graph = TaskGraph().audit(state)
        checks = {
            "workspace_containment": workspace.allowed("artifacts/output.txt") and not workspace.allowed(Path(workspace_root).resolve().parent / "escape.txt"),
            "concurrency_invariants": concurrency["pass"],
            "graph_integrity": graph["valid"],
            "no_negative_cost_reservations": not concurrency["negative_reservations"],
        }
        return {
            "pass": all(checks.values()),
            "checks": checks,
            "deferred": ["physical_windows", "authenticated_live_provider", "field_production_proof"],
        }
