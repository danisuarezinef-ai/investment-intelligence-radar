from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ["CEO_W6_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))

from ceo_core.completion import CompletionEngine
from ceo_core.deterministic_completion_certifier_v1 import DeterministicCompletionCertifierV1
from ceo_core.goal_completion_gate import GoalCompletionGate
from ceo_core.models import ProjectState, Task, TaskStatus, utcnow
from ceo_core.progress_tracker import StableProgressTracker


def make_state() -> ProjectState:
    create = Task(
        id="create",
        title="Create CEO_FIRST_RESULT.md",
        status=TaskStatus.COMPLETE,
        result="Created and hashed requested deliverable.",
        quality_score=0.95,
        metadata={
            "task_role": "productive",
            "artifacts": ["CEO_FIRST_RESULT.md"],
            "acceptance_evidence": True,
        },
    )
    verify = Task(
        id="verify",
        title="Verify CEO_FIRST_RESULT.md",
        status=TaskStatus.COMPLETE,
        result="Independent verification pass.",
        quality_score=0.96,
        required_capabilities=["verification"],
        metadata={
            "task_role": "verification",
            "independently_verified": True,
            "verification_application": {"task_id": "verify"},
            "acceptance_evidence": True,
        },
    )
    return ProjectState(
        id="w6-project",
        goal="Create CEO_FIRST_RESULT.md and verify it.",
        goal_success_definition="The requested file exists, is non-empty, and is independently verified.",
        completion_criteria=["requested file exists", "independent verification passed"],
        goal_deliverables=["CEO_FIRST_RESULT.md"],
        tasks={"create": create, "verify": verify},
        root_task_ids=["create", "verify"],
        metadata={
            "real_work_intake_v1": {"mode": "general_supervised"},
            "strict_goal_completion_gate": True,
            "require_goal_audit": True,
            "min_goal_audit_evidence_refs": 2,
            "min_goal_audit_grounded_refs": 2,
            "min_goal_continuity_generations": 3,
            "goal_continuity_generation": 0,
            "requires_field_endurance_certification": False,
            "field_endurance_certified": False,
            "deliverable_evidence": {
                "CEO_FIRST_RESULT.md": {
                    "task_id": "create",
                    "kind": "file",
                    "ref": "CEO_FIRST_RESULT.md",
                    "sha256": "a" * 64,
                    "size_bytes": 512,
                }
            },
        },
    )


def main() -> int:
    state = make_state()
    gate = GoalCompletionGate()
    cert = DeterministicCompletionCertifierV1().apply(state, gate)
    assert cert["work_complete"] is True, cert
    assert cert["final_complete"] is True, cert
    assert state.metadata.get("goal_audit_passed") is True
    assessment = CompletionEngine().assess(state)
    assert assessment.complete is True, assessment

    state.completed_at = utcnow()
    progress = StableProgressTracker().snapshot(state, persist=True)
    print("W6_PROGRESS_AFTER_COMPLETION", json.dumps(progress, default=str, sort_keys=True))

    payload = state.model_dump_json()
    restored = ProjectState.model_validate_json(payload)
    migration = GoalCompletionGate().migrate_invalid_legacy_pass(restored)
    print("W6_REOPEN_MIGRATION", json.dumps(migration, default=str, sort_keys=True))
    print("W6_REOPEN_STATE", json.dumps({
        "completed_at": str(restored.completed_at) if restored.completed_at else None,
        "goal_audit_passed": restored.metadata.get("goal_audit_passed"),
        "completion_phase": restored.metadata.get("completion_phase_v1"),
        "source": (restored.metadata.get("goal_audit_evidence") or {}).get("source"),
    }, sort_keys=True))

    failures = []
    if int(progress.get("display_progress", -1)) != 100:
        failures.append(f"display_progress_after_completion={progress.get('display_progress')}")
    if migration.get("changed"):
        failures.append("deterministic_completion_reopened_by_legacy_migration")
    if restored.completed_at is None:
        failures.append("completed_at_lost_on_reopen")
    if restored.metadata.get("goal_audit_passed") is not True:
        failures.append("goal_audit_passed_lost_on_reopen")

    if failures:
        print("W6_ANTI99_REGRESSION_FAIL", failures)
        return 7

    print("W6_ANTI99_REGRESSION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
