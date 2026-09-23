from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(os.environ["CEO_W9_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))

from ceo_core.completion import CompletionEngine
from ceo_core.decomposer import TaskDecomposer
from ceo_core.goal_completion_gate import GoalCompletionGate
from ceo_core.goal_engine import GoalEngine
from ceo_core.goal_lock_local_provider_v1 import GoalLockLocalProviderV1
from ceo_core.graph import TaskGraph
from ceo_core.local_finite_file_provider_v1 import (
    LocalFiniteFileProviderV1,
    configure_local_finite_file_state,
    parse_local_finite_file_goal,
)
from ceo_core.models import ProjectState, TaskStatus
from ceo_core.progress_tracker import StableProgressTracker
from ceo_core.recovery_budget_guard_v1 import RecoveryBudgetGuardV1
from ceo_core.routing import MultiProviderRouter
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.store import CheckpointStore


GOAL = "Crea CEO_LOCAL_W9.txt. Debe contener exactamente: CEO_LOCAL_W9_OK"
EXPECTED = "CEO_LOCAL_W9_OK"


def assert_recovery_guard_preserves_verification() -> None:
    import inspect
    from ceo_core.task_roles_v2 import is_verification

    print("W9_RECOVERY_GUARD_PATCHED_SOURCE_BEGIN")
    print(inspect.getsource(RecoveryBudgetGuardV1))
    print("W9_RECOVERY_GUARD_PATCHED_SOURCE_END")

    state = ProjectState(goal="W9 guard semantics")
    control_a = TaskStatus  # keep import usage explicit for static analyzers
    del control_a

    from ceo_core.models import Task

    c1 = Task(
        id="control-a",
        title="Goal continuity audit #A",
        status=TaskStatus.READY,
        priority=100,
        metadata={"task_role": "control", "goal_continuity_audit": True},
    )
    c2 = Task(
        id="control-b",
        title="Goal continuity audit #B",
        status=TaskStatus.READY,
        priority=90,
        metadata={"task_role": "control", "goal_continuity_audit": True},
    )
    verification = Task(
        id="verify-real",
        title="Final audit local verification",
        status=TaskStatus.READY,
        priority=10,
        metadata={
            "task_role": "verification",
            "verification_task": True,
            "verifies": "productive",
        },
    )
    for task in (c1, c2, verification):
        state.tasks[task.id] = task
        state.root_task_ids.append(task.id)

    print(
        "W9_RECOVERY_GUARD_ROLE_CHECK",
        json.dumps(
            {
                "verification_is_verification": is_verification(verification, state),
                "verification_metadata": verification.metadata,
            },
            sort_keys=True,
        ),
    )
    report = RecoveryBudgetGuardV1(max_active_internal=1).apply(state)
    assert verification.status == TaskStatus.READY, (
        verification.status,
        verification.metadata,
        report.to_dict(),
    )
    retired_controls = [
        t for t in (c1, c2)
        if t.status == TaskStatus.SUPERSEDED
        and t.metadata.get("superseded_reason") == "recovery_budget_guard_duplicate_internal_control"
    ]
    assert len(retired_controls) == 1, (
        [(t.id, t.status.value, t.metadata) for t in (c1, c2)],
        report.to_dict(),
    )


def package_hash_ok(relative: str) -> tuple[bool, str, str]:
    contract = json.loads((ROOT / "CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8"))
    expected = str((contract.get("file_hashes") or {}).get(relative) or "")
    actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    return bool(expected and expected == actual), expected, actual


def prepare_state(workspace: pathlib.Path) -> ProjectState:
    spec = parse_local_finite_file_goal(GOAL)
    assert spec is not None, "W9 parser rejected bounded local goal"
    assert spec["path"] == "CEO_LOCAL_W9.txt", spec
    assert spec["content"] == EXPECTED, spec

    contract = GoalEngine().lock(
        GOAL,
        success_definition=(
            "CEO_LOCAL_W9.txt exists in the managed workspace, contains exactly "
            "CEO_LOCAL_W9_OK and is independently verified."
        ),
        completion_criteria=[
            "Requested local file exists inside the managed workspace.",
            "Requested exact content matches after UTF-8 readback.",
            "Independent local verification passes.",
        ],
        deliverables=["CEO_LOCAL_W9.txt"],
        constraints=[
            "No network.",
            "No API.",
            "No shell.",
            "No spending.",
        ],
        forbidden_actions=[
            "network",
            "api",
            "shell",
            "spending",
        ],
        budget_limit=0.0,
    )

    state = TaskDecomposer().plan(GOAL)
    GoalEngine().apply(state, contract)
    state.project_name = "W9 local finite task"
    state.metadata["workspace_v2"] = {
        "root": str(workspace.resolve()),
        "project_id": state.id,
        "managed": True,
        "available": True,
        "schema_version": 1,
    }
    state.metadata["real_work_intake_v1"] = {
        "mode": "local_finite_file",
        "automatic_spending": False,
        "git_network_allowed": False,
        "destructive_actions_require_gate": True,
    }
    state.metadata["strict_goal_completion_gate"] = True
    state.metadata["require_goal_audit"] = True
    state.metadata["goal_audit_passed"] = False
    state.metadata["goal_continuity_generation"] = 0
    state.metadata["production_verified"] = False
    state.metadata["provider_mode"] = "local-finite-file"
    state.metadata["requires_field_endurance_certification"] = False
    configure_local_finite_file_state(state, spec, workspace)
    return state


class JsonCheckpointStore(CheckpointStore):
    """Minimal durable store for exercising the real scheduler contract in W9."""

    def __init__(self, path: pathlib.Path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, state: ProjectState) -> None:
        payload = state.model_dump_json()
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self.path)

    def load(self) -> ProjectState | None:
        if not self.path.is_file():
            return None
        return ProjectState.model_validate_json(self.path.read_text(encoding="utf-8"))


def make_store(path: pathlib.Path):
    return JsonCheckpointStore(path)


async def run_scheduler() -> dict:
    for key in (
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "PERPLEXITY_API_KEY",
        "XAI_API_KEY",
    ):
        os.environ.pop(key, None)
    os.environ["CEO_ALLOW_OPTIONAL_API"] = "0"

    with tempfile.TemporaryDirectory(prefix="ceo-w9-workspace-") as ws_raw, tempfile.TemporaryDirectory(
        prefix="ceo-w9-state-"
    ) as state_raw:
        workspace = pathlib.Path(ws_raw).resolve()
        state = prepare_state(workspace)

        providers = [GoalLockLocalProviderV1(), LocalFiniteFileProviderV1()]
        router = MultiProviderRouter(providers)
        store = make_store(pathlib.Path(state_raw) / "state.json")
        store.save(state)

        scheduler = ContinuousScheduler(
            state,
            None,
            store,
            graph=TaskGraph(),
            router=router,
        )
        scheduler.start()

        deadline = time.monotonic() + 25.0
        while time.monotonic() < deadline:
            if state.completed_at is not None:
                break
            bad = [
                t
                for t in state.leaf_tasks
                if t.status in {TaskStatus.FAILED, TaskStatus.NEEDS_REVIEW}
            ]
            if bad:
                break
            await asyncio.sleep(0.10)

        if state.completed_at is None:
            await scheduler.stop()
            snapshot = [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status.value,
                    "provider": t.provider_name,
                    "result": (t.result or "")[:300],
                    "metadata": {
                        k: v
                        for k, v in (t.metadata or {}).items()
                        if k
                        in {
                            "task_role",
                            "preferred_kind",
                            "local_fallback_kind",
                            "local_finite_file_mode",
                            "blocked_safe_reason",
                            "last_provider_error",
                            "provider_stage",
                            "superseded_reason",
                            "verification_task",
                            "verifies",
                            "verification_scheduled",
                            "task_role",
                        }
                    },
                    "dependencies": list(t.dependencies or []),
                    "parent_id": t.parent_id,
                }
                for t in state.leaf_tasks
            ]
            raise AssertionError(
                "W9 scheduler did not close finite local objective: "
                + json.dumps(
                    {
                        "tasks": snapshot,
                        "completion": state.metadata.get("completion_assessment"),
                        "goal_audit_passed": state.metadata.get("goal_audit_passed"),
                        "operator": state.metadata.get("operator_productivity_state"),
                        "provider_wait": state.metadata.get("provider_wait_v1"),
                        "completion_phase": state.metadata.get("completion_phase_v1"),
                        "deterministic_certificate": state.metadata.get("deterministic_completion_certificate_v1"),
                        "last_goal_audit_rejection": state.metadata.get("last_goal_audit_rejection"),
                        "continuity_generation": state.metadata.get("goal_continuity_generation"),
                    },
                    ensure_ascii=False,
                    default=str,
                )
            )

        await scheduler.stop()

        target = workspace / "CEO_LOCAL_W9.txt"
        assert target.is_file(), "W9 target file missing"
        actual = target.read_text(encoding="utf-8")
        assert actual == EXPECTED, repr(actual)
        target_sha = hashlib.sha256(target.read_bytes()).hexdigest()

        leaves = state.leaf_tasks
        execution = next(t for t in leaves if t.title.lower().startswith("execution"))
        verify = next(t for t in leaves if t.title.lower().startswith("final audit"))
        goal_lock = next(t for t in leaves if t.title.lower().startswith("clarify & lock goal"))

        assert goal_lock.provider_name == "ceo-local-goal-lock", goal_lock.provider_name
        assert execution.provider_name == "ceo-local-finite-file", execution.provider_name
        assert verify.provider_name == "ceo-local-finite-file", verify.provider_name
        assert verify.status == TaskStatus.COMPLETE, verify.status
        assert execution.metadata.get("verification_scheduled") == [verify.id], execution.metadata
        assert verify.metadata.get("verifies") == execution.id, verify.metadata
        assert not any(
            ("execution" in str(t.title or "").lower())
            and (
                str(t.title or "").lower().startswith("independent verification")
                or str(t.title or "").lower().startswith("verify ")
            )
            for t in leaves
            if t.id != verify.id
        ), [
            {"title": t.title, "status": t.status.value, "metadata": t.metadata}
            for t in leaves
        ]
        assert goal_lock.metadata.get("task_role") == "internal_control", goal_lock.metadata
        assert not goal_lock.metadata.get("verification_scheduled"), goal_lock.metadata
        assert not any(
            ("clarify & lock goal" in str(t.title or "").lower())
            and (
                t.metadata.get("verification_task")
                or "independent verification" in str(t.title or "").lower()
                or str(t.title or "").lower().startswith("verify ")
            )
            for t in leaves
            if t.id != goal_lock.id
        ), [
            {"title": t.title, "status": t.status.value, "metadata": t.metadata}
            for t in leaves
        ]

        writes = list(execution.metadata.get("workspace_writes_v1") or [])
        assert len(writes) == 2, writes
        assert writes[0]["path"] == "CEO_LOCAL_W9.txt"
        assert writes[1]["path"] == "CEO_LOCAL_W9.txt"
        assert writes[0]["sha256"] != writes[1]["sha256"], writes
        assert writes[1]["sha256"] == target_sha, writes

        assert verify.metadata.get("independently_verified") is True, verify.metadata
        assert verify.provider_name == "ceo-local-finite-file", verify.provider_name
        verification = dict(verify.metadata.get("verification_application") or {})
        assert verification.get("applied") is True, verification
        assert verification.get("verdict") == "pass", verification
        assert verification.get("target_id") == execution.id, verification
        assert float(verification.get("confidence") or 0.0) == 1.0, verification

        evidence = dict(state.metadata.get("deliverable_evidence") or {})
        assert evidence.get("CEO_LOCAL_W9.txt"), evidence
        assert state.metadata.get("goal_audit_passed") is True
        assert CompletionEngine().assess(state).complete is True

        progress = StableProgressTracker().snapshot(state, persist=True)
        assert float(progress.get("display_progress", -1)) == 100.0, progress
        assert int(progress.get("productive_pending", -1)) == 0, progress

        all_providers = {str(t.provider_name or "") for t in leaves}
        assert all(
            not any(token in provider.lower() for token in ("gemini", "openai", "chatgpt", "claude", "perplexity", "grok"))
            for provider in all_providers
        ), all_providers

        cost_spent = float(scheduler.cost_engine.spent(state))
        assert cost_spent == 0.0, {
            "cost_spent": cost_spent,
            "budget": scheduler.cost_engine.snapshot(state),
        }

        payload = state.model_dump_json()
        restored = ProjectState.model_validate_json(payload)
        migration = GoalCompletionGate().migrate_invalid_legacy_pass(restored)
        assert migration.get("changed") is not True, migration
        assert restored.completed_at is not None
        assert restored.metadata.get("goal_audit_passed") is True
        reopened_progress = StableProgressTracker().snapshot(restored, persist=False)
        assert float(reopened_progress.get("display_progress", -1)) == 100.0, reopened_progress

        return {
            "goal": GOAL,
            "completed_at": str(state.completed_at),
            "target_sha256": target_sha,
            "target_size": target.stat().st_size,
            "providers": sorted(all_providers),
            "writes": writes,
            "verification": verification,
            "goal_audit_passed": state.metadata.get("goal_audit_passed"),
            "progress": progress,
            "reopen_migration": migration,
            "reopen_progress": reopened_progress,
            "task_statuses": {
                t.title: t.status.value for t in leaves
            },
            "api_env_present": False,
            "cost_spent": cost_spent,
        }


