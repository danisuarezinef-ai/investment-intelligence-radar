from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256

from .autonomy import AutonomyEngine
from .completion import CompletionEngine
from .directors import ProjectDirector
from .knowledge_v2 import KnowledgeIntegrationEngine
from .models import ProjectState, Task, TaskStatus
from .blocked_safe_state_v1 import is_blocked_safe
from .replanning import ReplanningEngine
from .self_improvement import SelfEvaluationEngine
from .recursive_planning import RecursivePlanningEngine
from .liveness import ProductiveProgressWatchdog, RecoveryIncidentManager
from .continuity_policy import is_goal_audit_lineage, is_internal_continuity_task, protected_human_gate, recover_internal_continuity_decisions
from .task_roles_v2 import is_productive, is_internal


class AutonomousProjectLoop:
    """High-level control cycle above the worker scheduler.

    Besides periodic strategic replanning, the loop owns a bounded anti-deadlock
    watchdog.  A project that is not complete but has no runnable work must either
    repair its plan or create one explicit recovery unit instead of silently idling.
    """

    def __init__(self) -> None:
        self.director = ProjectDirector()
        self.replanner = ReplanningEngine()
        self.knowledge = KnowledgeIntegrationEngine()
        self.autonomy = AutonomyEngine()
        self.self_eval = SelfEvaluationEngine()
        self.recursive_planner = RecursivePlanningEngine()
        self.completion = CompletionEngine()
        self.liveness = ProductiveProgressWatchdog()
        self.recovery_incidents = RecoveryIncidentManager()

    def tick(self, state: ProjectState, *, decomposer=None) -> dict:
        tree = self.director.rebuild(state)
        knowledge = self.knowledge.rebuild_indexes(state)
        for decision in state.decisions.values():
            if decision.status.value == "open":
                self.autonomy.annotate(state, decision)
        actions = self.replanner.inspect(state)
        changed = self.replanner.apply(state, actions, decomposer=decomposer)
        planning = self.recursive_planner.refine(
            state, max_splits=max(1, min(8, state.depth_percent // 15 + 1))
        )
        watchdog = self.ensure_progress(state, decomposer=decomposer)
        state.metadata["autonomous_loop"] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "directors": len(tree),
            "knowledge": asdict(knowledge),
            "replan_actions": len(actions),
            "replan_changes": changed,
            "recursive_planning": asdict(planning),
            "watchdog": watchdog,
        }
        return dict(state.metadata["autonomous_loop"])


    @staticmethod
    def _is_goal_audit_lineage(state: ProjectState, task: Task) -> bool:
        return is_goal_audit_lineage(state, task)

    def _repair_legacy_split_goal_audits(self, state: ProjectState) -> dict:
        """Supersede malformed split descendants created by older builds.

        A continuity audit is a protocol message, not divisible domain work. Older
        recursive planners could repeatedly split it into titles such as
        ``... part 2/6 · part 3/8 ...`` and lose the audit marker on descendants.
        Such descendants cannot safely be resumed; retire them and let the normal
        watchdog create one fresh atomic audit on the next cycle.
        """
        repaired: list[str] = []
        for task in state.leaf_tasks:
            if not self._is_goal_audit_lineage(state, task):
                continue
            malformed = bool(task.metadata.get("adaptive_split_of")) or " · part " in str(task.title or "")
            if not malformed:
                continue
            if task.status == TaskStatus.RUNNING:
                continue
            if task.status not in {TaskStatus.SUPERSEDED, TaskStatus.COMPLETE}:
                task.status = TaskStatus.SUPERSEDED
                task.metadata["continuity_lineage_repaired"] = datetime.now(timezone.utc).isoformat()
                task.metadata["superseded_reason"] = "legacy_split_goal_audit_control_plane_corruption"
                repaired.append(task.id)
        if repaired:
            hist = state.metadata.setdefault("goal_continuity_lineage_repairs", [])
            hist.append({"ts": datetime.now(timezone.utc).isoformat(), "task_ids": repaired})
            del hist[:-20]
        return {"changed": len(repaired), "task_ids": repaired}


    @staticmethod
    def _completed_domain_count(state: ProjectState) -> int:
        terminal = {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}
        return sum(
            1 for t in state.leaf_tasks
            if t.status in terminal
            and not t.metadata.get("goal_continuity_audit")
            and not t.metadata.get("autonomy_recovery")
            and not t.metadata.get("control_plane_atomic")
        )

    def _refresh_recovery_budget_after_progress(self, state: ProjectState) -> dict:
        """Reset stale deadlock budgets after concrete project progress.

        DEV16 still kept a lifetime recovery counter. After several historical
        recoveries, a later and unrelated blocker could immediately enter
        ``bounded_stall`` even though the project had since completed many real
        tasks. Recovery budgets are now progress-epoch scoped instead.
        """
        completed = self._completed_domain_count(state)
        watermark = int(state.metadata.get("autonomy_recovery_progress_watermark", 0))
        if completed <= watermark:
            return {"changed": 0, "completed": completed, "watermark": watermark}
        retired = []
        for task in state.leaf_tasks:
            if task.metadata.get("autonomy_recovery") and task.status == TaskStatus.FAILED:
                task.status = TaskStatus.SUPERSEDED
                task.metadata["superseded_reason"] = "historical_recovery_failure_after_later_project_progress"
                task.metadata["superseded_after_progress"] = datetime.now(timezone.utc).isoformat()
                retired.append(task.id)
        state.metadata["autonomy_recovery_progress_watermark"] = completed
        state.metadata["autonomy_recovery_tasks_created_by_signature"] = {}
        state.metadata["autonomy_recovery_tasks_created"] = 0  # legacy compatibility / UI only
        state.metadata["autonomy_stall_cycles"] = 0
        state.metadata.pop("autonomy_stalled", None)
        hist = state.metadata.setdefault("autonomy_recovery_budget_resets", [])
        hist.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "completed_domain_tasks": completed,
            "previous_watermark": watermark,
            "retired_failed_recoveries": retired,
        })
        del hist[:-30]
        return {"changed": 1 + len(retired), "completed": completed, "watermark": completed, "retired": retired}

    def _recycle_terminal_goal_audit(self, state: ProjectState) -> dict:
        """Retire failed/blocked internal audits so a fresh atomic audit can be created.

        A goal-continuity audit is control-plane work. A provider failure or stale
        dependency may leave it FAILED/BLOCKED, but that must not become a permanent
        project-level deadlock or a human decision.
        """
        open_decision_ids = {
            d.id for d in state.decisions.values() if getattr(d.status, "value", d.status) == "open"
        }
        for audit in state.leaf_tasks:
            if not self._is_goal_audit_lineage(state, audit):
                continue
            if audit.status not in {TaskStatus.FAILED, TaskStatus.BLOCKED}:
                continue
            if audit.metadata.get("waiting_provider_v1"):
                continue
            retry_after = float(audit.metadata.get("retry_after_ts", 0) or 0)
            if retry_after > datetime.now(timezone.utc).timestamp():
                continue
            decision_id = str(audit.metadata.get("decision_id") or "")
            if decision_id and decision_id in open_decision_ids:
                continue
            prior = audit.status.value
            audit.status = TaskStatus.SUPERSEDED
            audit.metadata["continuity_terminal_auto_recycled"] = datetime.now(timezone.utc).isoformat()
            audit.metadata["superseded_reason"] = f"internal_goal_audit_{prior}_recreate_fresh_atomic_audit"
            state.metadata["autonomy_stall_cycles"] = 0
            state.metadata.pop("autonomy_stalled", None)
            return {"changed": 1, "task_id": audit.id, "prior_status": prior}
        return {"changed": 0}

    @staticmethod
    def _is_control_plane_task(task: Task) -> bool:
        return is_internal(task)

    def _repair_recovery_churn(self, state: ProjectState) -> dict:
        """Repair historical recovery churn without erasing domain history.

        DEV188 could successfully complete a recovery wrapper for a BLOCKED target
        yet leave that target BLOCKED forever because apply_recovery_result only
        superseded FAILED targets. It also allowed failed control-plane wrappers to
        accumulate as project blockers. This migration is idempotent and runs before
        the watchdog decides whether more recovery work is needed.
        """
        changed = 0
        resolved_targets: list[str] = []
        retired_control: list[str] = []

        # Replay already-completed recovery evidence onto unresolved targets.
        for recovery in list(state.leaf_tasks):
            if not recovery.metadata.get("autonomy_recovery") or recovery.status != TaskStatus.COMPLETE:
                continue
            for target_id in [str(x) for x in recovery.metadata.get("recovery_targets", [])]:
                target = state.tasks.get(target_id)
                if not target or target.status not in {TaskStatus.FAILED, TaskStatus.BLOCKED}:
                    continue
                target.status = TaskStatus.SUPERSEDED
                target.metadata["superseded_by_autonomy_recovery"] = recovery.id
                target.metadata["recovery_result_excerpt"] = (recovery.result or "")[:800]
                target.metadata["dev189_recovery_churn_repaired"] = datetime.now(timezone.utc).isoformat()
                resolved_targets.append(target.id)
                changed += 1

        # Failed/blocked/needs-review recovery wrappers are historical control-plane
        # attempts, not new domain requirements. Retire them so their generated IDs
        # cannot create fresh incident signatures forever. Keep READY/RUNNING/RETRY
        # wrappers intact because they may be the currently active bounded attempt.
        for task in list(state.leaf_tasks):
            if not task.metadata.get("autonomy_recovery"):
                continue
            if task.status not in {TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.NEEDS_REVIEW}:
                continue
            task.status = TaskStatus.SUPERSEDED
            task.metadata["superseded_reason"] = "dev189_historical_control_recovery_retired"
            task.metadata["dev189_recovery_churn_repaired"] = datetime.now(timezone.utc).isoformat()
            retired_control.append(task.id)
            changed += 1

        if changed:
            state.metadata["autonomy_stall_cycles"] = 0
            state.metadata.pop("autonomy_stalled", None)
            state.metadata.pop("autonomy_stall_signature", None)
            # Preserve incident state: the incident ladder may already have advanced
            # from retry -> fresh_worker -> clean_audit, and resetting it here would
            # recreate the very retry loop DEV189 is designed to stop. Historical
            # incident rows are harmless because new signatures ignore control tasks.
            state.metadata["dev189_recovery_churn_repair"] = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "resolved_targets": resolved_targets,
                "retired_control": retired_control,
                "changed": changed,
            }
        return {"changed": changed, "resolved_targets": resolved_targets, "retired_control": retired_control}

    @staticmethod
    def _actionable_blockers(state: ProjectState, assessment_blockers: list[str]) -> list[str]:
        """Return stable blockers that can drive recovery, excluding final-audit facts."""
        domain = [t for t in state.leaf_tasks if not AutonomousProjectLoop._is_control_plane_task(t)]
        problem = [
            f"{t.id}:{t.status.value}" for t in domain
            if t.status in {TaskStatus.FAILED, TaskStatus.BLOCKED}
            and not t.metadata.get("explicit_human_gate")
        ]
        if problem:
            return sorted(problem)
        deferred_prefixes = (
            "criterion:", "deliverable:", "goal_audit_required",
            "confidence_below_threshold", "unresolved_critical_claims:"
        )
        filtered = [b for b in assessment_blockers if not str(b).startswith(deferred_prefixes)]
        return filtered or ["project incomplete with no runnable productive work"]

    def ensure_progress(self, state: ProjectState, *, decomposer=None) -> dict:
        if state.paused or state.completed_at is not None:
            return {"status": "inactive", "created": 0, "changed": 0}

        # DEV215/218: when the hardening supervisor opens the control-plane
        # circuit, do not manufacture more recovery wrappers. Productive work
        # remains dispatchable by the normal scheduler; protected human gates
        # remain untouched.
        if state.metadata.get("suppress_new_internal_recovery"):
            productive_runnable = [
                t for t in state.leaf_tasks
                if is_productive(t, state) and t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING}
            ]
            if productive_runnable:
                return {"status": "work_available", "created": 0, "changed": 0, "hardening_circuit": True}
            return {
                "status": "control_churn_circuit_open",
                "created": 0,
                "changed": 0,
                "reason": "internal recovery budget exhausted without productive progress",
            }

        churn_repair = self._repair_recovery_churn(state)
        if churn_repair.get("changed"):
            return {
                "status": "recovery_churn_repaired",
                "created": 0,
                "changed": churn_repair["changed"],
                "resolved_targets": churn_repair.get("resolved_targets", []),
                "retired_control": churn_repair.get("retired_control", []),
            }

        recovered_decisions = recover_internal_continuity_decisions(state)
        if recovered_decisions:
            return {
                "status": "internal_goal_audit_decision_auto_recovered",
                "created": 0,
                "changed": recovered_decisions,
            }

        # Liveness invariant: any concrete domain progress starts a new recovery
        # epoch. Historical recovery exhaustion must never poison later work.
        progress_reset = self._refresh_recovery_budget_after_progress(state)
        if progress_reset.get("changed"):
            self.recovery_incidents.close_after_progress(state)
        liveness = self.liveness.assess(state, persist=True)

        legacy_repair = self._repair_legacy_split_goal_audits(state)
        if legacy_repair["changed"]:
            state.metadata["autonomy_stall_cycles"] = 0
            return {
                "status": "legacy_goal_audit_lineage_repaired",
                "created": 0,
                "changed": legacy_repair["changed"],
                "task_ids": legacy_repair["task_ids"],
            }

        recycled_audit = self._recycle_terminal_goal_audit(state)
        if recycled_audit["changed"]:
            return {
                "status": "goal_audit_terminal_auto_recycled",
                "created": 0,
                "changed": 1,
                "task_id": recycled_audit["task_id"],
                "prior_status": recycled_audit["prior_status"],
            }

        productive_runnable = [
            t for t in state.leaf_tasks
            if is_productive(t, state)
            and t.status in {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.RETRY}
        ]
        if productive_runnable:
            state.metadata["autonomy_stall_cycles"] = 0
            state.metadata.pop("autonomy_stalled", None)
            return {
                "status": "productive_work_available",
                "created": 0,
                "changed": 0,
                "productive_task_ids": [t.id for t in productive_runnable[:20]],
            }

        internal_runnable = [
            t for t in state.leaf_tasks
            if is_internal(t, state)
            and t.status in {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.RETRY}
        ]
        if internal_runnable:
            state.metadata["control_only_runtime_detected"] = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "task_ids": [t.id for t in internal_runnable[:20]],
                "count": len(internal_runnable),
            }
            # Deliberately continue. A control-only queue must not suppress
            # productive reseeding/replanning for an unfinished objective.

        # Goal-continuity audits are internal control work, not a human decision.
        # Older scheduler heuristics could strand such an audit in NEEDS_REVIEW
        # (for example after a cognitive early-abort), leaving the project idle.
        # Recover it automatically unless it is explicitly tied to an open human
        # decision.  This also repairs already-persisted projects after upgrade.
        open_decision_ids = {
            d.id for d in state.decisions.values() if getattr(d.status, "value", d.status) == "open"
        }
        for audit in state.leaf_tasks:
            if not is_internal_continuity_task(state, audit) or audit.status != TaskStatus.NEEDS_REVIEW:
                continue
            if protected_human_gate(audit):
                continue
            decision_id = str(audit.metadata.get("decision_id") or "")
            if decision_id and decision_id in open_decision_ids:
                continue
            recoveries = int(audit.metadata.get("continuity_review_auto_recoveries", 0))
            max_recoveries = int(state.metadata.get("max_continuity_review_auto_recoveries", 4))
            if recoveries >= max_recoveries:
                audit.status = TaskStatus.SUPERSEDED
                audit.metadata["continuity_review_recovery_exhausted"] = datetime.now(timezone.utc).isoformat()
                audit.metadata["superseded_reason"] = "control_plane_retry_budget_exhausted_recreate_fresh_audit"
                state.metadata["autonomy_stall_cycles"] = 0
                return {
                    "status": "goal_audit_review_recovery_exhausted",
                    "created": 0,
                    "changed": 1,
                    "task_id": audit.id,
                }
            audit.metadata["continuity_review_auto_recoveries"] = recoveries + 1
            audit.metadata["continuity_review_auto_recovered"] = datetime.now(timezone.utc).isoformat()
            audit.metadata.pop("cognitive_early_abort", None)
            audit.max_attempts = max(int(audit.max_attempts), int(audit.attempts) + 2)
            audit.status = TaskStatus.RETRY
            audit.metadata["next_instruction"] = (
                "This is an internal continuity audit, not a human-review task. Continue autonomously. "
                "If the locked goal is incomplete, spawn 3-8 concrete executable follow-up tasks. "
                "Do not request human review merely because the current batch ended."
            )
            state.metadata["autonomy_stall_cycles"] = 0
            state.metadata.pop("autonomy_stalled", None)
            return {
                "status": "goal_audit_review_auto_recovered",
                "created": 0,
                "changed": 1,
                "task_id": audit.id,
            }

        # If the current finite batch is exhausted, do not confuse "no runnable
        # tasks" with "the locked goal is finished".  Real-work mode requires an
        # explicit goal audit.  That audit either proves completion or asks the AI
        # controller to spawn the next concrete work batch.
        if bool(state.metadata.get("require_goal_audit", False)) and not bool(state.metadata.get("goal_audit_passed", False)):
            terminal = self.completion.TERMINAL
            leaves = list(state.leaf_tasks)
            productive_leaves = [t for t in leaves if not self._is_control_plane_task(t)]
            productive_successes = self._completed_domain_count(state)
            # A final/continuity audit is only meaningful after real domain progress.
            # At 0% or while domain blockers remain, recovery/replanning owns the next
            # step; the completion gate must not become the work item itself.
            batch_exhausted = (
                bool(productive_leaves)
                and productive_successes > 0
                and all(t.status in terminal for t in productive_leaves)
            )
            if batch_exhausted:
                existing_audits = [
                    t for t in leaves
                    if t.metadata.get("goal_continuity_audit")
                    and t.status not in {TaskStatus.SUPERSEDED, TaskStatus.FAILED, TaskStatus.COMPLETE}
                ]
                if not existing_audits:
                    generation = int(state.metadata.get("goal_continuity_generation", 0)) + 1
                    max_generation = int(state.metadata.get("max_goal_continuity_generations", 24) or 24)
                    if generation > max_generation:
                        last = dict(state.metadata.get("last_goal_audit_rejection") or {})
                        state.metadata["autonomy_stalled"] = {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "action": "closure_convergence_exhausted",
                            "generation": generation - 1,
                            "max_generation": max_generation,
                            "gaps": list(last.get("gaps") or [])[:20],
                        }
                        state.metadata["operator_productivity_state"] = "BLOQUEADO"
                        state.metadata["operator_block_reason"] = (
                            f"Cierre acotado agotado tras {max_generation} auditorías; "
                            "CEO no repetirá el bucle indefinidamente."
                        )
                        return {
                            "status": "closure_bounded_stall",
                            "created": 0,
                            "changed": 0,
                            "generation": generation - 1,
                            "max_generation": max_generation,
                            "gaps": list(last.get("gaps") or [])[:20],
                        }
                    audit = Task(
                        title=f"Goal continuity audit #{generation}: plan the next autonomous work batch",
                        description=(
                            "Audit the LOCKED PROJECT GOAL against all completed results, evidence, artifacts and unresolved gaps. "
                            "Do not treat exhaustion of the current finite task list as project completion. "
                            "If the locked goal is NOT fully achieved, end with CEO_RESULT status=spawn and provide 3-8 concrete, "
                            "non-duplicate, executable follow-up tasks in followups. Prefer the highest-impact next work that can be "
                            "completed autonomously. If and only if the full locked goal is actually achieved with auditable evidence, "
                            "include the exact line 'CEO_GOAL_AUDIT: PASS' in the substantive response and end with status=complete. "
                            "A PASS MUST include evidence_refs in CEO_RESULT: 2 or more IDs of EXISTING completed NON-AUDIT tasks, "
                            "including at least one grounded artifact/test/source/verification task. Never invent task IDs. "
                            "The audit itself is NOT evidence. If objective-specific success criteria or deliverables are still missing, "
                            "you MUST spawn follow-up work to define and verify them instead of passing. "
                            "Never claim tests, file changes, production proof or external effects that were not actually performed."
                        ),
                        priority=100,
                        status=TaskStatus.READY,
                        estimated_seconds=45.0,
                        max_attempts=6,
                        required_capabilities=["reasoning"],
                        acceptance_criteria=[
                            "If the goal is incomplete, 3-8 executable follow-up tasks are spawned",
                            "If the goal is declared complete, CEO_GOAL_AUDIT: PASS is backed by explicit evidence",
                            "No completed work or safety constraint is silently discarded",
                        ],
                        metadata={
                            "goal_continuity_audit": True,
                            "goal_continuity_generation": generation,
                            "control_plane_atomic": True,
                            "do_not_split": True,
                            "critical_followups": True,
                            "preferred_kind": "api",
                        },
                    )
                    state.tasks[audit.id] = audit
                    state.root_task_ids.append(audit.id)
                    state.metadata["goal_continuity_generation"] = generation
                    state.metadata["autonomy_stall_cycles"] = 0
                    state.metadata.pop("autonomy_stalled", None)
                    return {"status": "goal_audit_created", "created": 1, "changed": 0, "task_id": audit.id}

        # DEV305: an external-provider wait is a legitimate executable route state,
        # not an autonomy stall. We deliberately reach this point only AFTER the
        # goal-continuity-audit creation block above, so a 99% project may still
        # create its final audit locally. Once all remaining nonterminal work is
        # waiting on a provider, stop recovery/replanning churn until its retry time.
        provider_wait = dict(state.metadata.get("provider_wait_v1") or {})
        provider_wait_tasks = [
            t for t in state.leaf_tasks
            if t.status == TaskStatus.BLOCKED
            and bool(t.metadata.get("waiting_provider_v1"))
        ]
        if provider_wait.get("active") and provider_wait_tasks:
            state.metadata["autonomy_stall_cycles"] = 0
            state.metadata.pop("autonomy_stalled", None)
            state.metadata.pop("productive_stall_escape_required", None)
            state.metadata.pop("suppress_new_internal_recovery", None)
            state.metadata["endgame_route_v1"] = {
                "status": "waiting_provider",
                "task_ids": [t.id for t in provider_wait_tasks[:20]],
                "category": str(provider_wait.get("category") or "provider_unavailable"),
                "retry_after_ts": provider_wait.get("retry_after_ts"),
            }
            return {
                "status": "waiting_provider",
                "created": 0,
                "changed": 0,
                "task_ids": [t.id for t in provider_wait_tasks[:20]],
            }

        # Recovery ordering is deliberate: do not jump directly to replanning.
        # The incident ladder below owns retry -> fresh worker -> clean audit ->
        # partial replan -> global replan, which keeps recovery bounded and auditable.
        assessment = self.completion.assess(state)
        if assessment.complete:
            state.metadata["autonomy_stall_cycles"] = 0
            return {"status": "completion_ready", "created": 0, "changed": 0}

        blockers = self._actionable_blockers(state, list(assessment.blockers))
        hard_blocked = [
            t for t in state.leaf_tasks
            if is_blocked_safe(t) and t.status == TaskStatus.BLOCKED
        ]
        other_recoverable = [
            t for t in state.leaf_tasks
            if t.status in {TaskStatus.FAILED, TaskStatus.BLOCKED}
            and not is_blocked_safe(t)
            and not t.metadata.get("explicit_human_gate")
        ]
        if hard_blocked and not other_recoverable:
            state.metadata["autonomy_stalled"] = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "blockers": blockers[:50],
                "hard_blocked_task_ids": [t.id for t in hard_blocked[:50]],
                "action": "blocked_safe_requires_explicit_strategy_or_operator_review",
            }
            state.metadata["suppress_new_internal_recovery"] = True
            state.metadata["operator_productivity_state"] = "BLOQUEADO"
            return {
                "status": "bounded_stall", "created": 0, "changed": 0,
                "blockers": blockers[:20], "hard_blocked": len(hard_blocked),
                "liveness": liveness.as_dict(),
            }
        signature = sha256("|".join(sorted(blockers)).encode()).hexdigest()[:16]
        previous = state.metadata.get("autonomy_stall_signature")
        cycles = int(state.metadata.get("autonomy_stall_cycles", 0)) + 1 if previous == signature else 1
        state.metadata["autonomy_stall_signature"] = signature
        state.metadata["autonomy_stall_cycles"] = cycles

        incident = self.recovery_incidents.get_or_create(state, signature, blockers)
        stage = self.recovery_incidents.stage(incident)
        existing = [
            t for t in state.leaf_tasks
            if t.metadata.get("recovery_incident_id") == incident["id"]
            and t.status in {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.RETRY}
        ]
        if existing:
            return {
                "status": "recovery_in_progress",
                "created": 0,
                "changed": 0,
                "incident_id": incident["id"],
                "recovery_stage": stage,
                "liveness": liveness.as_dict(),
            }

        # One natural watchdog cycle is deliberately left to dependency refresh/backoff.
        if cycles < 2:
            return {
                "status": "watching",
                "created": 0,
                "changed": 0,
                "blockers": blockers[:20],
                "incident_id": incident["id"],
                "recovery_stage": stage,
                "liveness": liveness.as_dict(),
            }

        # Stage 1: smallest possible retry wrapper.  Keep the failed leaf immutable
        # until retry evidence succeeds; this preserves history and allows the normal
        # recovery-result linker to supersede it only after a verified completion.
        if stage == "retry":
            candidates = [
                t for t in state.leaf_tasks
                if t.status in {TaskStatus.FAILED, TaskStatus.BLOCKED}
                and not self._is_goal_audit_lineage(state, t)
                and not t.metadata.get("explicit_human_gate")
                and not is_blocked_safe(t)
            ]
            if candidates:
                target = sorted(candidates, key=lambda t: (-int(t.priority), t.created_at))[0]
                task = Task(
                    title=f"Retry blocked work · {target.title}",
                    description=(
                        "Retry the smallest blocked work unit using the existing durable context. "
                        "Do not broaden scope. If the same execution path fails again, preserve "
                        "diagnostics so the next recovery stage can use a fresh worker context."
                    ),
                    priority=100,
                    status=TaskStatus.READY,
                    estimated_seconds=max(10.0, float(target.estimated_seconds or 0.0)),
                    max_attempts=2,
                    required_capabilities=list(target.required_capabilities or ["reasoning"]),
                    acceptance_criteria=list(target.acceptance_criteria) or ["The blocked unit is resolved or a concrete failure diagnostic is produced"],
                    metadata={
                        "autonomy_recovery": True,
                        "control_plane_atomic": True,
                        "do_not_split": True,
                        "blocker_signature": signature,
                        "blockers": blockers[:50],
                        "recovery_incident_id": incident["id"],
                        "recovery_stage": "retry",
                        "recovery_targets": [target.id],
                        "preferred_kind": target.metadata.get("preferred_kind", "api"),
                    },
                )
                state.tasks[task.id] = task
                state.root_task_ids.append(task.id)
                self.recovery_incidents.record_attempt(incident, outcome="retry_wrapper_created")
                self.recovery_incidents.escalate(incident, reason="retry stage issued; next no-progress pass uses fresh worker")
                by_signature = state.metadata.setdefault("autonomy_recovery_tasks_created_by_signature", {})
                by_signature[signature] = int(by_signature.get(signature, 0)) + 1
                state.metadata["autonomy_recovery_tasks_created"] = sum(int(v) for v in by_signature.values())
                state.metadata["autonomy_stall_cycles"] = 0
                state.metadata.pop("autonomy_stalled", None)
                return {"status": "recovery_created", "created": 1, "changed": 0, "task_id": task.id, "incident_id": incident["id"], "recovery_stage": "retry"}
            self.recovery_incidents.escalate(incident, reason="no retryable failed leaf")
            stage = self.recovery_incidents.stage(incident)

        if stage == "global_replan" and incident.get("global_replan_issued"):
            state.metadata["autonomy_stalled"] = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "blockers": blockers[:50],
                "signature": signature,
                "incident_id": incident["id"],
                "recovery_stage": stage,
                "action": "human_attention_only_after_incident_scoped_recovery_ladder",
            }
            return {"status": "bounded_stall", "created": 0, "changed": 0, "blockers": blockers[:20], "incident_id": incident["id"], "recovery_stage": stage, "liveness": liveness.as_dict()}

        descriptions = {
            "fresh_worker": "Re-execute the blocked objective fragment with a fresh worker/provider context. Preserve prior evidence, diagnose the blocker and produce concrete domain work or executable follow-ups.",
            "clean_audit": "Perform a clean atomic continuity audit from durable project evidence. Do not reuse stale provider context. Identify the smallest missing executable work and create concrete follow-ups; do not ask for human review unless a genuine human-only decision exists.",
            "partial_replan": "Replan only the blocked subgraph. Preserve completed work and dependencies, replace dead-end leaves with the smallest executable tasks, and produce concrete domain progress.",
            "global_replan": "As a last autonomous recovery stage, rebuild the remaining project plan from the locked goal and durable evidence. Preserve completed work and safety constraints. Produce a minimal executable next batch.",
        }
        if stage in descriptions:
            task = Task(
                title=f"Autonomous recovery · {stage.replace('_', ' ')}",
                description=descriptions[stage] + " Current blockers: " + "; ".join(blockers[:20]),
                priority=100,
                status=TaskStatus.READY,
                estimated_seconds=45.0,
                max_attempts=3,
                required_capabilities=["reasoning"],
                acceptance_criteria=[
                    "The current blocker is resolved or converted into executable domain work",
                    "Completed work and safety constraints are preserved",
                    "No human review is requested without a genuine human-only decision",
                ],
                metadata={
                    "autonomy_recovery": True,
                    "control_plane_atomic": True,
                    "do_not_split": True,
                    "blocker_signature": signature,
                    "blockers": blockers[:50],
                    "recovery_incident_id": incident["id"],
                    "recovery_stage": stage,
                    "fresh_provider_context": stage == "fresh_worker",
                    "partial_replan": stage == "partial_replan",
                    "global_replan": stage == "global_replan",
                    "recovery_targets": [t.id for t in state.leaf_tasks if t.status in {TaskStatus.FAILED, TaskStatus.BLOCKED} and not is_blocked_safe(t)][:50],
                    "preferred_kind": "api",
                },
            )
            state.tasks[task.id] = task
            state.root_task_ids.append(task.id)
            self.recovery_incidents.record_attempt(incident, outcome="recovery_task_created")
            if stage != "global_replan":
                self.recovery_incidents.escalate(incident, reason=f"{stage} task created; next no-progress pass advances recovery")
            else:
                incident["global_replan_issued"] = True
            by_signature = state.metadata.setdefault("autonomy_recovery_tasks_created_by_signature", {})
            by_signature[signature] = int(by_signature.get(signature, 0)) + 1
            state.metadata["autonomy_recovery_tasks_created"] = sum(int(v) for v in by_signature.values())
            state.metadata["autonomy_stall_cycles"] = 0
            state.metadata.pop("autonomy_stalled", None)
            return {"status": "recovery_created", "created": 1, "changed": 0, "task_id": task.id, "incident_id": incident["id"], "recovery_stage": stage, "liveness": liveness.as_dict()}

        # Fail closed only after the complete incident-scoped recovery ladder has been used.
        state.metadata["autonomy_stalled"] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "blockers": blockers[:50],
            "signature": signature,
            "incident_id": incident["id"],
            "recovery_stage": stage,
            "action": "human_attention_only_after_incident_scoped_recovery_ladder",
        }
        return {"status": "bounded_stall", "created": 0, "changed": 0, "blockers": blockers[:20], "incident_id": incident["id"], "recovery_stage": stage, "liveness": liveness.as_dict()}

    def apply_recovery_result(self, state: ProjectState, recovery_task: Task) -> dict:
        """Apply a successful bounded recovery task to the failed work it replaced.

        The recovery task does not erase history. It links every exhausted failed target to the
        recovery evidence and marks that failed leaf as SUPERSEDED only after the recovery task
        itself reached COMPLETE. This lets the autonomous loop escape a dead end without
        pretending the original execution succeeded.
        """
        if not recovery_task.metadata.get("autonomy_recovery") or recovery_task.status != TaskStatus.COMPLETE:
            return {"superseded": 0}
        targets = [str(x) for x in recovery_task.metadata.get("recovery_targets", [])]
        superseded = 0
        for task_id in targets:
            target = state.tasks.get(task_id)
            if not target or target.status not in {TaskStatus.FAILED, TaskStatus.BLOCKED}:
                continue
            target.status = TaskStatus.SUPERSEDED
            target.metadata["superseded_by_autonomy_recovery"] = recovery_task.id
            target.metadata["recovery_result_excerpt"] = (recovery_task.result or "")[:800]
            superseded += 1
        if superseded:
            row = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "recovery_task": recovery_task.id,
                "superseded": superseded,
                "targets": targets,
            }
            state.metadata.setdefault("autonomy_recovery_history", []).append(row)
            events = state.metadata.setdefault("recovery_events", [])
            events.append({
                "ts": row["ts"],
                "kind": "autonomy_recovery_applied",
                "task_id": recovery_task.id,
                "title": recovery_task.title,
                "status": recovery_task.status.value,
                "attempt": int(recovery_task.attempts),
                "provider": recovery_task.provider_name,
                "detail": f"Recovered {superseded} failed target(s)",
                "targets": targets,
            })
            del events[:-200]
            state.metadata["autonomy_stall_cycles"] = 0
        return {"superseded": superseded}

    def finalize(self, state: ProjectState) -> dict:
        return self.self_eval.evaluate(state)
