from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ["CEO_DEV313_BUILD_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))

from ceo_core.autonomous_loop import AutonomousProjectLoop
from ceo_core.completion import CompletionEngine
from ceo_core.deterministic_completion_certifier_v1 import DeterministicCompletionCertifierV1
from ceo_core.goal_completion_gate import GoalCompletionGate
from ceo_core.models import ProjectState, Task, TaskStatus


def make_state(*, field_required: bool = False, field_certified: bool = False) -> ProjectState:
    create = Task(
        id="create",
        title="Create AUTONOMY_GATE_1.md",
        status=TaskStatus.COMPLETE,
        result="Created and hashed requested deliverable.",
        quality_score=0.95,
        metadata={
            "artifacts": ["AUTONOMY_GATE_1.md"],
            "acceptance_evidence": True,
            "evidence_refs": ["file:AUTONOMY_GATE_1.md"],
        },
    )
    verify = Task(
        id="verify",
        title="Verify AUTONOMY_GATE_1.md",
        status=TaskStatus.COMPLETE,
        result="Independent verification pass.",
        quality_score=0.96,
        required_capabilities=["verification"],
        metadata={
            "independently_verified": True,
            "verification_application": {"task_id": "verify"},
            "acceptance_evidence": True,
        },
    )
    state = ProjectState(
        id="project-dev313",
        goal="Create AUTONOMY_GATE_1.md and verify it.",
        goal_success_definition="The file exists, contains the required report, and is independently verified.",
        completion_criteria=["requested file exists", "independent verification passed"],
        goal_deliverables=["AUTONOMY_GATE_1.md"],
        tasks={"create": create, "verify": verify},
        root_task_ids=["create", "verify"],
        metadata={
            "real_work_intake_v1": {"goal": "locked"},
            "strict_goal_completion_gate": True,
            "require_goal_audit": True,
            "min_goal_audit_evidence_refs": 2,
            "min_goal_audit_grounded_refs": 2,
            "min_goal_continuity_generations": 3,
            "goal_continuity_generation": 0,
            "requires_field_endurance_certification": field_required,
            "field_endurance_certified": field_certified,
            "deliverable_evidence": {
                "AUTONOMY_GATE_1.md": {
                    "task_id": "create",
                    "kind": "file",
                    "ref": "AUTONOMY_GATE_1.md",
                    "sha256": "a" * 64,
                    "size_bytes": 512,
                }
            },
        },
    )
    return state


def test_final_provider_independent_completion():
    state = make_state()
    gate = GoalCompletionGate()
    certifier = DeterministicCompletionCertifierV1()

    before = gate.evaluate(state, evidence_refs=gate.auto_evidence_refs(state))
    assert any(str(x).startswith("continuity_rounds:") for x in before.gaps), before.to_dict()
    assert state.metadata.get("goal_audit_passed") is not True

    row = certifier.apply(state, gate)
    assert row["work_complete"] is True, row
    assert row["final_complete"] is True, row
    assert state.metadata["goal_audit_passed"] is True
    assert state.metadata["completion_phase_v1"] == "deterministically_certified"
    assert state.metadata["goal_audit_evidence"]["source"] == "deterministic_completion_certificate_v1"
    assert len(state.metadata["goal_audit_evidence"]["evidence_refs"]) >= 2
    assert state.metadata["completion_evidence"]["requested file exists"]["source"] == "deterministic_completion_certificate_v1"

    assessment = CompletionEngine().assess(state)
    assert assessment.complete is True, assessment
    return {
        "provider_call_required": False,
        "goal_audit_passed": state.metadata["goal_audit_passed"],
        "completion_engine_complete": assessment.complete,
        "certificate": row["certificate_sha256"],
    }


def test_field_endurance_cannot_be_bypassed():
    state = make_state(field_required=True, field_certified=False)
    audit = Task(
        id="audit",
        title="Goal continuity audit #1",
        status=TaskStatus.READY,
        result=None,
        metadata={"goal_continuity_audit": True, "control_plane_atomic": True},
    )
    state.tasks[audit.id] = audit
    state.root_task_ids.append(audit.id)

    certifier = DeterministicCompletionCertifierV1()
    row = certifier.apply(state, GoalCompletionGate())

    assert row["work_complete"] is True, row
    assert row["final_complete"] is False, row
    assert row["pending_certifications"] == ["field_endurance_certification_required"], row
    assert state.metadata["work_complete_certified_v1"] is True
    assert state.metadata["goal_audit_passed"] is False
    assert state.metadata["completion_phase_v1"] == "work_complete_pending_certification"
    assert state.tasks["audit"].status == TaskStatus.SUPERSEDED
    assert state.metadata["operator_productivity_state"] == "CERTIFICACIÓN PENDIENTE"

    assessment = CompletionEngine().assess(state)
    assert assessment.complete is False
    return {
        "work_complete": True,
        "final_complete": False,
        "field_gate_preserved": True,
        "provider_audit_retired": state.tasks["audit"].status.value,
    }


def test_field_certification_promotes_without_provider():
    state = make_state(field_required=True, field_certified=False)
    certifier = DeterministicCompletionCertifierV1()
    first = certifier.apply(state, GoalCompletionGate())
    assert first["final_complete"] is False

    state.metadata["field_endurance_certified"] = True
    second = certifier.apply(state, GoalCompletionGate())
    assert second["work_complete"] is True
    assert second["final_complete"] is True
    assert state.metadata["goal_audit_passed"] is True
    assert state.metadata["completion_phase_v1"] == "deterministically_certified"
    return {
        "before": first["final_complete"],
        "after": second["final_complete"],
        "provider_call_required": False,
    }


def test_missing_deliverable_blocks_certificate():
    state = make_state()
    state.metadata["deliverable_evidence"] = {}
    row = DeterministicCompletionCertifierV1().apply(state, GoalCompletionGate())
    assert row["work_complete"] is False, row
    assert any(str(x).startswith("deliverable_unproven:") for x in row["non_certification_gaps"]), row
    assert state.metadata.get("goal_audit_passed", False) is not True
    return {"blocked": True, "gaps": row["non_certification_gaps"]}


def test_productive_blocker_blocks_certificate():
    state = make_state()
    blocked = Task(
        id="blocked",
        title="Unresolved productive task",
        status=TaskStatus.BLOCKED,
        result="",
        metadata={"task_role": "productive"},
    )
    state.tasks[blocked.id] = blocked
    state.root_task_ids.append(blocked.id)

    row = DeterministicCompletionCertifierV1().apply(state, GoalCompletionGate())
    assert row["work_complete"] is False, row
    assert "blocked" in row["blocking_productive_task_ids"], row
    assert state.metadata["goal_audit_passed"] is not True
    return {"blocked": True, "task_ids": row["blocking_productive_task_ids"]}


def test_certificate_is_bound_to_evidence():
    state = make_state()
    certifier = DeterministicCompletionCertifierV1()
    first = certifier.apply(state, GoalCompletionGate())
    h1 = first["certificate_sha256"]
    state.metadata["deliverable_evidence"]["AUTONOMY_GATE_1.md"]["sha256"] = "b" * 64
    second = certifier.apply(state, GoalCompletionGate())
    h2 = second["certificate_sha256"]
    assert h1 != h2
    assert second["changed"] is True
    return {"hash_changed": True, "before": h1, "after": h2}


def test_watchdog_holds_provider_free_pending_state():
    state = make_state(field_required=True, field_certified=False)
    certifier = DeterministicCompletionCertifierV1()
    certifier.apply(state, GoalCompletionGate())
    before = set(state.tasks)
    row = AutonomousProjectLoop().ensure_progress(state)
    after = set(state.tasks)
    assert row["status"] == "work_complete_pending_certification", row
    assert row["created"] == 0
    assert before == after
    return row


def test_ui_and_packaging_semantics():
    ui = (ROOT / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")
    scheduler = (ROOT / "ceo_core" / "scheduler.py").read_text(encoding="utf-8")
    loop = (ROOT / "ceo_core" / "autonomous_loop.py").read_text(encoding="utf-8")
    contract = (ROOT / "CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8")

    assert "work_complete_pending_certification" in ui
    assert "CEO no gastará llamadas IA ni creará nuevas auditorías mientras espera" in ui
    assert "DeterministicCompletionCertifierV1" in scheduler
    assert "deterministic_completion_certifier_last_v1" in scheduler
    assert "deterministic_completion_hold" in loop
    assert "ceo_core/deterministic_completion_certifier_v1.py" in contract
    return {
        "ui_pending_state": True,
        "scheduler_certifier": True,
        "watchdog_hold": True,
        "package_contract": True,
    }


def main():
    rows = {
        "final": test_final_provider_independent_completion(),
        "field_pending": test_field_endurance_cannot_be_bypassed(),
        "field_promote": test_field_certification_promotes_without_provider(),
        "missing_deliverable": test_missing_deliverable_blocks_certificate(),
        "productive_blocker": test_productive_blocker_blocks_certificate(),
        "hash_binding": test_certificate_is_bound_to_evidence(),
        "watchdog": test_watchdog_holds_provider_free_pending_state(),
        "ui_packaging": test_ui_and_packaging_semantics(),
    }
    print("DEV313_DETERMINISTIC_COMPLETION_PASS")
    print(rows)


if __name__ == "__main__":
    main()
