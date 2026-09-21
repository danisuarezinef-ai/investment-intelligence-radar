from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from ceo_core.autonomous_mission_soak_v1 import AutonomousMissionSoakV1
from ceo_core.autonomous_replan_v2 import AutonomousReplanV2
from ceo_core.autonomy_readiness_v1 import evaluate_autonomy_readiness_v1
from ceo_core.contracts import WorkerKind, WorkerProvider, WorkerRequest, WorkerResult
from ceo_core.deliverable_evidence_engine_v1 import DeliverableEvidenceEngineV1
from ceo_core.mission_continuity_v2 import MissionContinuityV2
from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.multi_worker_concurrency_v1 import MultiWorkerConcurrencyV1
from ceo_core.productive_task_contract_v1 import ProductiveTaskContractV1
from ceo_core.provider_resilience_v2 import ProviderResilienceV2
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.self_development_sandbox_v3 import SelfDevelopmentSandboxV3
from ceo_core.store import JsonCheckpointStore
from ceo_core.worker_lifecycle_v2 import WorkerLifecycleV2


CANDIDATE = "1.4.88-rc1-autonomous-productive-execution"


class ProductiveProvider(WorkerProvider):
    name = "dev211-productive-provider"
    kind = WorkerKind.MOCK
    capabilities = frozenset({"general", "reasoning", "verification"})

    def __init__(self, *, delay: float = 0.015) -> None:
        self.delay = delay
        self.running = 0
        self.max_running = 0
        self.calls: dict[str, int] = {}

    def supports(self, task: Task) -> bool:
        return True

    async def execute(self, request: WorkerRequest) -> WorkerResult:
        tid = request.work_unit.id
        self.calls[tid] = self.calls.get(tid, 0) + 1
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            await asyncio.sleep(self.delay)
            return WorkerResult(
                provider=self.name,
                kind=self.kind,
                success=True,
                text=f"Verified productive deliverable for {request.work_unit.title}",
                conversation_id=f"dev211-{tid}-{self.calls[tid]}",
                metadata={"acceptance_evidence": True},
            )
        finally:
            self.running -= 1


def add(state: ProjectState, task: Task) -> Task:
    state.tasks[task.id] = task
    state.root_task_ids.append(task.id)
    return task


def productive_contract_check() -> bool:
    state = ProjectState(goal="contract")
    dep = add(state, Task(title="dependency", status=TaskStatus.COMPLETE, result="done", metadata={"acceptance_evidence": True}))
    task = add(state, Task(title="deliverable", status=TaskStatus.COMPLETE, result="result", dependencies=[dep.id], metadata={"acceptance_evidence": True}))
    receipt = ProductiveTaskContractV1().evaluate(state, task)
    bad = Task(title="bad", status=TaskStatus.COMPLETE, result="result")
    state.tasks[bad.id] = bad
    bad_receipt = ProductiveTaskContractV1().evaluate(state, bad)
    return receipt.definition_of_done_met and not bad_receipt.definition_of_done_met and len(receipt.receipt_sha256) == 64


def lifecycle_check() -> bool:
    state = ProjectState(goal="lifecycle")
    task = add(state, Task(title="lease", status=TaskStatus.READY))
    life = WorkerLifecycleV2()
    lease = life.claim(state, task, "w1", ttl_seconds=30)
    collision = False
    try:
        life.claim(state, task, "w2", ttl_seconds=30)
    except RuntimeError:
        collision = True
    hb = life.heartbeat(state, task.id, ttl_seconds=30)
    released = life.release(state, task, reason="test")
    return collision and hb and released and task.worker_id is None and bool(lease.lease_id)


def multi_worker_check() -> bool:
    state = ProjectState(goal="multi")
    tasks = [add(state, Task(title=f"t{i}", status=TaskStatus.READY, priority=100-i)) for i in range(8)]
    alloc = MultiWorkerConcurrencyV1().allocate(state, tasks, worker_count=4)
    return len(alloc) == 4 and len({x.task_id for x in alloc}) == 4 and sum(t.status == TaskStatus.RUNNING for t in tasks) == 4


