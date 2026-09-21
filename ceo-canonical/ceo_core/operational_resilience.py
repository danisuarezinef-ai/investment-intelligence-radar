from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import blake2b
from typing import Any, Mapping
from uuid import uuid4

from .continuity import ContinuityManager
from .continuity_policy import recover_internal_continuity_decisions
from .models import ProjectState, Task, TaskStatus
from .task_roles_v2 import is_productive
from .recovery_storm_guard_v1 import RecoveryStormGuardV1
from .blocked_safe_state_v1 import is_blocked_safe, mark_blocked_safe, preserve_blocked_safe


TERMINAL_OK = {
    TaskStatus.COMPLETE,
    TaskStatus.PARTIAL_COMPLETE,
    TaskStatus.COMPLETE_WITH_UNCERTAINTY,
    TaskStatus.SUPERSEDED,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _task_has_evidence(task: Task) -> bool:
    if (task.result or "").strip():
        return True
    if task.metadata.get("artifacts") or task.metadata.get("sources") or task.metadata.get("test_ref"):
        return True
    if task.metadata.get("evidence_refs") or task.metadata.get("verification_application"):
        return True
    return False


def _unsafe_to_repeat(task: Task) -> bool:
    return bool(
        task.metadata.get("external_action")
        or task.metadata.get("irreversible")
        or task.metadata.get("destructive")
        or task.metadata.get("spending")
        or task.metadata.get("purchase")
        or task.metadata.get("public_release")
        or task.metadata.get("git_network_action")
    )


def _productive(task: Task) -> bool:
    return is_productive(task)


@dataclass(slots=True)
class ResumeReport:
    source: str
    recovered_running: int = 0
    ambiguous_external_effects: int = 0
    uncertain_completions: int = 0
    retry_exhausted: int = 0
    dependency_repairs: int = 0
    internal_decisions_recovered: int = 0
    preserved_pause: bool = False
    classifications: dict[str, int] | None = None

    def as_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["classifications"] = dict(self.classifications or {})
        return row


class ResumeCoordinator:
    """Classify persisted work conservatively before a scheduler resumes.

    The coordinator avoids the dangerous shortcut "everything RUNNING becomes retry" for
    work that may already have had an external/irreversible effect. Safe internal work is
    retried automatically; ambiguous external work is held for a real human decision.
    """

    def prepare(self, state: ProjectState, *, source: str = "restart") -> ResumeReport:
        report = ResumeReport(source=source, preserved_pause=bool(state.paused), classifications={})
        now = utcnow().isoformat()
        terminal = TERMINAL_OK

        for task in state.tasks.values():
            cls = "unchanged"
            if preserve_blocked_safe(task, source="resume_coordinator"):
                cls = "blocked_safe_preserved"
            elif task.status == TaskStatus.RUNNING:
                if _unsafe_to_repeat(task):
                    task.status = TaskStatus.NEEDS_REVIEW
                    task.metadata["resume_ambiguity"] = "external_or_irreversible_effect_may_have_occurred"
                    task.metadata["explicit_human_gate"] = True
                    task.metadata["resume_class"] = "ambiguous_external_effect"
                    report.ambiguous_external_effects += 1
                    cls = "ambiguous_external_effect"
                else:
                    task.status = TaskStatus.RETRY
                    task.metadata["recovered_after_restart"] = True
                    task.metadata["resume_class"] = "safe_retry_after_interruption"
                    task.metadata["retry_after_ts"] = 0
                    task.worker_id = None
                    report.recovered_running += 1
                    cls = "safe_retry_after_interruption"
            elif task.status == TaskStatus.RETRY and int(task.attempts) >= int(task.max_attempts):
                task.status = TaskStatus.FAILED
                task.metadata["resume_class"] = "retry_budget_exhausted"
                report.retry_exhausted += 1
                cls = "retry_budget_exhausted"
            elif task.status == TaskStatus.COMPLETE and not task.children and not _task_has_evidence(task):
                # Completion with no durable evidence is suspicious, but do not blindly repeat
                # it: the original operation may have been valid but simply under-documented.
                task.metadata["resume_uncertain_completion"] = True
                task.metadata["resume_class"] = "uncertain_completion_no_durable_evidence"
                report.uncertain_completions += 1
                cls = "uncertain_completion_no_durable_evidence"
            elif task.status == TaskStatus.BLOCKED and not task.metadata.get("paused"):
                retry_after = float(task.metadata.get("retry_after_ts", 0) or 0)
                deps_done = all(dep in state.tasks and state.tasks[dep].status in terminal for dep in task.dependencies)
                if deps_done and retry_after <= utcnow().timestamp():
                    task.status = TaskStatus.READY
                    task.metadata["resume_class"] = "dependency_block_repaired"
                    report.dependency_repairs += 1
                    cls = "dependency_block_repaired"

            task.metadata["last_resume_inspected_at"] = now
            report.classifications[cls] = int(report.classifications.get(cls, 0)) + 1

        report.internal_decisions_recovered = recover_internal_continuity_decisions(state)
        state.metadata["last_resume_report"] = {**report.as_dict(), "ts": now}
        state.metadata["resume_prepared_at"] = now
        state.metadata["resume_source"] = source
        ContinuityManager().mark_resume(state, source=source)
        return report


class LongRunningAutonomyController:
    """Durable runtime session/heartbeat state for unattended execution."""

    def start_session(self, state: ProjectState, *, source: str = "scheduler") -> dict[str, Any]:
        previous = dict(state.metadata.get("runtime_session") or {})
        unclean_previous = bool(previous and not previous.get("clean_stop", False))
        session = {
            "id": uuid4().hex,
            "started_at": utcnow().isoformat(),
            "last_heartbeat_at": utcnow().isoformat(),
            "heartbeat_seq": 0,
            "clean_stop": False,
            "source": source,
            "unclean_previous_session": unclean_previous,
            "idle_ticks": 0,
            "progress_epoch": int(state.metadata.get("runtime_progress_epoch", 0) or 0),
        }
        state.metadata["runtime_session"] = session
        state.metadata["runtime_session_starts"] = int(state.metadata.get("runtime_session_starts", 0) or 0) + 1
        if unclean_previous:
            state.metadata["unclean_runtime_restarts"] = int(state.metadata.get("unclean_runtime_restarts", 0) or 0) + 1
        return dict(session)

    def heartbeat(self, state: ProjectState, *, active_count: int, ready_count: int) -> dict[str, Any]:
        session = state.metadata.setdefault("runtime_session", {})
        session["last_heartbeat_at"] = utcnow().isoformat()
        session["heartbeat_seq"] = int(session.get("heartbeat_seq", 0) or 0) + 1
        session["active_workers"] = int(active_count)
        session["ready_tasks"] = int(ready_count)

        completed = sum(1 for t in state.leaf_tasks if _productive(t) and t.status in TERMINAL_OK)
        evidence = len(state.metadata.get("evidence_ledger_v1", []) or [])
        token = f"{completed}:{evidence}:{len(state.tasks)}:{state.progress}"
        prior = str(session.get("progress_token") or "")
        if token != prior:
            session["progress_token"] = token
            session["last_progress_at"] = utcnow().isoformat()
            session["idle_ticks"] = 0
            state.metadata["runtime_progress_epoch"] = int(state.metadata.get("runtime_progress_epoch", 0) or 0) + 1
            session["progress_epoch"] = state.metadata["runtime_progress_epoch"]
        elif not active_count and not ready_count and state.completed_at is None and not state.paused:
            session["idle_ticks"] = int(session.get("idle_ticks", 0) or 0) + 1
        else:
            session["idle_ticks"] = 0
        return dict(session)

    @staticmethod
    def needs_progress_kick(state: ProjectState, *, threshold_ticks: int = 5) -> bool:
        if state.paused or state.completed_at is not None:
            return False
        session = state.metadata.get("runtime_session") or {}
        return int(session.get("idle_ticks", 0) or 0) >= max(1, int(threshold_ticks))

    def stop_session(self, state: ProjectState, *, clean: bool = True) -> dict[str, Any]:
        session = state.metadata.setdefault("runtime_session", {})
        session["clean_stop"] = bool(clean)
        session["stopped_at"] = utcnow().isoformat()
        return dict(session)

    def record_dispatch_intent(self, state: ProjectState, tasks: list[Task]) -> dict[str, Any]:
        session = state.metadata.setdefault("runtime_session", {})
        session_id = str(session.get("id") or "unknown")
        rows = state.metadata.setdefault("dispatch_ledger", [])
        batch_id = uuid4().hex
        ts = utcnow().isoformat()
        for task in tasks:
            token = blake2b(f"{state.id}:{session_id}:{task.id}:{task.attempts}".encode(), digest_size=12).hexdigest()
            task.metadata["dispatch_token"] = token
            task.metadata["dispatch_session_id"] = session_id
            task.metadata["dispatch_batch_id"] = batch_id
            task.metadata["dispatch_persisted_at"] = ts
            rows.append({"ts": ts, "session_id": session_id, "batch_id": batch_id, "task_id": task.id, "attempt": task.attempts, "token": token})
        del rows[:-300]
        return {"batch_id": batch_id, "count": len(tasks), "session_id": session_id}


class WorkerRecoverySupervisor:
    """Reconcile live worker bookkeeping with durable task state."""

    def reconcile(
        self,
        state: ProjectState,
        *,
        active: Mapping[str, Any],
        providers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        providers = providers or {}
        now = utcnow()
        cancel: list[str] = []
        recovered: list[dict[str, Any]] = []
        storm = RecoveryStormGuardV1()

        active_ids = set(active)
        for task in state.tasks.values():
            if task.status != TaskStatus.RUNNING or task.id in active_ids:
                continue
            if _unsafe_to_repeat(task):
                task.status = TaskStatus.NEEDS_REVIEW
                task.metadata["explicit_human_gate"] = True
                task.metadata["live_recovery_reason"] = "orphan_running_external_effect"
                recovered.append({"task_id": task.id, "action": "human_gate", "reason": "orphan_running_external_effect"})
            else:
                reason = "orphan_running_without_live_future"
                decision = storm.record_task_recovery(task, reason=reason, provider=task.provider_name)
                task.metadata["live_recovery_reason"] = reason
                if decision["must_change_strategy"]:
                    failed_provider = task.provider_name
                    task.metadata["strategy_change_requested"] = True
                    task.metadata["strategy_change_from"] = failed_provider
                    task.metadata["strategy_change_applied"] = False
                    if task.metadata.get("local_fallback_kind") == "goal_lock":
                        task.metadata["preferred_kind"] = "local"
                        task.metadata["preferred_provider"] = "ceo-local-goal-lock"
                        task.metadata["recovery_strategy"] = "local_goal_lock"
                    elif failed_provider:
                        avoid = task.metadata.setdefault("avoid_providers", [])
                        if failed_provider not in avoid:
                            avoid.append(failed_provider)
                        task.metadata["recovery_strategy"] = "alternate_provider_requested"
                if decision["exhausted"] or int(task.attempts) >= max(1, int(task.max_attempts)):
                    mark_blocked_safe(task, "worker_recovery_budget_exhausted", source="worker_recovery_supervisor")
                    action = "blocked_safe"
                else:
                    task.status = TaskStatus.RETRY
                    task.metadata["retry_after_ts"] = 0
                    action = "retry_strategy_change_requested" if decision["must_change_strategy"] else "retry"
                recovered.append({"task_id": task.id, "action": action, "reason": reason, "recovery_count": decision["count"], "repeat_count": decision["repeat_count"]})

        for task_id, future in active.items():
            task = state.tasks.get(task_id)
            if task is None or getattr(future, "done", lambda: False)():
                continue
            if task.started_at is None:
                continue
            started = task.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            elapsed = max(0.0, (now - started.astimezone(timezone.utc)).total_seconds())
            provider_timeout = float(task.metadata.get("provider_timeout_seconds", state.metadata.get("provider_timeout_seconds", 180.0)) or 180.0)
            hard_timeout = max(30.0, min(3600.0, provider_timeout * 1.35 + 20.0))
            if elapsed <= hard_timeout:
                continue
            cancel.append(task_id)
            task.metadata["worker_watchdog_timeout"] = {
                "elapsed_seconds": round(elapsed, 1),
                "hard_timeout_seconds": round(hard_timeout, 1),
                "provider": providers.get(task_id) or task.provider_name,
                "ts": now.isoformat(),
            }
            task.metadata["last_provider_error"] = f"Worker watchdog exceeded {hard_timeout:.0f}s"
            if _unsafe_to_repeat(task):
                task.status = TaskStatus.NEEDS_REVIEW
                task.metadata["explicit_human_gate"] = True
                action = "human_gate"
                decision = None
            else:
                reason = "worker_watchdog_timeout"
                decision = storm.record_task_recovery(task, reason=reason, provider=providers.get(task_id) or task.provider_name)
                if decision["must_change_strategy"]:
                    failed_provider = providers.get(task_id) or task.provider_name
                    task.metadata["strategy_change_requested"] = True
                    task.metadata["strategy_change_from"] = failed_provider
                    task.metadata["strategy_change_applied"] = False
                    if task.metadata.get("local_fallback_kind") == "goal_lock":
                        task.metadata["preferred_kind"] = "local"
                        task.metadata["preferred_provider"] = "ceo-local-goal-lock"
                        task.metadata["recovery_strategy"] = "local_goal_lock"
                    elif failed_provider:
                        avoid = task.metadata.setdefault("avoid_providers", [])
                        if failed_provider not in avoid:
                            avoid.append(failed_provider)
                        task.metadata["recovery_strategy"] = "alternate_provider_requested"
                if decision["exhausted"] or int(task.attempts) >= max(1, int(task.max_attempts)):
                    mark_blocked_safe(task, "worker_recovery_budget_exhausted", source="worker_watchdog")
                    action = "blocked_safe"
                else:
                    task.status = TaskStatus.RETRY
                    action = "retry_strategy_change_requested" if decision["must_change_strategy"] else "retry"
                task.metadata["retry_after_ts"] = 0
            row = {"task_id": task.id, "action": action, "reason": "worker_watchdog_timeout"}
            if decision is not None:
                row.update({"recovery_count": decision["count"], "repeat_count": decision["repeat_count"]})
            recovered.append(row)

        if recovered:
            history = state.metadata.setdefault("worker_recovery_history", [])
            history.extend({"ts": now.isoformat(), **row} for row in recovered)
            del history[:-200]
            state.metadata["worker_recoveries"] = int(state.metadata.get("worker_recoveries", 0) or 0) + len(recovered)
        storm_report = storm.assess(state)
        return {"cancel_task_ids": cancel, "recovered": recovered, "storm": storm_report.to_dict()}


@dataclass(slots=True)
class AdaptiveConcurrencyDecision:
    target: int
    base_target: int
    learned_target: int
    cpu_percent: float
    ram_percent: float
    failure_rate: float
    queued: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdaptiveSchedulerController:
    """Smooth, resource-aware concurrency target with fast backoff and slow ramp-up."""

    def decide(
        self,
        state: ProjectState,
        governor: Any,
        *,
        learned_target: int | None = None,
        current_active: int = 0,
    ) -> AdaptiveConcurrencyDecision:
        pstats = state.metadata.get("provider_stats", {}) or {}
        runs = sum(int(v.get("runs", 0) or 0) for v in pstats.values())
        failures = sum(int(v.get("failures", 0) or 0) for v in pstats.values())
        failure_rate = failures / max(1, runs)
        base = max(1, int(governor.adaptive_target(state.power_percent, failure_rate=failure_rate)))
        learned = max(1, int(learned_target or base))
        target = min(base, learned)
        snap = governor.snapshot()
        cpu = float(snap.get("cpu_percent", 0.0) or 0.0)
        ram = float(snap.get("ram_percent", 0.0) or 0.0)
        queued = sum(1 for t in state.leaf_tasks if t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.WAITING})
        reasons: list[str] = []

        if cpu >= 95.0 or ram >= 94.0:
            target = max(1, min(target, max(1, current_active // 2 or 1)))
            reasons.append("hard_resource_backoff")
        elif cpu >= 85.0 or ram >= 88.0:
            target = max(1, int(target * 0.65))
            reasons.append("resource_backoff")
        elif failure_rate >= 0.30:
            target = max(1, int(target * 0.50))
            reasons.append("failure_backoff")
        elif failure_rate >= 0.12:
            target = max(1, int(target * 0.75))
            reasons.append("failure_caution")
        elif queued > target and cpu < 70.0 and ram < 78.0:
            reasons.append("healthy_ramp")

        previous = int((state.metadata.get("adaptive_scheduler") or {}).get("target", 0) or 0)
        if previous > 0:
            if target > previous:
                target = min(target, previous + 1)
            elif target < previous:
                # Backoff may be fast, but avoid collapsing more than 75% in one ordinary tick.
                target = max(target, max(1, previous // 4))
        target = max(1, min(int(snap.get("hardware_worker_capacity", target) or target), target))
        decision = AdaptiveConcurrencyDecision(
            target=target,
            base_target=base,
            learned_target=learned,
            cpu_percent=round(cpu, 2),
            ram_percent=round(ram, 2),
            failure_rate=round(failure_rate, 4),
            queued=queued,
            reason="+".join(reasons) or "steady",
        )
        state.metadata["adaptive_scheduler"] = {**decision.as_dict(), "ts": utcnow().isoformat()}
        hist = state.metadata.setdefault("adaptive_scheduler_history", [])
        hist.append(dict(state.metadata["adaptive_scheduler"]))
        del hist[:-100]
        return decision


def resilience_snapshot(state: ProjectState) -> dict[str, Any]:
    return {
        "runtime_session": dict(state.metadata.get("runtime_session") or {}),
        "last_resume_report": dict(state.metadata.get("last_resume_report") or {}),
        "worker_recoveries": int(state.metadata.get("worker_recoveries", 0) or 0),
        "adaptive_scheduler": dict(state.metadata.get("adaptive_scheduler") or {}),
        "unclean_runtime_restarts": int(state.metadata.get("unclean_runtime_restarts", 0) or 0),
    }