def main() -> int:
    failures = []

    assert_recovery_guard_preserves_verification()

    # Unsafe/ambiguous variants must not activate the local executor.
    rejected = [
        "Crea ../escape.txt. Debe contener exactamente: NO",
        "Crea a.txt y b.txt. Debe contener exactamente: NO",
        "Investiga y crea report.txt",
        "Crea run.exe. Debe contener exactamente: NO",
        "Crea note.txt",
    ]
    for goal in rejected:
        parsed = parse_local_finite_file_goal(goal)
        if parsed is not None:
            failures.append(f"unsafe_or_ambiguous_goal_accepted:{goal}:{parsed}")

    if failures:
        print("W9_LOCAL_FINITE_PRECHECK_FAIL", json.dumps(failures, ensure_ascii=False))
        return 9

    result = asyncio.run(run_scheduler())
    print("W9_LOCAL_FINITE_E2E", json.dumps(result, ensure_ascii=False, default=str, sort_keys=True))

    for relative in (
        "ceo_core/local_finite_file_provider_v1.py",
        "ceo_core/recovery_budget_guard_v1.py",
        "scripts/ceo_stdlib_work_mode.py",
        "ceo_core/goal_completion_gate.py",
        "ceo_core/productive_fallback_orchestrator_v1.py",
        "ceo_core/progress_tracker.py",
    ):
        ok, expected, actual = package_hash_ok(relative)
        print(
            "W9_PACKAGE_HASH",
            json.dumps(
                {"path": relative, "ok": ok, "expected": expected, "actual": actual},
                sort_keys=True,
            ),
        )
        if not ok:
            failures.append(f"package_hash_mismatch:{relative}")

    work_mode = (ROOT / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")
    required_source = [
        "LocalFiniteFileProviderV1",
        "parse_local_finite_file_goal",
        "configure_local_finite_file_state",
        'state.metadata["provider_mode"] = "local-finite-file"',
        "if not self.execution_enabled and not local_finite_spec",
    ]
    for needle in required_source:
        if needle not in work_mode:
            failures.append(f"work_mode_integration_missing:{needle}")

    if failures:
        print("W9_LOCAL_FINITE_REGRESSION_FAIL", json.dumps(failures, ensure_ascii=False))
        return 9

    print("W9_LOCAL_FINITE_REGRESSION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
