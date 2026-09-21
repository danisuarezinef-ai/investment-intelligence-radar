from __future__ import annotations

import pathlib
import re

import asyncio
import statistics
import time
from dataclasses import asdict
from datetime import datetime, timezone

from .contracts import FixedWorkerRouter, GoalContract, WorkUnit, WorkerKind, WorkerProvider, WorkerRequest, WorkerRouter
from .conversation_controller import ConversationController
from .decision_manager import DecisionManager
from .continuity_policy import is_goal_audit_lineage, is_internal_continuity_task, protected_human_gate, task_for_decision, should_override_cognitive_early_abort
from .graph import TaskGraph
from .models import ProjectState, Task, TaskStatus
from .notifications import NotificationHub
from .resource_governor import ResourceGovernor
from .store import CheckpointStore
from .completion import CompletionEngine
from .goal_completion_gate import GoalCompletionGate
from .result_protocol import extract_directive
from .context import ContextBuilder
from .continuity import ContinuityManager
from .cost import CostEngine
from .production_intelligence import ProductionIntelligenceCore
from .long_horizon import OutcomeLearningEngine, SemanticProjectMemory
from .security_governance_v2 import SecurityGovernanceV2
from .learning_governance import ConfidenceCalibrationEngine, AutomatedSOPBuilder
from .cognitive_evolution import CognitiveEvolutionCore
from .quality_engineering import QualityEngineeringCore
from .integrity_engineering import IntegrityEngineeringCore
from .release_candidate_v1 import ReleaseCandidateCore
from .provider_policy import ProviderPolicy
from .provenance import AuditLog, ProvenanceGraph
from .quality import ConflictResolver, QualityEngine, ResultIntegrator, ConsensusBuilder, AdversarialVerifier
from .telemetry import Telemetry
from .optimizer import TaskOptimizer
from .memory import ProceduralMemory, DecisionLearningMemory, EpisodicMemory
from .safety import ActionRequest, SafetyBoundary
from .scheduling_v3 import TaskValueModel, BackpressureManager, SpeculativeExecutionManager, AdaptiveConcurrencyOptimizer, WorkloadPools
from .context import HierarchicalSummarizer, MemoryGarbageCollector
from .decomposition_v3 import AdaptiveTaskDecomposer, TaskFamilyManager
from .autonomous_loop import AutonomousProjectLoop
from .verification_v2 import LayeredVerificationEngine
from .resource_adaptive import AdaptiveResourceGovernor, CapacityProfiler
from .eta_v2 import MonteCarloETAEngine
from .hybrid_execution import HybridExecutionEngine
from .knowledge_v2 import KnowledgeIntegrationEngine
from .evolution_v07 import StrategicEvolutionLoopV07
from .self_hosting_tools import ArtifactExchangeLayer, FilesystemOperations, ProviderContextRecovery, WorkerSessionManager
from .operational_resilience import (
    AdaptiveSchedulerController,
    LongRunningAutonomyController,
    ResumeCoordinator,
    WorkerRecoverySupervisor,
)
from .quality_gate import AutomaticQualityGate
from .self_correction import SelfCorrectionEngine
from .project_memory_v2 import StructuredProjectMemory
from .dynamic_task_tree import DynamicTaskTreeManager
from .value_prioritization import ValuePrioritizer
from .dependency_manager import DependencyManager
from .consensus_verification import ConsensusVerificationEngine
from .application_recovery import ApplicationRecoveryManager
from .evidence_ledger_v2 import EvidenceLedgerV2
from .incident_manager_v2 import IncidentManagerV2
from .mission_supervisor_v2 import MissionSupervisorV2
from .fair_work_allocator import FairWorkAllocator
from .checkpoint_integrity_v2 import CheckpointIntegrityV2
from .capability_policy_v2 import CapabilityPolicyV2
from .quota_governor_v2 import QuotaGovernorV2
from .decision_trace_v3 import DecisionTraceV3
from .delegation_contracts_v2 import DelegationContractsV2
from .scheduler_reconciler_v1 import SchedulerStateReconcilerV1
from .task_roles_v2 import is_productive, is_internal, task_role, TaskRole
from .worker_lifecycle_v2 import WorkerLifecycleV2
from .provider_resilience_v2 import ProviderResilienceV2
from .deliverable_evidence_engine_v1 import DeliverableEvidenceEngineV1
from .scheduler_productivity_supervisor_v1 import SchedulerProductivitySupervisorV1
from .productive_throughput_ledger_v1 import ProductiveThroughputLedgerV1
from .critical_path_eta_v3 import CriticalPathETAV3
from .useful_milestone_engine_v1 import UsefulMilestoneEngineV1
from .useful_output_watchdog_v2 import UsefulOutputWatchdogV2
from .recovery_storm_guard_v1 import RecoveryStormGuardV1
from .blocked_safe_state_v1 import mark_blocked_safe, preserve_blocked_safe, release_blocked_safe


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


RELIABILITY_EPOCH = "dev309-closure-convergence-v1"


def _apply_reliability_epoch_migration(state: ProjectState) -> dict:
    marker = state.metadata.setdefault("reliability_epoch_v1", {})
    if marker.get("epoch") == RELIABILITY_EPOCH:
        return {"changed": False, "epoch": RELIABILITY_EPOCH}

    now = utcnow().isoformat()
    worker_recoveries = int(state.metadata.get("worker_recoveries", 0) or 0)
    recovery_tasks = int(state.metadata.get("autonomy_recovery_tasks_created", 0) or 0)
    productive_done = sum(
        1 for task in state.leaf_tasks
        if is_productive(task, state)
        and task.status in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}
    )

    previous = {
        "epoch": marker.get("epoch"),
        "worker_recoveries": worker_recoveries,
        "autonomy_recovery_tasks_created": recovery_tasks,
        "productive_completed": productive_done,
        "operator_productivity_state": state.metadata.get("operator_productivity_state"),
    }
    history = marker.setdefault("history", [])
    history.append({"ts": now, **previous})
    del history[:-20]

    truth = state.metadata.setdefault("productive_truth_v2", {})
    truth.update({
        "epoch": RELIABILITY_EPOCH,
        "productive_watermark": productive_done,
        "recoveries_at_watermark": worker_recoveries,
        "historical_recoveries_before_epoch": worker_recoveries,
        "worker_recoveries": 0,
        "stalled": False,
        "reason": "reliability epoch migrated",
    })

    budget = state.metadata.setdefault("recovery_budget_guard_v1", {})
    budget.update({
        "epoch": RELIABILITY_EPOCH,
        "productive_watermark": productive_done,
        "recoveries_at_watermark": recovery_tasks,
        "migration_existing_recoveries": recovery_tasks,
        "attempts_without_progress": 0,
        "budget_exhausted": False,
    })
    state.metadata.pop("control_plane_recovery_budget_exhausted", None)

    progress = state.metadata.setdefault("productive_progress_guard_v1", {})
    progress.update({
        "epoch": RELIABILITY_EPOCH,
        "historical_ticks_before_epoch": int(progress.get("ticks", 0) or 0),
        "historical_no_progress_cycles_before_epoch": int(progress.get("no_progress_cycles", 0) or 0),
        "historical_control_only_cycles_before_epoch": int(progress.get("control_only_cycles", 0) or 0),
        "ticks": 0,
        "last_productive_completed": productive_done,
        "no_progress_cycles": 0,
        "control_only_cycles": 0,
        "stalled": False,
        "reason": "reliability epoch migrated",
    })

    storm = state.metadata.setdefault("recovery_storm_guard_v1", {})
    storm.update({
        "epoch": RELIABILITY_EPOCH,
        "productive_watermark": productive_done,
        "recoveries_at_watermark": worker_recoveries,
        "historical_recoveries_before_epoch": worker_recoveries,
        "recoveries_without_progress": 0,
        "open": False,
        "reason": "reliability epoch migrated",
    })
    state.metadata.pop("recovery_storm_breaker", None)
    state.metadata.pop("recovery_storm_suppression_owner", None)

    circuit = state.metadata.setdefault("control_churn_circuit_breaker_v1", {})
    circuit.update({
        "epoch": RELIABILITY_EPOCH,
        "epoch_started_at": now,
        "signature": "none",
        "repeated_signature_count": 0,
        "open": False,
    })
    state.metadata.pop("control_plane_circuit_open", None)
    state.metadata.pop("productive_stall_escape_required", None)

    # DEV309 closure contract migration. Explicit filenames in a free-text goal are
    # real deliverables, and a bounded single-artifact objective must not inherit the
    # same evidence/generation thresholds as a long research or implementation project.
    if not state.goal_deliverables:
        matches = re.findall(
            r"(?<![A-Za-z0-9_])([A-Za-z0-9_.\/\-]+\.(?:md|txt|json|csv|html))(?![A-Za-z0-9_])",
            str(state.goal or ""),
            flags=re.IGNORECASE,
        )
        state.goal_deliverables = list(dict.fromkeys(
            str(x).replace("\\", "/").strip().strip(".,;:()[]{}") for x in matches if str(x).strip()
        ))

    single_artifact = len(state.goal_deliverables) == 1
    closure_profile = "bounded_single_artifact" if single_artifact else "general"
    if single_artifact:
        state.metadata["min_goal_audit_evidence_refs"] = 2
        state.metadata["min_goal_audit_grounded_refs"] = 2
        state.metadata["min_goal_continuity_generations"] = 1
        state.metadata["max_goal_continuity_generations"] = 4
    else:
        state.metadata.setdefault("min_goal_audit_evidence_refs", 3)
        state.metadata.setdefault("min_goal_audit_grounded_refs", 2)
        state.metadata.setdefault("min_goal_continuity_generations", 3)
        state.metadata.setdefault("max_goal_continuity_generations", 24)
    state.metadata["closure_profile_v1"] = {
        "epoch": RELIABILITY_EPOCH,
        "profile": closure_profile,
        "deliverables": list(state.goal_deliverables),
        "max_generations": int(state.metadata.get("max_goal_continuity_generations", 24)),
    }

    # Field repair for the observed #173 loop. Preserve history but start one fresh,
    # bounded closure epoch and retire only active continuity machinery.
    historical_generation = int(state.metadata.get("goal_continuity_generation", 0) or 0)
    max_generation = int(state.metadata.get("max_goal_continuity_generations", 24) or 24)
    if historical_generation > max_generation:
        retired_closure = []
        for task in state.leaf_tasks:
            if protected_human_gate(task):
                continue
            if not (
                is_goal_audit_lineage(state, task)
                or task.metadata.get("continuity_gap_recovery")
            ):
                continue
            if task.status in {
                TaskStatus.WAITING, TaskStatus.READY, TaskStatus.RUNNING,
                TaskStatus.BLOCKED, TaskStatus.RETRY, TaskStatus.NEEDS_REVIEW,
            }:
                task.status = TaskStatus.SUPERSEDED
                task.worker_id = None
                task.metadata["superseded_reason"] = "dev309_restart_bounded_closure_epoch"
                retired_closure.append(task.id)
        state.metadata["historical_goal_continuity_generation"] = historical_generation
        state.metadata["goal_continuity_generation"] = 0
        state.metadata["continuity_nonspawn_rejections"] = 0
        state.metadata["goal_audit_passed"] = False
        state.metadata.pop("last_goal_audit_rejection", None)
        state.metadata["dev309_closure_epoch_restarted"] = {
            "historical_generation": historical_generation,
            "retired_active_closure_tasks": retired_closure,
            "profile": closure_profile,
            "ts": now,
        }

    # DEV308: rebase the separate recovery-churn fuse and remove only stale
    # operator/suppression state when concrete productive execution is already
    # available. Protected task-level blocks remain untouched.
    churn = state.metadata.setdefault("recovery_churn_fuse_v2", {})
    churn.update({
        "open": False,
        "attempts_without_progress": 0,
        "retired": 0,
        "reason": "reliability epoch migrated",
    })
    executable_productive = [
        task for task in state.leaf_tasks
        if is_productive(task, state)
        and task.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING}
    ]
    if executable_productive:
        state.metadata.pop("suppress_new_internal_recovery", None)
        state.metadata.pop("autonomy_stalled", None)
        state.metadata.pop("operator_block_reason", None)
        state.metadata["operator_productivity_state"] = (
            "TRABAJANDO" if any(t.status == TaskStatus.RUNNING for t in executable_productive)
            else "PLANIFICANDO"
        )

    # DEV307 field migration: release only fail-closed tasks whose evidence
    # proves they were blocked by the 1.5.82 orphan-worker bookkeeping defect.
    # Legitimate safety/human gates remain untouched.
    released_orphan_worker_tasks = []
    recovery_history = list(state.metadata.get("worker_recovery_history") or [])
    for task in state.leaf_tasks:
        if protected_human_gate(task):
            continue
        reason = str(task.metadata.get("blocked_safe_reason") or "")
        source = str(task.metadata.get("blocked_safe_source") or "")
        orphan_history = any(
            str(row.get("task_id") or "") == task.id
            and str(row.get("reason") or "") == "orphan_running_without_live_future"
            for row in recovery_history
            if isinstance(row, dict)
        )
        affected = (
            reason == "orphan_running_without_live_future"
            or (
                reason == "worker_recovery_budget_exhausted"
                and source in {"worker_recovery_supervisor", "worker_watchdog"}
                and orphan_history
            )
        )
        if affected and (task.metadata.get("blocked_safe") or task.metadata.get("manual_release_required")):
            row = release_blocked_safe(
                task,
                reason="DEV307 repairs false orphan-worker field block",
                strategy="finished_future_durable_state_normalization",
            )
            if row.get("released"):
                task.metadata.pop("live_recovery_reason", None)
                task.metadata.pop("strategy_change_requested", None)
                task.metadata.pop("strategy_change_applied", None)
                task.metadata.pop("strategy_change_from", None)
                task.metadata.pop("recovery_strategy", None)
                task.metadata.pop("recovery_storm_guard_v1", None)
                task.metadata["dev307_orphan_field_migration"] = now
                task.attempts = max(0, min(int(task.attempts), max(0, int(task.max_attempts) - 1)))
                task.metadata["retry_after_ts"] = 0
                released_orphan_worker_tasks.append(task.id)

    # Retire only stale internal units that the OLD recovery guard made
    # permanently undispatchable. Do not release protected human gates and
    # do not erase the blocked-safe evidence.
    retired = []
    for task in state.leaf_tasks:
        if not is_internal(task, state) or protected_human_gate(task):
            continue
        reason = str(task.metadata.get("blocked_safe_reason") or "")
        source = str(task.metadata.get("blocked_safe_source") or "")
        stale_guard_block = (
            bool(task.metadata.get("blocked_safe") or task.metadata.get("manual_release_required"))
            and source == "scheduler_dispatch_guard"
            and reason in {
                "global_recovery_storm_breaker_open",
                "task_recovery_budget_exhausted",
                "task_attempt_budget_exhausted",
            }
        )
        stale_exhausted_control = (
            task.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.BLOCKED, TaskStatus.NEEDS_REVIEW}
            and int(task.attempts) >= max(1, int(task.max_attempts))
            and not task.metadata.get("explicit_human_gate")
        )
        if stale_guard_block or stale_exhausted_control:
            task.status = TaskStatus.SUPERSEDED
            task.worker_id = None
            task.metadata["superseded_reason"] = "reliability_epoch_migration_stale_internal_control"
            task.metadata["reliability_epoch_retired_at"] = now
            task.metadata["reliability_epoch_retired_from"] = RELIABILITY_EPOCH
            retired.append(task.id)

    marker.update({
        "epoch": RELIABILITY_EPOCH,
        "started_at": now,
        "historical_worker_recoveries": worker_recoveries,
        "historical_recovery_tasks": recovery_tasks,
        "productive_watermark": productive_done,
        "retired_stale_internal_task_ids": retired,
        "released_false_orphan_task_ids": released_orphan_worker_tasks,
    })
    return {
        "changed": True,
        "epoch": RELIABILITY_EPOCH,
        "retired": retired,
        "released_false_orphan_task_ids": released_orphan_worker_tasks,
        "previous": previous,
    }


