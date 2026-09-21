from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Any

from .models import ProjectState, Task, TaskStatus
from .progress_tracker import TERMINAL_OK, is_control_plane
from .operational_resilience import resilience_snapshot
from .operations_dashboard import OperationsDashboardBuilder
from .evidence_ledger_v2 import EvidenceLedgerV2
from .decision_trace_v3 import DecisionTraceV3
from .quota_governor_v2 import QuotaGovernorV2


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _age_seconds(dt: datetime | None, now: datetime) -> float | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (now - dt.astimezone(timezone.utc)).total_seconds())


def _is_productive(task: Task) -> bool:
    return not is_control_plane(task)


@dataclass(frozen=True)
class ObservabilityWindow:
    recent_minutes: int = 15
    history_limit: int = 40


class OperationalObservability:
    """Build a durable, read-only operator view from project/task state.

    The snapshot intentionally does not depend on frontend timers. It can be rebuilt
    after a restart from persisted task timestamps and bounded activity/recovery logs.
    """

    def __init__(self, window: ObservabilityWindow | None = None) -> None:
        self.window = window or ObservabilityWindow()
        self.dashboard_builder = OperationsDashboardBuilder()
        self.evidence_ledger = EvidenceLedgerV2()
        self.decision_trace_v3 = DecisionTraceV3()
        self.quota_governor_v2 = QuotaGovernorV2()

    def snapshot(self, state: ProjectState, scheduler: Any | None = None) -> dict[str, Any]:
        now = _utcnow()
        leaves = list(state.leaf_tasks)
        productive = [t for t in leaves if _is_productive(t) and t.status != TaskStatus.SUPERSEDED]
        terminal = [t for t in productive if t.status in TERMINAL_OK]
        running = [t for t in productive if t.status == TaskStatus.RUNNING]
        pending = [t for t in productive if t.status not in TERMINAL_OK and t.status != TaskStatus.SUPERSEDED]

        active_provider = dict(getattr(scheduler, "_active_provider", {}) or {}) if scheduler is not None else {}
        active_ids = set(getattr(scheduler, "_active", set()) or set()) if scheduler is not None else set()
        if not active_ids:
            active_ids = {t.id for t in running}

        current = []
        for tid in active_ids:
            task = state.tasks.get(tid)
            if task is None:
                continue
            elapsed = _age_seconds(task.started_at, now)
            current.append({
                "task_id": task.id,
                "title": task.title,
                "provider": active_provider.get(task.id) or task.provider_name,
                "stage": task.metadata.get("provider_stage") or "running",
                "attempt": int(task.attempts),
                "turn": int(task.conversation_turns),
                "started_at": _iso(task.started_at),
                "elapsed_seconds": round(elapsed, 1) if elapsed is not None else None,
            })
        current.sort(key=lambda row: (row.get("started_at") or "", row["title"]))

        durations = [float(t.actual_seconds) for t in terminal if t.actual_seconds is not None and float(t.actual_seconds) > 0]
        typical_seconds = float(median(durations)) if durations else self._median_planned_seconds(productive)
        cutoff = now.timestamp() - self.window.recent_minutes * 60
        recent_completed = [
            t for t in terminal
            if t.completed_at is not None and t.completed_at.timestamp() >= cutoff
        ]
        throughput_15m = round(len(recent_completed) / max(1, self.window.recent_minutes), 3)
        throughput_hour = round(throughput_15m * 60, 2)

        recent_terminal = sorted(terminal, key=lambda t: t.completed_at or t.started_at or t.created_at, reverse=True)[:20]
        quality_values = [float(t.quality_score) for t in recent_terminal if t.quality_score is not None]
        avg_quality = round(sum(quality_values) / len(quality_values), 3) if quality_values else None

        failures = [t for t in productive if t.status == TaskStatus.FAILED]
        blocked = [t for t in productive if t.status == TaskStatus.BLOCKED]
        human_review = [t for t in productive if t.status == TaskStatus.NEEDS_REVIEW]
        attention = failures + blocked + human_review

        eta_seconds = self._eta_seconds(pending, typical_seconds, max(1, len(current)))
        last_progress_task = max(terminal, key=lambda t: t.completed_at or t.started_at or t.created_at, default=None)
        last_progress_at = (last_progress_task.completed_at or last_progress_task.started_at or last_progress_task.created_at) if last_progress_task else None
        last_progress_age = _age_seconds(last_progress_at, now)

        stale_threshold = max(300.0, typical_seconds * 5.0)
        stale_workers = [row for row in current if row.get("elapsed_seconds") is not None and float(row["elapsed_seconds"]) > stale_threshold]

        recovery_events = list(state.metadata.get("recovery_events", []))[-self.window.history_limit:]
        activity = list(state.metadata.get("activity_timeline", []))[-self.window.history_limit:]
        crashes = list(state.metadata.get("scheduler_crash_history", []))[-10:]
        auto_restarts = int(state.metadata.get("scheduler_auto_restarts", 0) or 0)

        health, health_reasons = self._health(
            completed=state.completed_at is not None,
            paused=state.paused,
            current=current,
            pending=pending,
            attention=attention,
            stale_workers=stale_workers,
            scheduler=scheduler,
        )
        productive_truth = dict(state.metadata.get("productive_truth_v2") or {})
        watchdog = dict(state.metadata.get("useful_output_watchdog_v2") or {})
        if productive_truth.get("status") == "waiting_provider":
            health = "waiting_provider"
            health_reasons = [str(productive_truth.get("reason") or "provider temporarily unavailable")]
        elif productive_truth.get("stalled"):
            health = "stalled"
            health_reasons = [str(productive_truth.get("reason") or "productive output stalled")]

        provider_stats = self._provider_stats(state)
        next_tasks = sorted(
            [t for t in pending if t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.WAITING}],
            key=lambda t: (-int(t.priority), t.created_at),
        )[:8]

        return {
            "generated_at": now.isoformat(),
            "health": {"level": health, "reasons": health_reasons},
            "productive_truth": productive_truth,
            "stall_escape": watchdog,
            "current_work": current,
            "next_work": [
                {"task_id": t.id, "title": t.title, "status": t.status.value, "priority": int(t.priority)}
                for t in next_tasks
            ],
            "throughput": {
                "completed_last_15m": len(recent_completed),
                "tasks_per_minute_15m": throughput_15m,
                "tasks_per_hour_equivalent": throughput_hour,
                "typical_task_seconds": round(typical_seconds, 1),
                "average_recent_quality": avg_quality,
            },
            "eta": {
                "seconds": eta_seconds,
                "basis": "pending productive tasks / active workers using observed median duration",
                "pending_productive": len(pending),
                "active_workers": len(current),
            },
            "progress": {
                "productive_completed": len(terminal),
                "productive_total_known": len(productive),
                "last_productive_progress_at": _iso(last_progress_at),
                "last_productive_progress_age_seconds": round(last_progress_age, 1) if last_progress_age is not None else None,
            },
            "attention": [self._attention_row(t) for t in attention[:20]],
            "stale_workers": stale_workers,
            "recoveries": list(reversed(recovery_events[-20:])),
            "timeline": list(reversed(activity[-30:])),
            "scheduler": {
                "alive": self._scheduler_alive(scheduler),
                "auto_restarts": auto_restarts,
                "recent_crashes": list(reversed(crashes)),
            },
            "resilience": resilience_snapshot(state),
            "governance": {
                "quality_gate_rejections": len(state.metadata.get("quality_gate_history", []) or []),
                "self_corrections": len(state.metadata.get("self_correction_events", []) or []),
                "dependency_health": dict(state.metadata.get("dependency_health", {}) or {}),
                "dynamic_task_tree": dict(state.metadata.get("dynamic_task_tree_last", {}) or {}),
                "memory_counts": dict(((state.metadata.get("structured_project_memory_v2") or {}).get("counts") or {})),
            },
            "providers": provider_stats,
            "dashboard": self.dashboard_builder.build(state),
            "evidence_ledger": self.evidence_ledger.validate(state),
            "multi_ai": {
                "last_route": dict(state.metadata.get("last_multi_ai_route", {}) or {}),
                "provider_promotions": list(state.metadata.get("provider_promotions", []) or [])[-20:],
            },
            "application_recovery": {
                "count": len(state.metadata.get("application_recovery_history", []) or []),
                "latest": list(reversed((state.metadata.get("application_recovery_history", []) or [])[-10:])),
            },
            "advanced_readiness": {
                "stress_lab": dict(state.metadata.get("stress_lab_latest", {}) or {}),
                "field_campaign": dict(state.metadata.get("windows_field_campaign_v2", {}) or {}),
                "self_evolution": {
                    "candidates": len((((state.metadata.get("self_evolution_v2") or {}).get("candidates")) or {})),
                    "automatic_publication": False,
                    "automatic_stable_promotion": False,
                },
                "degraded_operation": dict(state.metadata.get("degraded_operation_v1", {}) or {}),
                "security_posture": dict(state.metadata.get("security_posture_v1", {}) or {}),
                "release_qualification": dict(state.metadata.get("release_qualification_v2", {}) or {}),
                "mission_supervisor": dict(state.metadata.get("mission_supervisor_v2", {}) or {}),
                "fair_allocator": dict(state.metadata.get("fair_work_allocator_v1", {}) or {}),
                "checkpoint_integrity": dict(state.metadata.get("checkpoint_integrity_v2", {}) or {}),
                "capability_policy_events": len(state.metadata.get("capability_policy_events_v2", []) or []),
                "remote_session": {"mutation_nonce_required": True, "used_nonce_count": len(((state.metadata.get("remote_session_v2") or {}).get("used_nonce_hashes") or {}))},
                "canary_execution": dict(state.metadata.get("canary_execution_v1", {}) or {}),
                "incident_manager": dict(state.metadata.get("incident_manager_v2", {}) or {}),
                "release_readiness_v3": dict(state.metadata.get("release_readiness_v3", {}) or {}),
                "portfolio_supervisor": dict(state.metadata.get("portfolio_supervisor_v1", {}) or {}),
                "quota_governor": {
                    "last_decision": dict(state.metadata.get("quota_governor_v2", {}) or {}),
                    "counters": self.quota_governor_v2.counters(state),
                    "limits": self.quota_governor_v2.limits(state),
                },
                "decision_trace_v3": self.decision_trace_v3.verify(state),
                "delegation_contracts_v2": {
                    "issued": int(((state.metadata.get("delegation_contracts_v2") or {}).get("issued") or 0)),
                    "blocked": int(((state.metadata.get("delegation_contracts_v2") or {}).get("blocked") or 0)),
                },
                "soak_guard_v1": dict(state.metadata.get("soak_guard_v1", {}) or {}),
                "release_readiness_v4": dict(state.metadata.get("release_readiness_v4", {}) or {}),
            },
        }

    @staticmethod
    def _median_planned_seconds(tasks: list[Task]) -> float:
        planned = [float(t.estimated_seconds) for t in tasks if float(t.estimated_seconds or 0) > 0]
        return float(median(planned)) if planned else 30.0

    @staticmethod
    def _eta_seconds(pending: list[Task], typical_seconds: float, active_workers: int) -> int:
        if not pending:
            return 0
        estimates = []
        for task in pending:
            planned = float(task.estimated_seconds or 0)
            if planned > 0:
                estimates.append((planned * 0.35) + (typical_seconds * 0.65))
            else:
                estimates.append(typical_seconds)
        return int(round(sum(estimates) / max(1, active_workers)))

    @staticmethod
    def _attention_row(task: Task) -> dict[str, Any]:
        return {
            "task_id": task.id,
            "title": task.title,
            "status": task.status.value,
            "provider": task.provider_name,
            "attempts": int(task.attempts),
            "error": str(task.metadata.get("last_provider_error") or "")[:700] or None,
        }

    @staticmethod
    def _scheduler_alive(scheduler: Any | None) -> bool:
        if scheduler is None:
            return False
        runner = getattr(scheduler, "_runner", None)
        return bool(runner is not None and not runner.done())

    def _health(
        self,
        *,
        completed: bool,
        paused: bool,
        current: list[dict[str, Any]],
        pending: list[Task],
        attention: list[Task],
        stale_workers: list[dict[str, Any]],
        scheduler: Any | None,
    ) -> tuple[str, list[str]]:
        if completed:
            return "complete", ["objective completed"]
        if paused:
            return "paused", ["project paused by operator"]
        reasons: list[str] = []
        if attention:
            reasons.append(f"{len(attention)} task(s) need recovery or human review")
        if stale_workers:
            reasons.append(f"{len(stale_workers)} active worker(s) exceed the adaptive stale threshold")
        alive = self._scheduler_alive(scheduler)
        if scheduler is not None and not alive:
            reasons.append("scheduler runner is not alive")
        if not current and pending and alive:
            reasons.append("scheduler is planning/dispatching pending work")
        if reasons and (attention or stale_workers or (scheduler is not None and not alive)):
            return "attention", reasons
        if current:
            return "working", [f"{len(current)} active worker(s)"]
        if pending:
            return "planning", reasons or ["pending executable work"]
        return "idle", ["no productive task currently running"]

    @staticmethod
    def _provider_stats(state: ProjectState) -> list[dict[str, Any]]:
        raw = state.metadata.get("provider_stats", {}) or {}
        rows = []
        for name, stats in raw.items():
            runs = int(stats.get("runs", 0) or 0)
            failures = int(stats.get("failures", 0) or 0)
            rows.append({
                "name": str(name),
                "runs": runs,
                "failures": failures,
                "success_rate": round((runs - failures) / runs, 3) if runs else None,
                "average_seconds": stats.get("average_seconds"),
                "cost": stats.get("cost"),
            })
        rows.sort(key=lambda row: (-int(row["runs"]), row["name"]))
        return rows