def resilience_check() -> bool:
    r = ProviderResilienceV2()
    quota = r.classify("HTTP 429 RESOURCE_EXHAUSTED quota", 2)
    auth = r.classify("HTTP 401 unauthorized", 1)
    billing = r.classify("billing required", 1)
    models = r.model_candidates(["gemini-3.6-flash", "custom"], failed_model="gemini-3.8-flash")
    return (
        quota.retry and quota.rotate_model and quota.rotate_provider and not quota.spending_allowed
        and auth.requires_human and not auth.retry
        and billing.requires_human and not billing.spending_allowed
        and "gemini-3.8-flash" not in models and len(models) == len(set(models))
    )


def evidence_check() -> bool:
    with tempfile.TemporaryDirectory(prefix="dev206-") as td:
        state = ProjectState(goal="evidence")
        task = add(state, Task(title="artifact", status=TaskStatus.COMPLETE, result="result"))
        p = Path(td) / "artifact.txt"; p.write_text("hello", encoding="utf-8")
        engine = DeliverableEvidenceEngineV1()
        file_rec = engine.record_file(state, task, p, root=td)
        text_rec = engine.record_text(state, task, "result")
        blocked = False
        try:
            engine.record_file(state, task, Path(td).parent / "outside.txt", root=td)
        except (FileNotFoundError, PermissionError):
            blocked = True
        return blocked and file_rec.size_bytes == 5 and len(file_rec.sha256) == 64 and len(text_rec.sha256) == 64 and bool(task.metadata.get("acceptance_evidence"))


def sandbox_check() -> bool:
    with tempfile.TemporaryDirectory(prefix="dev207-src-") as td:
        root = Path(td)
        (root / "ceo_core").mkdir(); (root / "ceo_core" / "safe.py").write_text("VALUE=1\n", encoding="utf-8")
        (root / "ceo_core" / "update_trust.json").write_text("{}\n", encoding="utf-8")
        def safe_patch(challenger: Path) -> None:
            (challenger / "ceo_core" / "safe.py").write_text("VALUE=2\n", encoding="utf-8")
        good = SelfDevelopmentSandboxV3().evaluate(root, patch=safe_patch, test_command=[sys.executable, "-m", "py_compile", "ceo_core/safe.py"])
        def unsafe_patch(challenger: Path) -> None:
            (challenger / "ceo_core" / "update_trust.json").write_text('{"changed":true}\n', encoding="utf-8")
        bad = SelfDevelopmentSandboxV3().evaluate(root, patch=unsafe_patch)
        return good.passed and good.tests_passed and not good.stable_mutated and not bad.passed and bool(bad.forbidden_paths)


def replan_check() -> bool:
    state = ProjectState(goal="replan")
    task = add(state, Task(title="failed", status=TaskStatus.FAILED, dependencies=[]))
    replanner = AutonomousReplanV2()
    first = replanner.replan_failed(state, task, ["alternative A", "alternative B"])
    if first.action != "replanned" or len(first.replacement_task_ids) != 2 or task.status != TaskStatus.SUPERSEDED:
        return False
    child = state.tasks[first.replacement_task_ids[0]]
    child.metadata["replan_generation_v2"] = 3
    bounded = replanner.replan_failed(state, child, ["another"])
    return bounded.action == "bounded_stall" and bounded.bounded


def continuity_check() -> bool:
    with tempfile.TemporaryDirectory(prefix="dev209-") as td:
        state = ProjectState(goal="continuity")
        task = add(state, Task(title="done", status=TaskStatus.COMPLETE, result="done", metadata={"acceptance_evidence": True}))
        store = JsonCheckpointStore(Path(td) / "state.json")
        continuity = MissionContinuityV2()
        receipt = continuity.checkpoint(store, state)
        resumed = continuity.resume(store, receipt)
        if resumed.id != state.id or resumed.tasks[task.id].status != TaskStatus.COMPLETE:
            return False
        Path(receipt.checkpoint_path).write_text("{}", encoding="utf-8")
        try:
            continuity.resume(store, receipt)
            return False
        except RuntimeError:
            return True