class ContinuousScheduler:
    """Dependency-aware continuous scheduler for API/browser/local workers."""

    def __init__(
        self,
        state: ProjectState,
        provider: WorkerProvider | None,
        store: CheckpointStore,
        graph: TaskGraph | None = None,
        governor: ResourceGovernor | None = None,
        controller: ConversationController | None = None,
        router: WorkerRouter | None = None,
        decision_manager: DecisionManager | None = None,
        notifications: NotificationHub | None = None,
    ) -> None:
        if router is None and provider is None:
            raise ValueError("ContinuousScheduler requires either a provider or a router")
        self.state = state
        epoch_migration = _apply_reliability_epoch_migration(self.state)
        if epoch_migration.get("changed"):
            self.state.metadata["reliability_epoch_last_migration"] = epoch_migration
        self.router = router or FixedWorkerRouter(provider)  # type: ignore[arg-type]
        self.store = store
        self.graph = graph or TaskGraph()
        self.governor = governor or ResourceGovernor()
        self.notifications = notifications or NotificationHub()
        self.controller = controller or ConversationController(notifications=self.notifications)
        self.decision_manager = decision_manager or DecisionManager()
        self._runner: asyncio.Task | None = None
        self._active: dict[str, asyncio.Task] = {}
        self._active_provider: dict[str, str] = {}
        self._stop = asyncio.Event()
        self._completed_notified = False
        self.completion_engine = CompletionEngine()
        self.context_builder = ContextBuilder()
        self.quality_engine = QualityEngine()
        self.integrator = ResultIntegrator()
        self.conflicts = ConflictResolver()
        self.provenance = ProvenanceGraph()
        self.audit_log = AuditLog()
        self.provider_policy = ProviderPolicy()
        self.cost_engine = CostEngine()
        self.production_intelligence = ProductionIntelligenceCore()
        self.outcome_learning = OutcomeLearningEngine()
        self.semantic_memory = SemanticProjectMemory()
        self.security_v2 = SecurityGovernanceV2()
        self.confidence_calibration = ConfidenceCalibrationEngine()
        self.sop_builder = AutomatedSOPBuilder()
        self.cognitive = CognitiveEvolutionCore()
        self.quality_engineering = QualityEngineeringCore()
        self.integrity_engineering = IntegrityEngineeringCore()
        self.release_candidate = ReleaseCandidateCore()
        self.quality_engineering.initialize_project(self.state)
        self.security_v2.initialize(self.state)
        stale_cost_reservations = self.cost_engine.clear_reservations(self.state, reason="scheduler_init")
        if stale_cost_reservations:
            self.state.metadata["stale_cost_reservations_released_on_init"] = len(stale_cost_reservations)
        self.telemetry = Telemetry()
        self.optimizer = TaskOptimizer()
        self.value_model = TaskValueModel()
        self.backpressure = BackpressureManager()
        self.speculation = SpeculativeExecutionManager()
        self.concurrency_optimizer = AdaptiveConcurrencyOptimizer()
        self.workload_pools = WorkloadPools()
        self.consensus_builder = ConsensusBuilder()
        self.adversarial_verifier = AdversarialVerifier()
        self.hierarchical_summarizer = HierarchicalSummarizer()
        self.memory_gc = MemoryGarbageCollector()
        self.adaptive_decomposer = AdaptiveTaskDecomposer()
        self.family_manager = TaskFamilyManager()
        self.autonomous_loop = AutonomousProjectLoop()
        self.layered_verification = LayeredVerificationEngine()
        self.adaptive_resources = AdaptiveResourceGovernor(self.governor)
        self.capacity_profiler = CapacityProfiler(self.governor)
        self.eta_engine = MonteCarloETAEngine(self.graph, self.governor)
        self.hybrid_execution = HybridExecutionEngine()
        self.knowledge_engine = KnowledgeIntegrationEngine()
        self.strategic_v07 = StrategicEvolutionLoopV07()
        self._ticks = 0
        self.safety = SafetyBoundary()
        store_path = getattr(store, "path", None)
        self.procedural_memory = ProceduralMemory(store_path.parent / "procedural_memory.json") if store_path else None
        self.decision_learning = DecisionLearningMemory(store_path.parent / "decision_learning.json") if store_path else None
        self.episodic_memory = EpisodicMemory(store_path.parent / "episodic_memory.json") if store_path else None
        self._episode_recorded = False
        self.controller.decision_learning = self.decision_learning
        self._milestones_notified: set[int] = set()
        self._obs_ts = time.perf_counter()
        self._obs_complete = len(self.state.completed_leaf_tasks)
        self.continuity = ContinuityManager()
        self.goal_completion_gate = GoalCompletionGate()
        self.worker_sessions = WorkerSessionManager()
        self.provider_context_recovery = ProviderContextRecovery()
        self.resume_coordinator = ResumeCoordinator()
        self.long_runtime = LongRunningAutonomyController()
        self.worker_recovery = WorkerRecoverySupervisor()
        self.adaptive_scheduler = AdaptiveSchedulerController()
        self.quality_gate = AutomaticQualityGate()
        self.self_correction = SelfCorrectionEngine()
        self.structured_memory = StructuredProjectMemory()
        self.dynamic_tree = DynamicTaskTreeManager()
        self.value_prioritizer = ValuePrioritizer()
        self.dependency_manager = DependencyManager()
        self.consensus_verification = ConsensusVerificationEngine()
        self.application_recovery = ApplicationRecoveryManager()
        self.evidence_ledger_v2 = EvidenceLedgerV2()
        self.incidents_v2 = IncidentManagerV2()
        self.mission_supervisor_v2 = MissionSupervisorV2()
        self.fair_allocator = FairWorkAllocator()
        self.checkpoint_integrity_v2 = CheckpointIntegrityV2()
        self.capability_policy_v2 = CapabilityPolicyV2()
        self.quota_governor_v2 = QuotaGovernorV2()
        self.decision_trace_v3 = DecisionTraceV3()
        self.delegation_contracts_v2 = DelegationContractsV2()
        self.scheduler_reconciler_v1 = SchedulerStateReconcilerV1()
        self.worker_lifecycle_v2 = WorkerLifecycleV2()
        self.provider_resilience_v2 = ProviderResilienceV2()
        self.deliverable_evidence_v1 = DeliverableEvidenceEngineV1()
        self.scheduler_productivity_supervisor_v1 = SchedulerProductivitySupervisorV1()
        self.productive_throughput_ledger_v1 = ProductiveThroughputLedgerV1()
        self.critical_path_eta_v3 = CriticalPathETAV3()
        self.useful_milestone_engine_v1 = UsefulMilestoneEngineV1()
        self.useful_output_watchdog_v2 = UsefulOutputWatchdogV2()
        self.recovery_storm_guard_v1 = RecoveryStormGuardV1()
        integrity_on_load = self.checkpoint_integrity_v2.verify(self.state)
        self.state.metadata["checkpoint_integrity_load_report"] = integrity_on_load.to_dict()
        self.structured_memory.sync(self.state)
        self._resume_report = None
        if any(t.status == TaskStatus.RUNNING for t in self.state.tasks.values()):
            self._resume_report = self.resume_coordinator.prepare(self.state, source="scheduler_init")

    def start(self) -> None:
        if self._runner and not self._runner.done():
            return
        self.state.started_at = self.state.started_at or utcnow()
        self.long_runtime.start_session(self.state, source="continuous_scheduler")
        # Persist the new runtime session before any provider is allowed to run.
        self.store.save(self.state)
        self._stop.clear()
        self._runner = asyncio.create_task(self._loop(), name="ceo-continuous-scheduler")

    async def stop(self) -> None:
        """Stop the scheduler at a durable, restart-safe boundary.

        Closing/switching projects may interrupt provider calls. Those tasks are
        explicitly returned to RETRY before the final checkpoint so a Windows
        restart never loses the work unit or reuses a stale RUNNING state.
        """
        self._stop.set()
        if self._runner:
            await self._runner

        # Let already-finished workers publish their final state, then cancel only
        # calls that are genuinely still in flight.
        await asyncio.sleep(0)
        for task_id, future in list(self._active.items()):
            if future.done():
                try:
                    await future
                except Exception:
                    pass
                continue
            task = self.state.tasks.get(task_id)
            if task and task.status == TaskStatus.RUNNING:
                if self.state.cancelled_at is not None or self.state.metadata.get("operator_cancelled"):
                    task.status = TaskStatus.SUPERSEDED
                    task.metadata["superseded_reason"] = "operator_cancelled"
                    task.metadata["cancelled_by_operator_at"] = (self.state.cancelled_at.isoformat() if self.state.cancelled_at else utcnow().isoformat())
                else:
                    task.status = TaskStatus.RETRY
                    task.metadata["interrupted_by_shutdown"] = utcnow().isoformat()
                    task.metadata["provider_stage"] = "interrupted"
            future.cancel()
        if self._active:
            await asyncio.gather(*self._active.values(), return_exceptions=True)
        self._collect_finished()
        self.long_runtime.stop_session(self.state, clean=True)
        self.continuity.capture(self.state, reason="scheduler_stop")
        self.store.save(self.state)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            if self.state.cancelled_at is not None or self.state.metadata.get("operator_cancelled"):
                self.state.paused = True
                self.state.autonomy_enabled = False
                self.state.metadata["suppress_new_internal_recovery"] = True
                self.state.metadata["operator_productivity_state"] = "CANCELADO"
                self.store.save(self.state)
                self._stop.set()
                break
            self._ticks += 1
            self.decision_manager.tick(self.state)
            if self._ticks == 1 or self._ticks % 10 == 0:
                self.mission_supervisor_v2.tick(self.state)
            if self._ticks % 50 == 0:
                pruned = self.optimizer.prune_duplicates(self.state)
                self.speculation.cancel_irrelevant(self.state)
                self.family_manager.index(self.state)
                if self.state.metadata.get("enable_auto_batching") and not self.backpressure.saturated(self.state):
                    merged=self.family_manager.merge_microtasks(self.state)
                    if merged:self.audit_log.emit(self.state,"batch_merge",{"superseded":merged})
                if pruned:
                    self.audit_log.emit(self.state, "dedupe", {"superseded": pruned})
            if self._ticks % 50 == 0:
                self._record_concurrency_observation()
            strategic_interval=max(1,int(self.state.metadata.get('strategic_tick_interval',200)))
            if self._ticks % strategic_interval == 0:
                self.hierarchical_summarizer.update(self.state)
                self.memory_gc.collect(self.state)
                self.autonomous_loop.tick(self.state, decomposer=self.adaptive_decomposer)
                self.strategic_v07.tick(self.state)
            if self._ticks % 25 == 0:
                dep_report = self.dependency_manager.reconcile(self.state)
                self.state.metadata["dependency_manager_last"] = dep_report.to_dict()
            if self._ticks % 100 == 0:
                tree_report = self.dynamic_tree.maintain(self.state, max_splits=4, max_dedupes=20)
                self.state.metadata["dynamic_task_tree_last"] = tree_report.to_dict()
                self.structured_memory.sync(self.state)
            self._collect_finished()
            reconcile = self.scheduler_reconciler_v1.reconcile(
                self.state, active_task_ids=set(self._active)
            )
            self.state.metadata["scheduler_reconciler_last"] = reconcile.to_dict()
            self.state.metadata["worker_lifecycle_v2_last"] = self.worker_lifecycle_v2.reconcile(
                self.state, active_task_ids=set(self._active)
            )
            hardening = self.scheduler_productivity_supervisor_v1.tick(
                self.state, active_task_ids=set(self._active)
            )
            self.state.metadata["scheduler_productivity_supervisor_last"] = hardening.to_dict()
            stall_escape = self.useful_output_watchdog_v2.tick(self.state)
            self.state.metadata["useful_output_watchdog_last"] = stall_escape.to_dict()
            throughput = self.productive_throughput_ledger_v1.snapshot(self.state, persist=True)
            self.state.metadata["productive_throughput_last"] = throughput.to_dict()
            if self._ticks % 5 == 0:
                eta = self.critical_path_eta_v3.estimate(
                    self.state, workers=max(1, self.governor.target_concurrency(self.state.power_percent))
                )
                self.state.metadata["critical_path_eta_last"] = eta.to_dict()
                self.state.metadata["useful_milestones_last"] = {
                    "milestones": [x.to_dict() for x in self.useful_milestone_engine_v1.rank(self.state, limit=8)]
                }
            self.graph.refresh(self.state)
            live_recovery = self._recover_live_workers()
            storm_report = self.recovery_storm_guard_v1.assess(self.state)
            self.state.metadata["recovery_storm_guard_last"] = storm_report.to_dict()
            storm_open = bool(storm_report.open)
            ready_count = sum(1 for t in self.state.leaf_tasks if t.status == TaskStatus.READY)
            self.long_runtime.heartbeat(self.state, active_count=len(self._active), ready_count=ready_count)
            if (
                not self.state.paused
                and not self._active
                and (self._ticks % 10 == 0 or self.long_runtime.needs_progress_kick(self.state))
                and not any(
                is_productive(t, self.state)
                and t.status in {TaskStatus.READY, TaskStatus.RETRY, TaskStatus.RUNNING}
                for t in self.state.leaf_tasks
            )
            ):
                self.autonomous_loop.ensure_progress(self.state, decomposer=self.adaptive_decomposer)
                self.graph.refresh(self.state)

            if not self.state.paused and not storm_open:
                pstats = self.state.metadata.get("provider_stats", {})
                runs = sum(int(v.get("runs", 0)) for v in pstats.values())
                failures = sum(int(v.get("failures", 0)) for v in pstats.values())
                failure_rate = failures / max(1, runs)
                target = self.governor.adaptive_target(self.state.power_percent, failure_rate=failure_rate)
                learned_target = self.concurrency_optimizer.optimal(self.state, self.governor.hardware_capacity())
                if self.state.metadata.get("concurrency_observations"):
                    target = min(target, max(1, learned_target))
                adaptive_decision = self.adaptive_scheduler.decide(
                    self.state,
                    self.governor,
                    learned_target=target,
                    current_active=len(self._active),
                )
                target = adaptive_decision.target
                free_slots = max(0, target - len(self._active))
                if free_slots and not self.backpressure.saturated(self.state):
                    for speculative in self.speculation.candidates(self.state, limit=min(3, free_slots)):
                        speculative.metadata["speculative"] = True
                        speculative.status = TaskStatus.READY
                if free_slots:
                    ready_candidates=[]
                    for t in self.state.leaf_tasks:
                        if t.status != TaskStatus.READY:
                            continue
                        allowed, deny_reason = self.recovery_storm_guard_v1.dispatch_allowed(self.state, t)
                        if not allowed:
                            mark_blocked_safe(t, deny_reason, source="scheduler_dispatch_guard")
                            self._activity_event("dispatch_blocked_safe", t, detail=deny_reason)
                            continue
                        ready_candidates.append(t)
                    value_scores=self.value_prioritizer.score_many(self.state, ready_candidates, self.graph)
                    ready = self.fair_allocator.allocate(self.state, ready_candidates, value_scores, max(free_slots, 1))
                    pool_counts=self.workload_pools.counts(self.state)
                    pool_limits=self.adaptive_resources.plan(self.state)
                    self.state.metadata["hybrid_execution_plan"] = asdict(self.hybrid_execution.plan(self.state, target, pool_limits))
                    scheduled=0
                    pending_launch: list[tuple[Task, str]] = []
                    for task in ready:
                        if scheduled>=free_slots:break
                        quota_decision = self.quota_governor_v2.assess_dispatch(self.state, task)
                        if not quota_decision.allowed:
                            task.status = TaskStatus.RETRY
                            task.result = "Renewable local resource quota is temporarily exhausted."
                            task.metadata["quota_decision_v2"] = quota_decision.to_dict()
                            task.metadata["quota_retry_after_seconds"] = quota_decision.retry_after_seconds
                            self._set_retry_backoff(task)
                            self.decision_trace_v3.append(self.state, "dispatch_deferred_quota", task=task, data=quota_decision.to_dict())
                            self._activity_event("quota_deferred", task, detail=quota_decision.reason)
                            continue
                        delegation_decision = self.delegation_contracts_v2.assess(self.state, task)
                        if not delegation_decision.allowed:
                            task.status = TaskStatus.NEEDS_REVIEW
                            task.result = "Delegated task exceeds or violates its least-privilege contract."
                            self.decision_trace_v3.append(self.state, "delegation_gate", task=task, data=delegation_decision.to_dict())
                            self._activity_event("delegation_gate", task, detail=delegation_decision.reason)
                            continue
                        capability_decision = self.capability_policy_v2.assess(self.state, task)
                        if not capability_decision.allowed:
                            task.status = TaskStatus.NEEDS_REVIEW
                            task.result = "Sensitive capability requires explicit human approval before dispatch."
                            self.decision_trace_v3.append(self.state, "capability_gate", task=task, data=capability_decision.to_dict())
                            self._activity_event("capability_gate", task, detail=capability_decision.reason)
                            continue
                        kind=self.workload_pools.classify(task)
                        cap=int(pool_limits.get(f"{kind}_workers", pool_limits.get("total_workers", target)))
                        if pool_counts.get(kind,0)>=cap:continue
                        predicted = task.metadata.setdefault("predicted_success_probability", self.production_intelligence.planner.task_probability(task))
                        budget_pressure = float(self.cost_engine.snapshot(self.state).get("pressure", 0.0))
                        deadline_pressure = float((self.state.metadata.get("deadline_intelligence") or {}).get("pressure", 0.0) or 0.0)
                        task.metadata["cognitive_plan"] = self.cognitive.task_plan(
                            self.state, task, budget_pressure=budget_pressure, deadline_pressure=deadline_pressure
                        )
                        task.metadata["strategy_observations"] = int(task.metadata.get("strategy_observations", 0)) + 1
                        early_abort = self.cognitive.early_abort.evaluate(
                            self.state, task,
                            spent_fraction=float(task.metadata.get("strategy_spent_fraction", 0.0)),
                            progress_gain=float(task.metadata.get("strategy_progress_gain", 1.0)),
                            failure_count=int(task.metadata.get("failure_count", 0)),
                            expected_success=float(predicted),
                        )
                        if early_abort["abort"]:
                            if should_override_cognitive_early_abort(self.state, task):
                                task.metadata["cognitive_early_abort_overridden"] = early_abort
                                override_count = int(task.metadata.get("cognitive_early_abort_override_count", 0)) + 1
                                task.metadata["cognitive_early_abort_override_count"] = override_count
                                # Keep observability useful without flooding the event stream on a stale task.
                                if override_count <= 3 or override_count in {5, 10}:
                                    self._activity_event(
                                        "internal_early_abort_overridden",
                                        task,
                                        detail=f"{early_abort['reason']} · internal control-plane task continues autonomously",
                                    )
                            else:
                                task.status = TaskStatus.NEEDS_REVIEW
                                task.metadata["cognitive_early_abort"] = early_abort
                                self._activity_event("cognitive_early_abort", task, detail=early_abort["reason"])
                                continue
                        try:
                            lease = self.worker_lifecycle_v2.claim(
                                self.state, task, f"scheduler-{task.id[:8]}", ttl_seconds=180
                            )
                            task.metadata["worker_lease_v2"] = lease.to_dict()
                        except RuntimeError:
                            task.status = TaskStatus.RETRY
                            task.metadata["worker_lease_collision_v2"] = True
                            self._set_retry_backoff(task)
                            continue
                        task.status = TaskStatus.RUNNING
                        task.started_at = utcnow()
                        task.attempts += 1
                        self.quota_governor_v2.record_dispatch(self.state, task)
                        self.decision_trace_v3.append(
                            self.state, "dispatch_selected", task=task,
                            data={
                                "value_score": float(value_scores.get(task.id, 0.0)),
                                "workload_kind": kind,
                                "capability": capability_decision.to_dict(),
                                "delegation": delegation_decision.to_dict(),
                                "quota": quota_decision.to_dict(),
                            },
                        )
                        # Executable work has resumed, so any prior bounded-stall marker
                        # is stale and must not poison operator status or future snapshots.
                        self.state.metadata.pop("autonomy_stalled", None)
                        self.state.metadata["autonomy_stall_cycles"] = 0
                        self._activity_event("task_started", task, detail="Tarea asignada a un worker")
                        pending_launch.append((task, kind))
                        pool_counts[kind]=pool_counts.get(kind,0)+1;scheduled+=1

                    if pending_launch:
                        # Crash consistency: the RUNNING/attempt transition and its dispatch
                        # token become durable before provider side effects can start.
                        self.long_runtime.record_dispatch_intent(self.state, [task for task, _ in pending_launch])
                        for task, _ in pending_launch:
                            self.evidence_ledger_v2.append(
                                self.state, "dispatch_intent", task=task,
                                data={"attempt": int(task.attempts), "dispatch_token": task.metadata.get("dispatch_token")},
                            )
                        self.continuity.capture(self.state, reason="pre_dispatch")
                        self.store.save(self.state)
                        for task, _kind in pending_launch:
                            coro = asyncio.create_task(self._run_task(task), name=f"worker-{task.id}")
                            self._active[task.id] = coro

            self.graph.refresh(self.state)
            self.state.metadata["knowledge_saturated"] = self.completion_engine.yield_tracker.saturated(self.state)
            budget_snapshot = self.cost_engine.snapshot(self.state)
            self.state.metadata["budget_snapshot"] = budget_snapshot
            if self._ticks % 50 == 0:
                hist = self.state.metadata.setdefault("cognitive_progress_samples_v1", [])
                hist.append({"progress": float(self.state.progress) / 100.0, "cost": float(budget_snapshot.get("spent", 0.0)), "evidence": len(self.state.metadata.get("evidence_ledger_v1", []))})
                del hist[:-20]
                if len(hist) >= 4:
                    dead = self.cognitive.dead_end.evaluate(
                        self.state,
                        progress_samples=[x["progress"] for x in hist],
                        cost_samples=[x["cost"] for x in hist],
                        evidence_samples=[x["evidence"] for x in hist],
                    )
                    self.state.metadata["cognitive_dead_end"] = dead
            if self.state.metadata.get("adaptive_budget_mode", True) and budget_snapshot["pressure"] >= 0.85 and self.state.priority_mode != "cost_min":
                self.state.metadata.setdefault("priority_mode_before_budget_pressure", self.state.priority_mode)
                self.state.priority_mode = "cost_min"
            self.state.metadata["activity_snapshot"] = self._activity_snapshot()
            self.continuity.capture(self.state, reason="scheduler_tick")
            if self._ticks % 50 == 0:
                self.state.metadata["checkpoint_compaction_v2"] = self.checkpoint_integrity_v2.compact(self.state)
            self.checkpoint_integrity_v2.stamp(self.state)
            self.store.save(self.state)
            progress = int(self.state.progress)
            for milestone in (25, 50, 75):
                if progress >= milestone and milestone not in self._milestones_notified:
                    self._milestones_notified.add(milestone)
                    snapshot_full = getattr(self.store, "snapshot_full", None)
                    if callable(snapshot_full):
                        seq = snapshot_full(self.state)
                        self.state.metadata.setdefault("milestone_snapshots", {})[str(milestone)] = seq
                    if self.state.notifications_enabled:
                        self.notifications.emit(self.state, title=f"Hito {milestone}%", body=f"CEO ha alcanzado {milestone}% de progreso.", severity="milestone")

            if self._is_complete():
                self.state.completed_at = self.state.completed_at or utcnow()
                self.long_runtime.stop_session(self.state, clean=True)
                if self.state.notifications_enabled and not self._completed_notified:
                    self.notifications.emit(
                        self.state,
                        title="Proyecto completado",
                        body=f"CEO ha completado: {self.state.goal}",
                        severity="success",
                    )
                    self._completed_notified = True
                if self.episodic_memory and not self._episode_recorded:
                    self.episodic_memory.record_run(self.state.id, strategy=self.state.priority_mode, outcome="complete", metrics={"progress":self.state.progress,"avoided":self.state.human_interventions_avoided,"cost":self.cost_engine.spent(self.state)})
                    self.autonomous_loop.finalize(self.state)
                    self.strategic_v07.finalize(self.state)
                    self._episode_recorded=True
                self.store.save(self.state)
                snapshot_full = getattr(self.store, "snapshot_full", None)
                if callable(snapshot_full) and not self.state.metadata.get("completion_snapshot"):
                    self.state.metadata["completion_snapshot"] = snapshot_full(self.state)
                    self.store.save(self.state)
                break

            await asyncio.sleep(0.1)

    def _priority_key(self, task: Task) -> tuple[float, datetime]:
        score = self.value_prioritizer.score(self.state, task, self.graph)
        age_seconds = max(0.0, (utcnow() - task.created_at).total_seconds())
        score += min(0.35, age_seconds / 36000.0)
        return (-score, task.created_at)

    def _goal_contract(self) -> GoalContract:
        return GoalContract(
            objective=self.state.goal,
            definition=self.state.goal_definition or self.state.goal,
            success_definition=self.state.goal_success_definition,
            completion_criteria=list(self.state.completion_criteria),
            constraints=list(self.state.goal_constraints),
            deliverables=list(self.state.goal_deliverables),
            forbidden_actions=list(self.state.metadata.get("forbidden_actions", [])),
            deadline=self.state.deadline,
            urgency=self.state.urgency,
            budget_limit=self.state.budget_limit,
        )

    async def _run_task(self, task: Task) -> None:
        started = time.perf_counter()
        provider_name = "unknown"
        reservation_active = False
        reservation_amount = max(0.0, float(task.cost_estimate or 0.0))
        try:
            if not self.cost_engine.reserve(self.state, task.id, reservation_amount):
                task.status = TaskStatus.NEEDS_REVIEW
                task.result = "Budget limit prevents automatic execution."
                task.metadata["budget_blocked"] = {
                    "estimate": reservation_amount,
                    "budget": self.cost_engine.snapshot(self.state),
                }
                self._activity_event("budget_blocked", task, detail="Presupuesto insuficiente para reservar esta ejecución")
                return
            reservation_active = reservation_amount > 0
            action_req = ActionRequest(
                action=str(task.metadata.get("action", "work")),
                external_effect=bool(task.metadata.get("external_action", False)),
                irreversible=bool(task.metadata.get("irreversible", False)),
                cost=float(task.cost_estimate or 0),
            )
            safety_policy = dict(self.state.metadata.get("safety_policy", {}))
            safety_policy.setdefault("forbidden_actions", list(self.state.metadata.get("forbidden_actions", [])))
            if not self.safety.allowed(action_req, safety_policy):
                task.status = TaskStatus.NEEDS_REVIEW
                task.result = "Safety boundary requires explicit permission before this external/irreversible action."
                return
            provider = self.router.select(task, self.state)
            provider_name = provider.name
            if task.metadata.get("strategy_change_requested"):
                prior_provider = str(task.metadata.get("strategy_change_from") or "")
                applied = bool(provider_name and provider_name != prior_provider)
                task.metadata["strategy_change_selected_provider"] = provider_name
                task.metadata["strategy_change_applied"] = applied
                if applied:
                    task.metadata["strategy_change_applied_at"] = utcnow().isoformat()
                    task.metadata["strategy_change_requested"] = False
                else:
                    # A repeated failure demanded a real strategy change, but routing
                    # found no compatible alternative. Fail closed instead of claiming
                    # a changed strategy while executing the same provider again.
                    mark_blocked_safe(task, "strategy_change_unavailable", source="scheduler_provider_selection")
                    task.result = f"No distinct recovery strategy/provider is available after failure of {prior_provider or provider_name}."
                    self._activity_event("strategy_change_unavailable", task, provider=provider_name, detail="No distinct fallback provider/strategy available; task blocked safely")
                    return
            if not self.incidents_v2.allowed(self.state, f"provider:{provider_name}"):
                if reservation_active:
                    self.cost_engine.release(self.state, task.id)
                    reservation_active = False
                task.status = TaskStatus.RETRY if task.attempts < task.max_attempts else TaskStatus.FAILED
                task.result = f"Provider circuit is temporarily open: {provider_name}"
                task.metadata["incident_circuit_open"] = provider_name
                if task.status == TaskStatus.RETRY:
                    self._set_retry_backoff(task)
                return
            recovered_conversation_id = self.worker_sessions.recover_conversation_id(self.state, task, provider_name)
            if recovered_conversation_id and not task.conversation_id:
                task.conversation_id = recovered_conversation_id
            task.provider_name = provider_name
            self._active_provider[task.id] = provider_name
            task.metadata["provider_stage"] = "selected"
            task.metadata["provider_stage_ts"] = utcnow().isoformat()
            self._activity_event("provider_selected", task, provider=provider_name, detail="Proveedor elegido para esta tarea")
            task.metadata.setdefault("provider_attempts", []).append({"provider": provider_name, "attempt": int(task.attempts), "ts": utcnow().isoformat()})
            self.evidence_ledger_v2.append(self.state, "provider_selected", task=task, data={"provider": provider_name, "attempt": int(task.attempts)})
            if getattr(provider, "kind", None) == WorkerKind.BROWSER:
                self.application_recovery.checkpoint(self.state, task, provider=provider_name, url=task.metadata.get("browser_url"), conversation_id=task.conversation_id)
            instruction = task.metadata.pop("next_instruction", None)
            work_unit = WorkUnit.from_task(task)
            work_unit.metadata.setdefault("estimated_seconds", task.estimated_seconds)
            request_context = {
                "human_interventions_avoided": self.state.human_interventions_avoided,
                **self.context_builder.build(self.state, task),
            }
            if task.metadata.get("goal_continuity_audit"):
                request_context["goal_audit_evidence_candidates"] = self.goal_completion_gate.evidence_candidates(
                    self.state, limit=40
                )
                request_context["goal_audit_requirements"] = {
                    "min_evidence_refs": int(self.state.metadata.get("min_goal_audit_evidence_refs", 1)),
                    "min_grounded_refs": int(self.state.metadata.get("min_goal_audit_grounded_refs", 0)),
                    "generation": int(self.state.metadata.get("goal_continuity_generation", 0)),
                    "required_generation": int(self.state.metadata.get("min_goal_continuity_generations", 1)),
                    "deliverables": list(self.state.goal_deliverables),
                }
            # If a provider session was lost or the task is being resumed, add a
            # compact reconstruction sourced from durable project ledgers.
            if task.conversation_turns or task.metadata.get("interrupted_by_shutdown") or task.metadata.get("provider_context_recovery_v1"):
                request_context["provider_context_recovery"] = self.provider_context_recovery.rebuild(self.state, task, provider=provider_name)
            workspace_root = (self.state.metadata.get("workspace_v2") or {}).get("root")
            if workspace_root:
                try:
                    artifact_exchange = ArtifactExchangeLayer(workspace_root)
                    inputs = artifact_exchange.worker_inputs(self.state, task)
                    if inputs:
                        request_context["artifact_inputs"] = inputs
                except Exception as exc:  # noqa: BLE001
                    task.metadata.setdefault("artifact_exchange_errors", []).append(f"{type(exc).__name__}: {exc}")
            request = WorkerRequest(
                project_id=self.state.id,
                goal=self._goal_contract(),
                work_unit=work_unit,
                conversation_id=task.conversation_id,
                turn_index=task.conversation_turns,
                instruction=instruction,
                context=request_context,
            )
            task.metadata["provider_stage"] = "executing"
            self._activity_event("provider_executing", task, provider=provider_name, detail="Proveedor ejecutando; todavía no cuenta como progreso hasta completar una salida útil")
            self.quota_governor_v2.record_provider_call(self.state, task)
            self.decision_trace_v3.append(self.state, "provider_execute", task=task, data={"provider": provider_name})
            provider_timeout = float(task.metadata.get("provider_timeout_seconds", self.state.metadata.get("provider_timeout_seconds", 180.0)))
            try:
                result = await asyncio.wait_for(provider.execute(request), timeout=max(5.0, provider_timeout))
            except asyncio.TimeoutError as exc:
                task.metadata["provider_stage"] = "timeout"
                raise TimeoutError(f"Provider '{provider_name}' exceeded {provider_timeout:.0f}s") from exc
            task.metadata["provider_stage"] = "returned"
            task.metadata["provider_stage_ts"] = utcnow().isoformat()
            self.evidence_ledger_v2.append(self.state, "provider_returned", task=task, data={"success": bool(result.success), "artifacts": list(result.artifacts or []), "usage": dict(result.usage or {}) if isinstance(result.usage, dict) else {}})
            self._activity_event("provider_returned", task, provider=provider_name, detail="Resultado recibido; CEO lo está evaluando")
            task.actual_seconds = round(time.perf_counter() - started, 3)
            self.quota_governor_v2.record_compute_seconds(self.state, task, float(task.actual_seconds or 0.0))
            result_cost = float(result.usage.get("cost", 0.0) or 0.0) if isinstance(result.usage, dict) else 0.0
            settlement = self.cost_engine.settle(self.state, task.id, result_cost)
            reservation_active = False
            task.metadata["cost_settlement"] = settlement
            if result_cost:
                self.provider_policy.stats(self.state, provider_name)["cost"] = round(float(self.provider_policy.stats(self.state, provider_name).get("cost", 0.0)) + result_cost, 6)
            directive = extract_directive(result.text)
            if result.success and directive and getattr(directive, "write_files", None):
                if not workspace_root:
                    result.success = False
                    result.error = "Worker requested workspace file writes but no workspace root is configured."
                else:
                    try:
                        fs = FilesystemOperations(workspace_root)
                        exchange = ArtifactExchangeLayer(workspace_root)
                        written = []
                        for spec in list(directive.write_files)[:20]:
                            relative = str(spec.path).strip()
                            if not relative:
                                continue
                            row = fs.write_text(relative, str(spec.content))
                            verified = exchange.register(
                                self.state, relative, task_id=task.id, direction="worker_output"
                            )
                            evidence = self.deliverable_evidence_v1.record_file(
                                self.state, task, pathlib.Path(workspace_root) / relative, root=workspace_root
                            )
                            if relative not in result.artifacts:
                                result.artifacts.append(relative)
                            written.append({
                                "path": relative,
                                "sha256": row.get("sha256"),
                                "size_bytes": row.get("size_bytes"),
                                "artifact_id": verified.get("artifact_id"),
                                "evidence_ref": evidence.ref,
                            })
                        if written:
                            task.metadata.setdefault("verified_artifacts", []).extend(
                                x["artifact_id"] for x in written if x.get("artifact_id")
                            )
                            task.metadata["workspace_writes_v1"] = written
                            self._activity_event(
                                "workspace_artifact_written", task, provider=provider_name,
                                detail=f"Materializados y verificados {len(written)} archivo(s) en el workspace",
                            )
                    except Exception as exc:
                        result.success = False
                        result.error = f"Workspace artifact write failed: {type(exc).__name__}: {exc}"

            if result.success and not str(result.text or "").strip() and not list(result.artifacts or []):
                # A technically successful HTTP/browser turn with no usable payload is
                # not productive work. Route it through normal provider-failure recovery.
                result.success = False
                result.error = result.error or "Provider returned an empty result with no artifacts"
                task.metadata["empty_provider_response"] = {
                    "provider": provider_name,
                    "attempt": int(task.attempts),
                    "ts": utcnow().isoformat(),
                }
            self._update_provider_stats(provider_name, task.actual_seconds, not result.success)
            decision = self.controller.decide(self.state, task, result)
            preexisting_task_ids = set(self.state.tasks)
            spawned = self.controller.apply(self.state, task, result, decision)
            if (
                task.status == TaskStatus.COMPLETE
                and (
                    "verification" in set(task.required_capabilities or [])
                    or str(task.metadata.get("task_role") or "") == "verification"
                )
                and (task.result or "").strip()
            ):
                task.metadata["independently_verified"] = True
                task.metadata["verification_application"] = {
                    "verified_at": utcnow().isoformat(),
                    "provider": provider_name,
                    "task_id": task.id,
                }
            if task.metadata.get("goal_continuity_audit") and spawned:
                spawned = self._filter_novel_continuity_followups(
                    audit=task, spawned=spawned, preexisting_task_ids=preexisting_task_ids
                )

            # A continuity audit is the explicit bridge between one finite work
            # batch and the next.  Completion is accepted only with the exact audit
            # marker; otherwise the task must either spawn follow-ups or retry.
            if task.metadata.get("goal_continuity_audit") and task.status == TaskStatus.COMPLETE:
                audit_text = (task.result or "")
                directive = directive or extract_directive(result.text)
                claimed_refs = list(getattr(directive, "evidence_refs", []) or []) if directive else []
                auto_refs = self.goal_completion_gate.auto_evidence_refs(self.state)
                evidence_refs = list(dict.fromkeys([str(x) for x in claimed_refs + auto_refs if str(x).strip()]))
                verdict = self.goal_completion_gate.evaluate(self.state, evidence_refs=evidence_refs)
                task.metadata["goal_audit_verdict"] = verdict.to_dict()
                if "CEO_GOAL_AUDIT: PASS" in audit_text and verdict.eligible:
                    self.state.metadata["goal_audit_passed"] = True
                    self.state.metadata["goal_audit_evidence"] = {
                        "task_id": task.id,
                        "provider": provider_name,
                        "generation": task.metadata.get("goal_continuity_generation"),
                        "verified_at": utcnow().isoformat(),
                        "evidence_refs": list(verdict.evidence_refs),
                        "grounded_refs": list(verdict.grounded_refs),
                    }
                    completion_evidence = self.state.metadata.setdefault("completion_evidence", {})
                    supporting_task = (verdict.grounded_refs or verdict.evidence_refs)[0] if (verdict.grounded_refs or verdict.evidence_refs) else None
                    for criterion in self.state.completion_criteria:
                        completion_evidence[criterion] = {
                            "task_id": supporting_task,
                            "source": "goal_audit_verified_references",
                            "evidence_refs": list(verdict.evidence_refs),
                        }
                    self.state.metadata.pop("last_goal_audit_rejection", None)
                    self._activity_event("goal_audit_pass", task, provider=provider_name, detail="Locked goal passed strict evidence gate")
                elif spawned:
                    self.state.metadata["goal_audit_passed"] = False
                    self.state.metadata["continuity_nonspawn_rejections"] = 0
                    self.state.metadata["last_goal_continuity_spawn"] = {
                        "task_id": task.id,
                        "count": len(spawned),
                        "ts": utcnow().isoformat(),
                    }
                    self._activity_event("goal_replenished", task, provider=provider_name, detail=f"Spawned {len(spawned)} next work unit(s)")
                else:
                    self.state.metadata["goal_audit_passed"] = False
                    self.state.metadata["last_goal_audit_rejection"] = {
                        "task_id": task.id,
                        "ts": utcnow().isoformat(),
                        "gaps": list(verdict.gaps),
                        "evidence_refs": list(verdict.evidence_refs),
                    }
                    gaps = "; ".join(verdict.gaps[:12]) or "missing grounded completion evidence"
                    nonspawn = int(self.state.metadata.get("continuity_nonspawn_rejections", 0)) + 1
                    self.state.metadata["continuity_nonspawn_rejections"] = nonspawn
                    # Repeating the same control audit without producing domain work is
                    # not progress. After two non-spawning rejections, deterministically
                    # bridge back into executable work instead of oscillating forever
                    # between 95/100 or burning retries on the audit itself.
                    if nonspawn >= 2:
                        fallback = self._spawn_goal_gap_recovery_batch(task, list(verdict.gaps))
                        task.status = TaskStatus.SUPERSEDED
                        task.metadata["superseded_reason"] = "nonspawning_goal_audit_replaced_by_gap_recovery_batch"
                        task.metadata["continuity_gap_recovery_spawned"] = [t.id for t in fallback]
                        self.state.metadata["continuity_nonspawn_rejections"] = 0
                        self._activity_event(
                            "goal_audit_gap_recovery_batch", task, provider=provider_name,
                            detail=f"Audit produced no work twice; spawned {len(fallback)} deterministic gap-closure tasks",
                        )
                    elif task.attempts < task.max_attempts:
                        task.status = TaskStatus.RETRY
                        task.metadata["next_instruction"] = (
                            "Your attempted goal completion was REJECTED by the deterministic evidence gate. "
                            f"Gaps: {gaps}. The audit itself cannot be evidence. "
                            "Do NOT repeat CEO_GOAL_AUDIT: PASS unless those gaps are resolved with existing real task IDs in evidence_refs. "
                            "Otherwise use CEO_RESULT status=spawn with 3-8 concrete follow-up tasks that close the gaps."
                        )
                        self._set_retry_backoff(task)
                        self._activity_event("goal_audit_rejected", task, provider=provider_name, detail=f"Completion rejected: {gaps}")
                    else:
                        # A continuity audit is internal control-plane work. It must
                        # never stop the unattended loop waiting for a human review.
                        # Retire this exhausted audit; the watchdog will create one
                        # fresh atomic audit on the next cycle.
                        task.status = TaskStatus.SUPERSEDED
                        task.metadata["completion_rejected"] = list(verdict.gaps)
                        task.metadata["continuity_audit_exhausted"] = utcnow().isoformat()
                        task.metadata["superseded_reason"] = "goal_audit_retry_budget_exhausted"
                        self._activity_event(
                            "goal_audit_exhausted_recycle",
                            task,
                            provider=provider_name,
                            detail="Internal audit exhausted retries; recycling autonomously instead of requesting human review",
                        )
            if task.status == TaskStatus.COMPLETE and task.metadata.get("autonomy_recovery"):
                recovery = self.autonomous_loop.apply_recovery_result(self.state, task)
                task.metadata["recovery_application"] = recovery
                if recovery.get("superseded"):
                    for target_id in task.metadata.get("recovery_targets", []):
                        target = self.state.tasks.get(str(target_id))
                        if not target:
                            continue
                        failure_type = ((target.metadata.get("failure_intelligence_v2") or {}).get("taxonomy") or {}).get("category", "unknown")
                        self.cognitive.recovery_ranker.record(
                            self.state, failure_type=failure_type, action="autonomy_recovery", success=True,
                            cost=result_cost, seconds=float(task.actual_seconds or 0.0),
                        )
            if task.status == TaskStatus.COMPLETE and is_productive(task, self.state):
                self._record_goal_deliverable_evidence(task)
            if task.status == TaskStatus.COMPLETE and self.state.metadata.get("strict_completion_audit") and self._requires_generic_completion_audit(task):
                accepted, audit_reasons = self.completion_engine.auditor.audit_task(task)
                if not accepted:
                    task.status = TaskStatus.NEEDS_REVIEW
                    task.metadata["completion_rejected"] = audit_reasons
                    self.provider_policy.record_task_outcome(self.state, provider_name, task, success=False, seconds=float(task.actual_seconds or 0), turns=max(1,task.conversation_turns), completion_rejected=True)
                    self.release_candidate.portfolio.record(self.state, provider_name, success=False, quality=0.0, latency_seconds=float(task.actual_seconds or 0), task_type=self.provider_policy.task_type(task))
                    self.release_candidate.degradation.assess(self.state, provider_name)
            if not result.success:
                if result.error:
                    task.metadata["last_provider_error"] = str(result.error)
                    task.metadata.setdefault("provider_errors", []).append({
                        "provider": provider_name,
                        "attempt": int(task.attempts),
                        "error": str(result.error),
                    })
                avoid = task.metadata.setdefault("avoid_providers", [])
                if provider_name not in avoid:
                    avoid.append(provider_name)
                rate_limited = "429" in str(result.error)
                task.metadata["provider_resilience_v2"] = self.provider_resilience_v2.classify(str(result.error), task.attempts).to_dict()
                if rate_limited: task.metadata["rate_limited"] = True
                self.provider_policy.record_failure(self.state, provider_name, rate_limited=rate_limited)
                self.incidents_v2.record_failure(self.state, f"provider:{provider_name}", str(result.error or "provider reported failure"), threshold=3, cooldown_seconds=30)
                self._recovery_event(
                    "provider_failure",
                    task,
                    detail=str(result.error or "provider reported failure"),
                    provider=provider_name,
                )
                predicted = task.metadata.get("predicted_success_probability")
                task_type = ":".join(sorted(task.required_capabilities or ["general"]))
                if predicted is not None:
                    self.confidence_calibration.record(self.state, predicted=float(predicted), success=False, context=task_type)
                    self.cognitive.calibration.record(self.state, predicted=float(predicted), success=False, task_type=task_type, agent=task_type, model=provider_name, tool="provider")
                failure_text = str(result.error or "provider reported failure")
                if getattr(provider, "kind", None) == WorkerKind.BROWSER:
                    app_recovery = self.application_recovery.record_failure(self.state, task, provider=provider_name, error=failure_text)
                    task.metadata["application_recovery"] = app_recovery
                    if app_recovery.get("requires_human"):
                        task.status = TaskStatus.NEEDS_REVIEW
                task.metadata["failure_count"] = int(task.metadata.get("failure_count", 0)) + 1
                taxonomy = self.cognitive.failures.classify(failure_text, task=task)
                root_cause = self.cognitive.root_cause.analyze(self.state, task, failure_text, recent_events=self.state.metadata.get("recovery_events", []))
                repeat = self.cognitive.repeat_guard.record(task, action="provider_execute", error=failure_text, progress_gain=float(task.metadata.get("strategy_progress_gain", 0.0)))
                ranked_recovery = self.cognitive.recovery_ranker.rank(self.state, taxonomy["category"], ["retry", "fallback_provider", "replan", "escalate"])
                task.metadata["failure_intelligence_v2"] = {"taxonomy": taxonomy, "root_cause": root_cause, "repeat_guard": repeat, "ranked_recovery": ranked_recovery}
                failure_row = self.production_intelligence.failure_memory.record(self.state, task, error=failure_text)
                recovery_plan = self.production_intelligence.recovery.plan(self.state, task, str(result.error or "provider reported failure"))
                task.metadata["recovery_plan_v2"] = {"action": recovery_plan.action, "confidence": recovery_plan.confidence, "reason": recovery_plan.reason, "alternatives": recovery_plan.alternatives, "failure_signature": failure_row.get("signature")}
                self.structured_memory.capture_failure(self.state, task, error=failure_text)
            if task.status in {TaskStatus.COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.PARTIAL_COMPLETE}:
                # Register sources before quality so source independence affects confidence.
                source_ids=[]
                for src in task.metadata.get("sources", []):
                    if isinstance(src, str): source_ids.append(self.integrator.sources.register(self.state, url=src))
                    elif isinstance(src, dict):
                        source_ids.append(self.integrator.sources.register(self.state, title=str(src.get("title","")), url=str(src.get("url","")), doi=str(src.get("doi","")), content=str(src.get("content","")), quality=float(src.get("quality",.5)), metadata=src.get("metadata") or {}))
                task.metadata["source_ids"] = source_ids
                independent = self.integrator.sources.independent_count(self.state, source_ids)
                source_quality = self.integrator.sources.average_quality(self.state, source_ids)
                task.metadata["independent_source_count"] = independent
                task.metadata["source_quality"] = source_quality
                siblings=[]
                if task.parent_id and task.parent_id in self.state.tasks:
                    siblings=[self.state.tasks[x] for x in self.state.tasks[task.parent_id].children if x in self.state.tasks and x!=task.id and self.state.tasks[x].status in {TaskStatus.COMPLETE,TaskStatus.COMPLETE_WITH_UNCERTAINTY}]
                consensus=self.consensus_builder.build(self.state, siblings+[task])
                task.metadata["consensus"] = consensus["consensus"]
                assessment = self.quality_engine.assess(task, agreement=consensus["consensus"], source_count=len(source_ids), source_quality=source_quality, independent_sources=independent, verification_depth=float(task.metadata.get("verification_depth",0)))
                task.confidence = assessment.confidence; task.quality_score = assessment.quality
                task.metadata["quality_dimensions"]={"evidence_strength":assessment.evidence_strength,"source_quality":assessment.source_quality,"consensus":assessment.consensus,"verification_depth":assessment.verification_depth}
                gate = self.quality_gate.evaluate(self.state, task, quality=assessment.quality)
                if not gate.accepted:
                    correction = self.self_correction.recover_quality_failure(self.state, task, gate)
                    task.metadata["quality_gate_correction"] = correction
                    self.structured_memory.capture_failure(self.state, task, error="quality_gate: " + ", ".join(gate.reasons))
                    self.provider_policy.record_task_outcome(
                        self.state, provider_name, task, success=False,
                        seconds=float(task.actual_seconds or 0), turns=max(1, task.conversation_turns),
                        completion_rejected=True,
                    )
                    self.audit_log.emit(self.state, "quality_gate_rejected", {"task_id": task.id, "provider": provider_name, "reasons": gate.reasons, "action": correction.get("action")})
                    self.evidence_ledger_v2.append(self.state, "quality_gate_rejected", task=task, data={"reasons": list(gate.reasons), "action": correction.get("action")})
                    self._activity_event("quality_gate_rejected", task, provider=provider_name, detail=", ".join(gate.reasons))
                    if task.status == TaskStatus.RETRY:
                        self._set_retry_backoff(task)
                    return
                task.metadata.pop("quality_correction_pending", None)
                self.provider_policy.record_quality(self.state, provider_name, assessment.quality)
                self.integrator.integrate_task(self.state, task)
                self.structured_memory.capture_task_success(self.state, task)
                if is_productive(task, self.state):
                    self.completion_engine.yield_tracker.record(self.state, float(task.metadata.get("novelty",1.0)))
                self.provider_policy.record_task_outcome(self.state, provider_name, task, success=True, seconds=float(task.actual_seconds or 0), quality=assessment.quality, turns=max(1,task.conversation_turns), cost=result_cost)
                self.incidents_v2.record_success(self.state, f"provider:{provider_name}")
                self.release_candidate.portfolio.record(self.state, provider_name, success=True, quality=assessment.quality, latency_seconds=float(task.actual_seconds or 0), cost=result_cost, task_type=self.provider_policy.task_type(task))
                self.release_candidate.degradation.assess(self.state, provider_name)
                task_type = ":".join(sorted(task.required_capabilities or ["general"]))
                self.outcome_learning.record(self.state, task_type=task_type, strategy=provider_name, success=True, quality=assessment.quality, cost=result_cost, seconds=float(task.actual_seconds or 0))
                predicted = task.metadata.get("predicted_success_probability")
                if predicted is not None:
                    self.confidence_calibration.record(self.state, predicted=float(predicted), success=True, context=task_type)
                    self.cognitive.calibration.record(self.state, predicted=float(predicted), success=True, task_type=task_type, agent=task_type, model=provider_name, tool="provider")
                procedure_steps = task.metadata.get("procedure_steps") or []
                if procedure_steps:
                    self.sop_builder.observe(self.state, task_type=task_type, steps=procedure_steps, verified_success=assessment.quality >= .65)
                self.semantic_memory.add(self.state, kind="task_result", text=f"{task.title} {task.result or ''}", source_ref=task.id, importance=assessment.quality, tags=["task", provider_name])
                bstats=self.state.metadata.setdefault("batch_stats",{})
                if task.metadata.get("batch_task"):
                    n=max(1,len(task.metadata.get("batched_task_ids",[])));per=float(task.actual_seconds or 0)/n;old=float(bstats.get("batch_seconds_per_item",per));bstats["batch_seconds_per_item"]=round(old*.7+per*.3,4)
                elif task.estimated_seconds<=.3:
                    sec=float(task.actual_seconds or 0);old=float(bstats.get("single_seconds",sec));bstats["single_seconds"]=round(old*.7+sec*.3,4)
                self.provenance.record(self.state, task)
                self.evidence_ledger_v2.append(self.state, "task_complete", task=task, data={"quality": assessment.quality, "confidence": assessment.confidence, "source_ids": list(task.metadata.get("source_ids", [])), "artifacts": list(task.metadata.get("artifacts", []))})
                if is_productive(task, self.state) and (task.result or "").strip():
                    self.deliverable_evidence_v1.record_text(self.state, task, task.result or "", kind="productive_result")
                self.decision_trace_v3.append(self.state, "task_complete", task=task, data={"provider": provider_name, "quality": assessment.quality, "confidence": assessment.confidence})
                self.audit_log.emit(self.state, "task_complete", {"task_id": task.id, "provider": provider_name, "quality": assessment.quality})
                self._activity_event("task_complete", task, provider=provider_name, detail=f"Completada con calidad {assessment.quality:.2f}")
                self.telemetry.record(self.state, "task_complete", task_id=task.id, provider=provider_name, seconds=task.actual_seconds, quality=assessment.quality)
                requirement_ids = [str(x) for x in task.metadata.get("requirement_ids", [])]
                if requirement_ids:
                    self.quality_engineering.record_task_completion(
                        self.state, task_id=task.id, requirement_ids=requirement_ids,
                        implementation_refs=[str(x) for x in task.metadata.get("implementation_refs", [])],
                        test_ref=task.metadata.get("test_ref"), evidence_ref=f"task:{task.id}",
                        independently_verified=bool(task.metadata.get("independently_verified", False)),
                    )
                if self.procedural_memory and assessment.quality >= 0.65:
                    proc_key = ":".join(sorted(task.required_capabilities or ["general"]))
                    self.procedural_memory.record(proc_key, {"provider": provider_name, "quality": assessment.quality, "seconds": task.actual_seconds, "pattern": task.title[:120]})
                    self.procedural_memory.record_outcome(proc_key, True)
                self._maybe_schedule_verification(task, assessment.needs_review)
                if task.metadata.get("verification_task"):
                    verdict = self.layered_verification.apply_result(self.state, task)
                    task.metadata["verification_application"] = verdict
                    if verdict.get("applied"):
                        target_id = str(task.metadata.get("verifies") or "") or None
                        self.production_intelligence.evidence.add(
                            self.state, source_kind="verification", source_ref=task.id,
                            task_id=target_id, direct=True, independent_group=f"verifier:{provider_name}",
                            strength=float(verdict.get("confidence") or .7),
                            outcome="contradicts" if verdict.get("verdict") == "fail" else "supports" if verdict.get("verdict") == "pass" else "neutral",
                            payload=verdict,
                        )
                    if verdict.get("applied"):
                        self._activity_event(
                            "verification_verdict",
                            task,
                            provider=provider_name,
                            detail=f"Veredicto independiente: {verdict.get('verdict', 'unclassified')}",
                        )
                self._maybe_schedule_conflict_review(task)
            if task.status == TaskStatus.RETRY:
                self._set_retry_backoff(task)
        except asyncio.CancelledError:
            # The live watchdog may already have classified the interrupted task as
            # FAILED or NEEDS_REVIEW. Do not overwrite that safer decision.
            if task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.RETRY
                self._set_retry_backoff(task)
            raise
        except Exception as exc:  # noqa: BLE001 - scheduler isolates worker failure
            provider_decision = self.provider_resilience_v2.classify(str(exc), max(1, int(task.attempts)))
            wait_categories = {"quota", "provider_unavailable", "model_unavailable", "transient"}
            if provider_decision.category in wait_categories:
                retry_seconds = max(30, int(provider_decision.retry_after_seconds or 0))
                global_wait = dict(self.state.metadata.get("provider_wait_v1") or {})
                if provider_decision.category == "quota" or global_wait.get("category") == "quota":
                    retry_seconds = max(300, retry_seconds)
                retry_at = time.time() + retry_seconds
                task.status = TaskStatus.BLOCKED
                task.attempts = max(0, int(task.attempts) - 1)
                task.worker_id = None
                task.result = f"WAITING_PROVIDER: {provider_decision.category}; retry in {retry_seconds}s. No recovery budget consumed."
                task.metadata["provider_stage"] = "waiting_provider"
                task.metadata["provider_stage_ts"] = utcnow().isoformat()
                task.metadata["provider_resilience_v2"] = provider_decision.to_dict()
                task.metadata["waiting_provider_v1"] = {
                    "active": True,
                    "category": provider_decision.category,
                    "provider": provider_name,
                    "retry_after_seconds": retry_seconds,
                    "retry_after_ts": retry_at,
                    "error": f"{type(exc).__name__}: {exc}"[:1000],
                    "since": utcnow().isoformat(),
                }
                task.metadata["retry_after_ts"] = retry_at
                wait = self.state.metadata.setdefault("provider_wait_v1", {})
                task_ids = list(dict.fromkeys(list(wait.get("task_ids") or []) + [task.id]))
                wait.update({
                    "active": True,
                    "category": "quota" if global_wait.get("category") == "quota" else provider_decision.category,
                    "provider": provider_name,
                    "retry_after_seconds": retry_seconds,
                    "retry_after_ts": retry_at,
                    "task_ids": task_ids[-100:],
                    "reason": str(exc)[:1000],
                    "updated_at": utcnow().isoformat(),
                    "recoveries_consumed": 0,
                })
                if provider_name:
                    self.provider_policy.record_failure(
                        self.state, provider_name,
                        rate_limited=provider_decision.category == "quota",
                    )
                self.decision_trace_v3.append(
                    self.state, "provider_wait", task=task,
                    data={"provider": provider_name, **provider_decision.to_dict()},
                )
                self.evidence_ledger_v2.append(
                    self.state, "provider_wait", task=task,
                    data={"provider": provider_name, "category": provider_decision.category,
                          "retry_after_seconds": retry_seconds, "recovery_budget_consumed": False},
                )
                self._activity_event(
                    "provider_wait", task, provider=provider_name,
                    detail=f"{provider_decision.category}: espera de proveedor; no cuenta como recuperación",
                )
                return

            task.metadata["provider_stage"] = "failed"
            task.metadata["provider_stage_ts"] = utcnow().isoformat()
            task.metadata["failure_count"] = int(task.metadata.get("failure_count", 0)) + 1
            avoid = task.metadata.setdefault("avoid_providers", [])
            if provider_name not in avoid: avoid.append(provider_name)
            rate_limited = "429" in str(exc)
            task.metadata["provider_resilience_v2"] = self.provider_resilience_v2.classify(str(exc), task.attempts).to_dict()
            if rate_limited: task.metadata["rate_limited"] = True
            self.provider_policy.record_failure(self.state, provider_name, rate_limited=rate_limited)
            self.incidents_v2.record_failure(self.state, f"provider:{provider_name}", f"{type(exc).__name__}: {exc}", threshold=3, cooldown_seconds=30)
            task.result = f"ERROR: {exc}"
            task.actual_seconds = round(time.perf_counter() - started, 3)
            self.quota_governor_v2.record_compute_seconds(self.state, task, float(task.actual_seconds or 0.0))
            self.decision_trace_v3.append(self.state, "task_error", task=task, data={"provider": provider_name, "error_type": type(exc).__name__})
            self.structured_memory.capture_failure(self.state, task, error=f"{type(exc).__name__}: {exc}")
            self._activity_event("task_error", task, provider=provider_name, detail=f"{type(exc).__name__}: {exc}")
            self._update_provider_stats(provider_name, task.actual_seconds, True)
            self.provider_policy.record_task_outcome(self.state, provider_name, task, success=False, seconds=float(task.actual_seconds or 0), turns=max(1, task.conversation_turns))
            self.release_candidate.portfolio.record(self.state, provider_name, success=False, quality=0.0, latency_seconds=float(task.actual_seconds or 0), task_type=self.provider_policy.task_type(task))
            self.release_candidate.degradation.assess(self.state, provider_name)
            task_type = ":".join(sorted(task.required_capabilities or ["general"]))
            self.outcome_learning.record(self.state, task_type=task_type, strategy=provider_name, success=False, quality=0.0, cost=0.0, seconds=float(task.actual_seconds or 0))
            predicted = task.metadata.get("predicted_success_probability")
            if predicted is not None:
                task_type = ":".join(sorted(task.required_capabilities or ["general"]))
                self.confidence_calibration.record(self.state, predicted=float(predicted), success=False, context=task_type)
            failure_row = self.production_intelligence.failure_memory.record(self.state, task, error=str(exc))
            if 'provider' in locals() and getattr(provider, "kind", None) == WorkerKind.BROWSER:
                app_recovery = self.application_recovery.record_failure(self.state, task, provider=provider_name, error=f"{type(exc).__name__}: {exc}")
                task.metadata["application_recovery"] = app_recovery
            self.evidence_ledger_v2.append(self.state, "task_error", task=task, data={"error_type": type(exc).__name__, "error": str(exc)[:1000], "provider": provider_name})
            recovery_plan = self.production_intelligence.recovery.plan(self.state, task, str(exc))
            task.metadata["recovery_plan_v2"] = {"action": recovery_plan.action, "confidence": recovery_plan.confidence, "reason": recovery_plan.reason, "alternatives": recovery_plan.alternatives, "failure_signature": failure_row.get("signature")}
            if self.procedural_memory:
                proc_key=":".join(sorted(task.required_capabilities or ["general"]));self.procedural_memory.record_outcome(proc_key,False)
            task.status = TaskStatus.RETRY if task.attempts < task.max_attempts else TaskStatus.FAILED
            self._recovery_event(
                "exception_retry" if task.status == TaskStatus.RETRY else "terminal_failure",
                task,
                detail=f"{type(exc).__name__}: {exc}",
                provider=provider_name,
            )
            if task.status == TaskStatus.RETRY:
                self._set_retry_backoff(task)
            elif task.status == TaskStatus.FAILED and self.state.depth_percent >= 60:
                children=self.adaptive_decomposer.split_failed(self.state,task)
                if children:
                    task.metadata["failure_recovered_by_split"]=[c.id for c in children]
                    self.audit_log.emit(self.state,"failure_split",{"task_id":task.id,"children":len(children)})
            elif self.state.notifications_enabled:
                self.notifications.emit(
                    self.state,
                    title="Tarea fallida",
                    body=f"{task.title}: {exc}",
                    severity="error",
                    data={"task_id": task.id},
                )
        finally:
            if reservation_active:
                released = self.cost_engine.release(self.state, task.id)
                if released:
                    task.metadata["cost_reservation_released"] = released
            self.worker_lifecycle_v2.release(self.state, task, reason=f"terminal:{task.status.value}")
            self._active_provider.pop(task.id, None)

    @staticmethod
    def _requires_generic_completion_audit(task: Task) -> bool:
        """Generic task completion audit is for domain work, not control-plane work.

        Internal recovery, continuity and verification tasks already have dedicated
        deterministic gates. Running the generic acceptance-evidence auditor on them
        can falsely convert a successful control result into NEEDS_REVIEW and strand
        dependent verification work.
        """
        return is_productive(task)

    def _record_goal_deliverable_evidence(self, task: Task) -> None:
        if not self.state.goal_deliverables:
            return
        artifacts = [str(x) for x in task.metadata.get("artifacts", [])]
        result_text = (task.result or "").lower()
        evidence = self.state.metadata.setdefault("deliverable_evidence", {})
        for deliverable in self.state.goal_deliverables:
            if evidence.get(deliverable):
                continue
            needle = deliverable.lower().strip()
            artifact_match = next((a for a in artifacts if needle and (needle in a.lower() or a.lower().endswith(needle))), None)
            explicit_marker = f"deliverable:{needle}" in result_text if needle else False
            if artifact_match:
                evidence[deliverable] = {"task_id": task.id, "artifact": artifact_match}
            elif explicit_marker:
                evidence[deliverable] = {"task_id": task.id, "result_marker": True}

    def _set_retry_backoff(self, task: Task) -> None:
        # Short in MVP tests, exponential in production-scale runs.
        cap = 300.0 if task.metadata.pop("rate_limited", False) else 60.0
        base = 2.0 if cap > 60 else 0.25
        delay = min(cap, base * (2 ** max(0, task.attempts - 1)))
        task.metadata["retry_after_ts"] = utcnow().timestamp() + delay

    @staticmethod
    def _normalized_task_title(title: str) -> str:
        import re
        return re.sub(r"[^a-z0-9áéíóúüñ]+", " ", str(title or "").lower()).strip()

    def _filter_novel_continuity_followups(self, *, audit: Task, spawned: list[Task], preexisting_task_ids: set[str]) -> list[Task]:
        """Reject audit follow-ups that only recreate work CEO already knows.

        The continuity controller used to treat any `status=spawn` response as forward
        progress.  Gemini could therefore keep returning the same 3-8 suggestions; the
        optimizer later superseded them as duplicates, and the next audit repeated the
        cycle forever.  Filtering before the audit accounting makes a duplicate-only
        spawn equivalent to *no spawn*, so the deterministic gap-recovery bridge is
        activated instead of burning hundreds of control cycles.
        """
        known: set[str] = set()
        for tid in preexisting_task_ids:
            prior = self.state.tasks.get(tid)
            if prior is None or self._is_goal_continuity_task(prior):
                continue
            norm = self._normalized_task_title(prior.title)
            if norm:
                known.add(norm)

        novel: list[Task] = []
        dropped: list[str] = []
        seen_new: set[str] = set()
        for child in spawned:
            norm = self._normalized_task_title(child.title)
            if not norm or norm in known or norm in seen_new:
                child.status = TaskStatus.SUPERSEDED
                child.metadata["superseded_reason"] = "duplicate_continuity_followup"
                child.metadata["duplicate_spawned_by"] = audit.id
                dropped.append(child.id)
                continue
            seen_new.add(norm)
            novel.append(child)

        if dropped:
            audit.metadata.setdefault("continuity_duplicate_followups_dropped", []).extend(dropped)
            self.state.metadata["continuity_duplicate_spawn_drops"] = int(
                self.state.metadata.get("continuity_duplicate_spawn_drops", 0)
            ) + len(dropped)
            self._activity_event(
                "continuity_duplicate_spawn_filtered", audit,
                provider=audit.provider_name,
                detail=f"Dropped {len(dropped)} duplicate continuity follow-up(s); {len(novel)} novel remain",
            )
        return novel

    def _spawn_goal_gap_recovery_batch(self, audit: Task, gaps: list[str]) -> list[Task]:
        """Create a bounded executable batch when the LLM audit fails to spawn work.

        This is a liveness fallback, not a completion shortcut. The tasks are ordinary
        domain work and must still execute, produce results/evidence, and pass the
        existing completion gate.
        """
        gap_text = "; ".join(str(g) for g in gaps[:8]) or "unresolved goal evidence and deliverable gaps"
        prefix = (self.state.goal or "Locked project goal")[:160]
        generation = int(audit.metadata.get("goal_continuity_generation", 0) or 0)
        tag = f" [cycle {generation}]" if generation else ""
        missing_deliverables = [
            str(g).split(":", 1)[1]
            for g in gaps
            if str(g).startswith("deliverable_unproven:") and ":" in str(g)
        ]
        if missing_deliverables:
            target = missing_deliverables[0].strip()
            specs = [
                (
                    f"Closure repair: create missing deliverable {target}" + tag,
                    (
                        f"Create the missing deliverable {target} in the CEO workspace. "
                        "Your substantive response must be the complete intended file content and your CEO_RESULT must use "
                        "Set write_files to one entry whose path is the target filename and whose content is the complete file content. "
                        "Do not merely describe the file. Use the locked project goal to include every requested field."
                    ),
                    ["reasoning"], "general",
                ),
                (
                    f"Closure repair: independently verify deliverable {target}" + tag,
                    (
                        f"Independently verify that {target} exists in the workspace, is non-empty, and satisfies the locked goal. "
                        "Report concrete verification findings; do not fabricate filesystem evidence."
                    ),
                    ["reasoning", "verification"], "code_review",
                ),
            ]
        else:
            specs = [
            (
                "Continuity recovery: map the highest-impact unresolved requirement to one concrete next action" + tag,
                f"Inspect the locked goal and current evidence. Gaps: {gap_text}. Identify one highest-impact unmet requirement and turn it into a concrete executable action. Goal: {prefix}",
                ["reasoning"], "reasoning",
            ),
            (
                "Continuity recovery: execute the highest-impact unresolved requirement and produce evidence" + tag,
                "Execute the concrete next action identified by the preceding gap analysis. Produce a substantive deliverable/result and explicit evidence; do not merely restate a plan.",
                ["reasoning"], "general",
            ),
            (
                "Continuity recovery: independently verify the new result against the locked goal" + tag,
                "Verify the preceding result against the locked goal and acceptance criteria. Record what was actually verified, what remains unresolved, and concrete evidence references where available.",
                ["reasoning", "verification"], "code_review",
            ),
            ]
        spawned: list[Task] = []
        previous_id = audit.id
        for index, (title, description, caps, kind) in enumerate(specs):
            task = Task(
                title=title,
                description=description,
                priority=max(80, 98 - index),
                status=TaskStatus.WAITING,
                dependencies=[previous_id],
                estimated_seconds=60.0,
                max_attempts=4,
                required_capabilities=caps,
                acceptance_criteria=[
                    "Produces substantive non-control work",
                    "Does not claim unperformed actions or evidence",
                    "Moves the locked goal toward a verifiable next state",
                ],
                metadata={
                    "continuity_gap_recovery": True,
                    "spawned_by": audit.id,
                    "preferred_kind": "api",
                    "task_kind": kind,
                    "task_role": ("productive" if index == 1 else "verification" if index == 2 else "control"),
                    "productive_recovery_work": index == 1,
                    "preemptible": True,
                    "checkpointable": False,
                    "goal_gap_snapshot": list(gaps[:12]),
                },
            )
            self.state.tasks[task.id] = task
            self.state.root_task_ids.append(task.id)
            spawned.append(task)
            previous_id = task.id
        return spawned

    def _update_provider_stats(self, provider: str, seconds: float, failed: bool) -> None:
        all_stats = self.state.metadata.setdefault("provider_stats", {})
        stats = all_stats.setdefault(provider, {"runs": 0, "failures": 0, "total_seconds": 0.0})
        stats["runs"] += 1
        stats["failures"] += int(failed)
        stats["total_seconds"] = round(float(stats.get("total_seconds", 0.0)) + seconds, 4)
        stats["average_seconds"] = round(stats["total_seconds"] / max(1, stats["runs"]), 4)

    def _collect_finished(self) -> None:
        finished = [task_id for task_id, future in self._active.items() if future.done()]
        for task_id in finished:
            future = self._active.get(task_id)
            task = self.state.tasks.get(task_id)
            provider = self._active_provider.get(task_id) or (task.provider_name if task else None)

            # DEV307 invariant: a completed Future may never disappear while its
            # durable task still says RUNNING. That state was interpreted by the
            # worker watchdog as an orphan and created recovery storms in the field.
            if task is not None and task.status == TaskStatus.RUNNING:
                outcome = "completed_without_terminal_state"
                detail = ""
                if future is not None:
                    if future.cancelled():
                        outcome = "cancelled_without_state_handoff"
                    else:
                        try:
                            exc = future.exception()
                        except BaseException as err:  # cancelled/broken future access
                            exc = err
                        if exc is not None:
                            outcome = "exception_without_state_handoff"
                            detail = f"{type(exc).__name__}: {exc}"[:1000]

                count = int(task.metadata.get("worker_terminal_normalization_count", 0) or 0) + 1
                task.metadata["worker_terminal_normalization_count"] = count
                task.metadata["worker_terminal_normalization_v1"] = {
                    "outcome": outcome,
                    "detail": detail,
                    "provider": provider,
                    "count": count,
                    "ts": utcnow().isoformat(),
                    "recovery_budget_consumed": False,
                }
                task.metadata["provider_stage"] = "terminal_normalized"
                task.metadata["provider_stage_ts"] = utcnow().isoformat()
                task.metadata["live_recovery_reason"] = "worker_future_finished_without_durable_state"
                task.worker_id = None

                # This is an internal bookkeeping failure, not a provider/task
                # failure. Permit at most two normalizations before failing the unit
                # so fallback/replanning can take over without an infinite loop.
                if count <= 2:
                    task.status = TaskStatus.RETRY
                    task.attempts = max(0, int(task.attempts) - 1)
                    task.metadata["retry_after_ts"] = time.time() + 1.0
                    if not (task.result or "").strip():
                        task.result = "Internal worker handoff normalized; retrying without consuming recovery budget."
                else:
                    task.status = TaskStatus.FAILED
                    task.result = (task.result or "") + (
                        " Internal worker handoff failed repeatedly; bounded terminal failure for autonomous replanning."
                    )

                hist = self.state.metadata.setdefault("worker_terminal_normalization_history", [])
                hist.append({
                    "task_id": task.id,
                    "outcome": outcome,
                    "count": count,
                    "provider": provider,
                    "ts": utcnow().isoformat(),
                    "recovery_budget_consumed": False,
                })
                del hist[:-200]

            self._active.pop(task_id, None)
            self._active_provider.pop(task_id, None)

    def _recover_live_workers(self) -> dict:
        result = self.worker_recovery.reconcile(
            self.state,
            active=self._active,
            providers=self._active_provider,
        )
        for task_id in result.get("cancel_task_ids", []):
            future = self._active.get(task_id)
            if future is not None and not future.done():
                future.cancel()
        for row in result.get("recovered", []):
            task = self.state.tasks.get(str(row.get("task_id") or ""))
            if task is None:
                continue
            self._recovery_event(
                "worker_watchdog_recovery",
                task,
                detail=f"{row.get('action')}: {row.get('reason')}",
                provider=self._active_provider.get(task.id) or task.provider_name,
            )
            self._activity_event(
                "worker_recovered",
                task,
                provider=self._active_provider.get(task.id) or task.provider_name,
                detail=f"{row.get('action')}: {row.get('reason')}",
            )
        return result

    def _is_complete(self) -> bool:
        assessment = self.completion_engine.assess(self.state)
        self.state.metadata["completion_assessment"] = {"complete": assessment.complete, "confidence": assessment.confidence, "blockers": assessment.blockers, "reasons": assessment.reasons, "outcome": assessment.outcome.value, "level": assessment.level, "evidence": assessment.evidence}
        return assessment.complete

    def _maybe_schedule_verification(self, task: Task, low_quality: bool) -> None:
        # Internal control and verification tasks already have dedicated deterministic
        # gates. Spawning verification-of-verification was a major source of churn.
        if not is_productive(task, self.state):
            return
        if task.metadata.get("verification_task") or task.metadata.get("verification_scheduled"):
            return
        percent=self.state.verification_percent
        available_providers = len(getattr(self.router, "providers", []) or []) or 1
        consensus_plan = self.consensus_verification.plan(self.state, task, available_providers=available_providers)
        if percent < 60 and consensus_plan.independent_checks <= 0 and not consensus_plan.adversarial_check:
            return
        if self.backpressure.saturated(self.state) and not task.metadata.get("external_action") and not task.metadata.get("irreversible"):
            return
        plan = self.layered_verification.plan(self.state, task)
        candidates = self.layered_verification.build_tasks(self.state, task)
        # Preserve the original slider contract, strengthened by DEV40 risk-adaptive consensus.
        independent = [x for x in candidates if not x.metadata.get("adversarial")]
        adversarial = [x for x in candidates if x.metadata.get("adversarial")]
        required_independent = max(2 if percent >= 85 else 1, int(consensus_plan.independent_checks or 0))
        while len(independent) < required_independent:
            idx = len(independent) + 1
            independent.append(Task(title=f"Verify {idx}: {task.title}", description="Independently verify the completed result. Use independent evidence where possible and identify unsupported claims, source dependence and conflicts. " + self.layered_verification.verifier_instruction(), parent_id=task.parent_id, depth=task.depth, priority=min(100, task.priority + 8 + idx), dependencies=[task.id], estimated_seconds=max(0.2, task.estimated_seconds), required_capabilities=list(task.required_capabilities), acceptance_criteria=["Independent verification completed", "Unsupported claims identified", "CEO_VERIFY marker returned"], metadata={"verification_task": True, "verification_index":idx, "verifies": task.id, "verification_depth":.7, "preferred_provider": None, "avoid_providers": [task.provider_name] if task.provider_name else []}))
        if (percent >= 95 or consensus_plan.adversarial_check) and not adversarial:
            adversarial = [self.adversarial_verifier.build_task(task)]
        candidates = independent + adversarial
        routing = task.metadata.get("provider_routing") or {}
        challenger = routing.get("challenger")
        if challenger and independent:
            independent[0].metadata["preferred_provider"] = challenger
            independent[0].metadata["provider_comparison"] = True
            independent[0].description += f" Compare the original output against an independent result from provider '{challenger}'."
        created=[]
        for verify in candidates:
            self.state.tasks[verify.id]=verify;created.append(verify.id)
            if task.parent_id and task.parent_id in self.state.tasks:self.state.tasks[task.parent_id].children.append(verify.id)
            else:self.state.root_task_ids.append(verify.id)
        task.metadata["verification_plan"]={"independent_checks":max(plan.independent_checks, required_independent),"adversarial":bool(plan.adversarial or consensus_plan.adversarial_check),"source_independence_required":bool(plan.source_independence_required or consensus_plan.require_distinct_provider),"reason":plan.reason,"multi_ai_consensus":consensus_plan.to_dict()}
        task.metadata["verification_scheduled"]=created

    def _maybe_schedule_conflict_review(self, task: Task) -> None:
        if not is_productive(task, self.state):
            return
        # Scalable conflict index: compare only semantically-near title buckets rather than
        # scanning every completed task (which becomes O(n²) at 100k tasks).
        key = " ".join(task.title.lower().split())[:120]
        index = self.state.metadata.setdefault("conflict_index", {})
        candidate_ids = list(index.get(key, []))[-20:]
        for oid in candidate_ids:
            other = self.state.tasks.get(oid)
            if not other or other.status != TaskStatus.COMPLETE:
                continue
            if self.conflicts.conflicts(task, other):
                pair_key = "|".join(sorted((task.id, other.id)))
                seen = self.state.metadata.setdefault("conflict_reviews", {})
                if pair_key in seen:
                    continue
                review = Task(
                    title=f"Resolve conflict: {task.title}",
                    description=f"Resolve conflicting outputs from tasks {task.id} and {other.id}. Prefer primary evidence and document uncertainty.",
                    priority=95, dependencies=[task.id, other.id], estimated_seconds=max(task.estimated_seconds, other.estimated_seconds),
                    acceptance_criteria=["Contradiction explicitly resolved or preserved as uncertainty"],
                    metadata={"conflict_review": True, "conflict_pair": [task.id, other.id], "conflict_type": self.conflicts.classify(task, other)},
                )
                self.state.tasks[review.id] = review; self.state.root_task_ids.append(review.id); seen[pair_key] = review.id
        bucket = index.setdefault(key, [])
        bucket.append(task.id)
        if len(bucket) > 50:
            del bucket[:-50]

    def _observed_task_seconds(self) -> float:
        samples = [t.actual_seconds for t in self.state.leaf_tasks if t.actual_seconds and t.status in {TaskStatus.COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.PARTIAL_COMPLETE}]
        if samples:
            return float(statistics.median(samples))
        estimates = [t.estimated_seconds for t in self.state.leaf_tasks if t.estimated_seconds > 0]
        return float(statistics.median(estimates)) if estimates else 30.0

    def _record_concurrency_observation(self) -> None:
        now=time.perf_counter();elapsed=max(.001,now-self._obs_ts);complete=len(self.state.completed_leaf_tasks);delta=max(0,complete-self._obs_complete);throughput=delta/elapsed
        pstats=self.state.metadata.get("provider_stats",{});runs=sum(int(x.get("runs",0)) for x in pstats.values());fails=sum(int(x.get("failures",0)) for x in pstats.values());failure_rate=fails/max(1,runs)
        latencies=[float(x.get("average_seconds",0)) for x in pstats.values() if x.get("average_seconds") is not None];latency=sum(latencies)/len(latencies) if latencies else 0.0
        workers=max(1,len(self._active))
        self.concurrency_optimizer.record(self.state,workers,throughput,failure_rate,latency)
        snap=self.governor.snapshot()
        self.capacity_profiler.record(self.state,self.state.power_percent,workers=workers,throughput=throughput,ram_percent=float(snap.get("ram_percent",0)),cpu_percent=float(snap.get("cpu_percent",0)),failures=failure_rate)
        self._obs_ts=now;self._obs_complete=complete

    def _recovery_event(self, kind: str, task: Task, *, detail: str = "", provider: str | None = None) -> None:
        row = {
            "ts": utcnow().isoformat(),
            "kind": kind,
            "task_id": task.id,
            "title": task.title,
            "status": task.status.value,
            "attempt": int(task.attempts),
            "provider": provider or task.provider_name,
            "detail": detail[:1000],
        }
        rows = self.state.metadata.setdefault("recovery_events", [])
        rows.append(row)
        del rows[:-200]

    def _activity_event(self, kind: str, task: Task | None = None, *, provider: str | None = None, detail: str = "") -> None:
        row = {
            "ts": utcnow().isoformat(),
            "kind": kind,
            "task_id": task.id if task else None,
            "title": task.title if task else self.state.goal,
            "provider": provider or (task.provider_name if task else None),
            "stage": task.metadata.get("provider_stage") if task else None,
            "status": task.status.value if task else None,
            "detail": detail,
        }
        rows = self.state.metadata.setdefault("activity_timeline", [])
        rows.append(row)
        del rows[:-200]

    def _is_goal_continuity_task(self, task: Task) -> bool:
        return is_goal_audit_lineage(self.state, task)

    def operational_status(self) -> str:
        """Human-readable high-level state for the operator UI.

        The status is deliberately derived from durable project/task state rather
        than from transient frontend timers so it remains meaningful after restart.
        """
        if self.state.completed_at is not None:
            return "COMPLETADO"
        if self.state.paused:
            return "PAUSADO"

        leaves = list(self.state.leaf_tasks)
        open_decisions = []
        for decision in self.state.decisions.values():
            if decision.status.value != "open":
                continue
            source_task = task_for_decision(self.state, decision)
            stale_internal = (
                self.state.autonomy_enabled
                and source_task is not None
                and is_internal_continuity_task(self.state, source_task)
                and not protected_human_gate(source_task, decision.metadata)
            )
            if not stale_internal:
                open_decisions.append(decision)
        human_review = any(
            t.status == TaskStatus.NEEDS_REVIEW
            and (not is_internal_continuity_task(self.state, t) or protected_human_gate(t))
            for t in leaves
        )
        if open_decisions or human_review:
            return "NECESITA DECISIÓN"

        # Active execution and genuinely executable queued work are authoritative.
        # A stale watchdog/operator marker must never override them.
        active = [self.state.tasks.get(tid) for tid in self._active]
        active = [t for t in active if t is not None]
        if active:
            if any(t.metadata.get("verification_task") for t in active):
                return "VERIFICANDO"
            if any(t.metadata.get("autonomy_recovery") or t.metadata.get("controller_action") == "correct" for t in active):
                return "CORRIGIENDO"
            return "TRABAJANDO"

        if any(t.status in {TaskStatus.READY, TaskStatus.RETRY} for t in leaves):
            return "PLANIFICANDO"

        truth_state = str(self.state.metadata.get("operator_productivity_state") or "").upper()
        if truth_state in {"ATASCADO", "BLOQUEADO"}:
            return "BLOQUEADO"
        if truth_state == "REPLANIFICANDO":
            return "CORRIGIENDO"

        # WAITING is soft pending work, not proof of a hard global block.
        if any(t.status == TaskStatus.WAITING for t in leaves):
            return "PLANIFICANDO"

        if self.state.metadata.get("autonomy_stalled") or any(t.status == TaskStatus.BLOCKED for t in leaves):
            return "BLOQUEADO"

        watchdog = self.state.metadata.get("autonomous_loop", {}).get("watchdog", {})
        if watchdog.get("status") in {"replanned", "recovery_created", "watching", "goal_audit_created", "goal_audit_review_auto_recovered"}:
            return "PLANIFICANDO"
        return "EN ESPERA"

    def _activity_snapshot(self) -> dict:
        active=[]
        for task_id, provider in self._active_provider.items():
            task=self.state.tasks.get(task_id)
            if not task: continue
            active.append({
                "task_id":task.id,"title":task.title,"provider":provider,
                "stage":task.metadata.get("provider_stage","running"),
                "attempt":task.attempts,"turn":task.conversation_turns,
            })
        ready=sorted(
            [t for t in self.state.leaf_tasks if t.status == TaskStatus.READY],
            key=lambda t: (-t.priority, t.created_at),
        )[:8]
        recent=list(self.state.metadata.get("result_order", []))[-8:]
        problems=[t for t in self.state.leaf_tasks if t.status in {TaskStatus.FAILED,TaskStatus.NEEDS_REVIEW,TaskStatus.BLOCKED}]
        reason = "Ejecutando trabajo priorizado por valor, dependencias y recursos." if active else (
            "Hay incidencias que requieren recuperación o decisión." if problems else
            "Esperando una tarea ejecutable o reevaluando el plan."
        )
        return {
            "status": self.operational_status(),
            "active":active,
            "why":reason,
            "next":[{"task_id":t.id,"title":t.title,"priority":t.priority,"why":"prioridad/dependencias"} for t in ready],
            "recent":[{"task_id":tid,"title":self.state.tasks[tid].title,"status":self.state.tasks[tid].status.value} for tid in reversed(recent) if tid in self.state.tasks],
            "timeline":list(self.state.metadata.get("activity_timeline", []))[-20:][::-1],
            "needs_attention":[{"task_id":t.id,"title":t.title,"status":t.status.value,"error":t.metadata.get("last_provider_error")} for t in problems[:20]],
            "stalled":self.state.metadata.get("autonomy_stalled"),
            "watchdog":self.state.metadata.get("autonomous_loop",{}).get("watchdog",{}),
        }

    def metrics(self) -> dict:
        leaves = self.state.leaf_tasks
        complete = [t for t in leaves if t.status in {TaskStatus.COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.PARTIAL_COMPLETE}]
        remaining = [t for t in leaves if t.status not in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.SUPERSEDED}]
        avg = self._observed_task_seconds()
        concurrency = self.governor.target_concurrency(self.state.power_percent)

        # Estimated remaining compute seconds calibrated by completed-task median.
        remaining_work = 0.0
        for task in remaining:
            if task.actual_seconds:
                estimate = task.actual_seconds
            elif complete:
                # Blend planner estimate and observed task duration as evidence accumulates.
                estimate = (task.estimated_seconds * 0.35) + (avg * 0.65)
            else:
                estimate = task.estimated_seconds
            remaining_work += max(0.05, estimate)

        efficiency = 0.82 if concurrency > 1 else 1.0
        critical = self.graph.remaining_critical_path(self.state)
        # ETA cannot be shorter than the sequential dependency chain, regardless of worker count.
        parallel_eta = remaining_work / max(1.0, concurrency * efficiency)
        eta_seconds = round(max(parallel_eta, float(critical["seconds"])), 1)
        scenarios = {}
        for power in (20, 40, 60, 80, 100):
            workers = self.governor.target_concurrency(power)
            scenario_eff = 0.82 if workers > 1 else 1.0
            p_eta = remaining_work / max(1.0, workers * scenario_eff)
            scenarios[str(power)] = {
                "workers": workers,
                "eta_seconds": round(max(p_eta, float(critical["seconds"])), 1),
            }
        return {
            "operational_status": self.operational_status(),
            "progress": self.state.progress,
            "active_workers": len(self._active),
            "target_workers": concurrency,
            "completed": len(complete),
            "remaining": len(remaining),
            "failed": sum(t.status == TaskStatus.FAILED for t in leaves),
            "needs_review": sum(t.status == TaskStatus.NEEDS_REVIEW for t in leaves),
            "eta_seconds": eta_seconds,
            "power_scenarios": scenarios,
            "observed_task_seconds": round(avg, 2),
            "resources": self.governor.snapshot(),
            "human_interventions_avoided": self.state.human_interventions_avoided,
            "human_interventions_required": self.state.human_interventions_required,
            "provider_stats": self.state.metadata.get("provider_stats", {}),
            "critical_path": critical,
            "completion": self.state.metadata.get("completion_assessment", {}),
            "average_quality": round(sum(t.quality_score or 0 for t in complete) / max(1, len(complete)), 3),
            "cost_spent": self.cost_engine.spent(self.state),
            "cost_projected": self.cost_engine.projected_cost(self.state),
            "budget": self.cost_engine.snapshot(self.state),
            "activity": self._activity_snapshot(),
            "notification_summary": self.notifications.summary(self.state),
            "quality_engineering": self.quality_engineering.project_snapshot(self.state),
            "integrity_engineering": self.integrity_engineering.snapshot(self.state),
            "cognitive_evolution": {
                "dead_end": self.state.metadata.get("cognitive_dead_end", {}),
                "calibration_contexts": len(self.state.metadata.get("confidence_calibration_v2", {})),
                "strategy_observations": len(self.state.metadata.get("cognitive_strategy_lab_v2", {})),
                "self_improvement_candidates": len(self.state.metadata.get("self_improvement_pipeline_v1", {})),
            },
            "resource_limits": self.governor.limits(self.state.power_percent),
            "graph_audit": self.graph.audit(self.state),
            "marginal_yield": round(self.completion_engine.yield_tracker.score(self.state), 4),
            "knowledge_saturated": self.completion_engine.yield_tracker.saturated(self.state),
            "workload_pools": self.workload_pools.counts(self.state),
            "backpressure": {"saturated": self.backpressure.saturated(self.state), **self.backpressure.limits(self.state)},
            "concurrency_saturation_point": self.concurrency_optimizer.saturation_point(self.state),
            "claims": {"total": len(self.state.metadata.get("claims", {})), "unresolved": len(self.integrator.claims.unresolved(self.state))},
            "sources": {"total": len(self.state.metadata.get("sources", {}))},
            "eta_v2": self.state.metadata.get("eta_v2", {}) or {"current": asdict(self.eta_engine.estimate(self.state, simulations=60))},
            "knowledge_status": asdict(self.knowledge_engine.rebuild_indexes(self.state)),
            "director_tree": self.state.metadata.get("director_tree", {}),
            "hybrid_execution_plan": self.state.metadata.get("hybrid_execution_plan", {}),
            "resource_plan": self.state.metadata.get("resource_plan", {}),
            "production_intelligence": {
                "health": self.production_intelligence.mission_control.health(self.state),
                "recommended_strategy": self.state.metadata.get("probabilistic_plan", {}).get("recommended"),
                "evidence_records": len(self.state.metadata.get("evidence_ledger_v2", [])),
                "failure_signatures": len(self.state.metadata.get("failure_memory_v1", {})),
                "learned_outcomes": len(self.state.metadata.get("outcome_learning_v1", {})),
            },
        }