async def productive_mission_e2e() -> dict:
    with tempfile.TemporaryDirectory(prefix="dev211-e2e-") as td:
        state = ProjectState(
            goal="Complete eight independent productive deliverables",
            project_name="DEV211 productive E2E",
            verification_percent=0,
            power_percent=100,
            metadata={
                "strict_completion_audit": False,
                "require_goal_audit": False,
                "completion_confidence_threshold": 0.0,
                "strategic_tick_interval": 10000,
                "concurrency_observations": [{"workers": 4, "throughput": 4.0, "failures": 0}],
            },
        )
        tasks: list[Task] = []
        for i in range(8):
            task = Task(
                title=f"Productive deliverable {i+1}",
                status=TaskStatus.READY,
                priority=100-i,
                estimated_seconds=0.02,
                required_capabilities=["general"],
                metadata={"quality_gate_threshold": 0.0},
            )
            add(state, task); tasks.append(task)
        store = JsonCheckpointStore(Path(td) / "state.json")
        provider = ProductiveProvider(delay=0.03)
        scheduler = ContinuousScheduler(state, provider, store)
        scheduler.start()
        deadline = asyncio.get_running_loop().time() + 8.0
        while asyncio.get_running_loop().time() < deadline:
            if all(t.status == TaskStatus.COMPLETE for t in tasks):
                break
            await asyncio.sleep(0.05)
        await scheduler.stop()
        first_complete = sum(t.status == TaskStatus.COMPLETE for t in tasks)
        loaded = store.load()
        if loaded is None:
            return {"ok": False, "reason": "checkpoint_missing"}
        evidence = loaded.metadata.get("deliverable_evidence_v1", [])
        leases = loaded.metadata.get("worker_leases_v2", {})
        leaked = [x for x in leases.values() if not x.get("released")]
        return {
            "ok": first_complete == 8 and len(evidence) >= 8 and not leaked and provider.max_running >= 2,
            "completed": first_complete,
            "evidence_records": len(evidence),
            "max_parallel_workers": provider.max_running,
            "leaked_leases": len(leaked),
            "checkpoint_exists": Path(td, "state.json").is_file(),
        }


def main() -> int:
    checks: dict[str, object] = {}
    checks["DEV202_productive_task_contract_v1"] = productive_contract_check()
    checks["DEV203_worker_lifecycle_v2"] = lifecycle_check()
    checks["DEV204_multi_worker_concurrency_v1"] = multi_worker_check()
    checks["DEV205_provider_resilience_v2"] = resilience_check()
    checks["DEV206_deliverable_evidence_engine_v1"] = evidence_check()
    checks["DEV207_self_development_sandbox_v3"] = sandbox_check()
    checks["DEV208_autonomous_replan_v2"] = replan_check()
    checks["DEV209_mission_continuity_v2"] = continuity_check()
    soak = AutonomousMissionSoakV1().run(rounds=5000, seed=211)
    checks["DEV210_autonomous_mission_soak_v1"] = soak.violations == 0 and soak.leaked_leases == 0 and soak.duplicate_allocations == 0
    e2e = asyncio.run(productive_mission_e2e())
    checks["DEV211_productive_mission_e2e"] = bool(e2e.get("ok"))

    readiness = evaluate_autonomy_readiness_v1(
        productive_contract=bool(checks["DEV202_productive_task_contract_v1"]),
        worker_lifecycle=bool(checks["DEV203_worker_lifecycle_v2"]),
        multi_worker=bool(checks["DEV204_multi_worker_concurrency_v1"]),
        provider_resilience=bool(checks["DEV205_provider_resilience_v2"]),
        evidence_engine=bool(checks["DEV206_deliverable_evidence_engine_v1"]),
        self_dev_sandbox=bool(checks["DEV207_self_development_sandbox_v3"]),
        autonomous_replan=bool(checks["DEV208_autonomous_replan_v2"]),
        mission_continuity=bool(checks["DEV209_mission_continuity_v2"]),
        mission_soak=bool(checks["DEV210_autonomous_mission_soak_v1"]),
        clean_package=True,
    )
    checks["DEV211_autonomy_readiness_v1"] = readiness.local_autonomy_candidate_ready
    ok = all(bool(v) for v in checks.values())
    print(json.dumps({"ok": ok, "candidate": CANDIDATE, "checks": checks, "soak": soak.to_dict(), "e2e": e2e, "readiness": readiness.to_dict()}, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
