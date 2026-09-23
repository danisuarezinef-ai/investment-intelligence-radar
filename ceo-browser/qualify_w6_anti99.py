from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = REPO / "ceo-updates" / "CEO_1.5.92-rc1-native-transport-integrity.zip"


def add_src(root: pathlib.Path) -> None:
    sys.path.insert(0, str(root))


def make_state():
    from ceo_core.models import ProjectState, Task, TaskStatus

    create = Task(
        id="create",
        title="Create CEO_FIRST_RESULT.md",
        status=TaskStatus.COMPLETE,
        result="Created requested deliverable.",
        quality_score=0.95,
        metadata={
            "task_role": "productive",
            "artifacts": ["CEO_FIRST_RESULT.md"],
            "acceptance_evidence": True,
            "evidence_refs": ["file:CEO_FIRST_RESULT.md"],
        },
    )
    verify = Task(
        id="verify",
        title="Verify CEO_FIRST_RESULT.md",
        status=TaskStatus.COMPLETE,
        result="Independent verification passed.",
        quality_score=0.96,
        required_capabilities=["verification"],
        metadata={
            "task_role": "verification",
            "independently_verified": True,
            "verification_application": {"task_id": "verify"},
            "acceptance_evidence": True,
        },
    )
    # Historical/internal residue must never keep the visible project at 99%.
    old_audit = Task(
        id="old-audit",
        title="Historical goal continuity audit",
        status=TaskStatus.FAILED,
        result="historical control-plane failure",
        metadata={
            "task_role": "control",
            "goal_continuity_audit": True,
            "control_plane_atomic": True,
        },
    )

    state = ProjectState(
        id="w6-project",
        goal="Create CEO_FIRST_RESULT.md and verify it.",
        goal_definition="Create one finite verified file.",
        goal_success_definition="CEO_FIRST_RESULT.md exists, is non-empty and independently verified.",
        completion_criteria=[
            "requested file exists",
            "independent verification passed",
        ],
        goal_deliverables=["CEO_FIRST_RESULT.md"],
        tasks={t.id: t for t in (create, verify, old_audit)},
        root_task_ids=["create", "verify", "old-audit"],
        metadata={
            "real_work_intake_v1": {"goal": "locked"},
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
    return state


def main() -> int:
    assert PACKAGE.is_file(), PACKAGE
    with tempfile.TemporaryDirectory(prefix="ceo-w6-") as td:
        root = pathlib.Path(td)
        with zipfile.ZipFile(PACKAGE) as z:
            z.extractall(root)
        add_src(root)

        from ceo_core.completion import CompletionEngine
        from ceo_core.deterministic_completion_certifier_v1 import DeterministicCompletionCertifierV1
        from ceo_core.goal_completion_gate import GoalCompletionGate
        from ceo_core.models import TaskStatus
        from ceo_core.scheduler import ContinuousScheduler

        state = make_state()
        cert = DeterministicCompletionCertifierV1().apply(state, GoalCompletionGate())

        assert cert["work_complete"] is True, cert
        assert cert["final_complete"] is True, cert
        assert state.metadata.get("goal_audit_passed") is True
        assert state.metadata.get("completion_phase_v1") == "deterministically_certified"
        assert state.metadata.get("operator_productivity_state") == "COMPLETADO"
        # Historical goal audit is retired by deterministic completion.
        assert state.tasks["old-audit"].status == TaskStatus.SUPERSEDED, state.tasks["old-audit"].status

        assessment = CompletionEngine().assess(state)
        assert assessment.complete is True, assessment
        assert not assessment.blockers, assessment.blockers

        # Scheduler source contract: certificate is evaluated before project completion
        # and a positive completion assessment writes completed_at in the same loop.
        scheduler_text = (root / "ceo_core" / "scheduler.py").read_text(encoding="utf-8")
        cert_pos = scheduler_text.find("deterministic_completion_certifier_v1.apply")
        is_complete_pos = scheduler_text.find("if self._is_complete():")
        completed_pos = scheduler_text.find("self.state.completed_at = self.state.completed_at or utcnow()")
        assert 0 <= cert_pos < is_complete_pos < completed_pos, (cert_pos, is_complete_pos, completed_pos)

        # Exercise the exact scheduler completion predicate without running providers.
        sched = object.__new__(ContinuousScheduler)
        sched.state = state
        sched.completion_engine = CompletionEngine()
        assert ContinuousScheduler._is_complete(sched) is True
        assert sched.state.metadata["completion_assessment"]["complete"] is True

        # UI/progress truth.
        progress_file = root / "ceo_core" / "progress_tracker.py"
        assert progress_file.is_file(), "StableProgressTracker module missing"
        from ceo_core.progress_tracker import StableProgressTracker
        tracker = StableProgressTracker()
        snap = tracker.snapshot(state)
        display = float(snap.get("display_progress", -1))
        productive_pending = int(snap.get("productive_pending", -1))
        control_pending = int(snap.get("control_pending", -1))
        assert display == 100.0, snap
        assert productive_pending == 0, snap
        # Superseded historical control work may remain in history but must not reduce progress.
        assert control_pending == 0, snap

        # Missing deliverable must fail closed.
        broken = make_state()
        broken.metadata["deliverable_evidence"] = {}
        cert2 = DeterministicCompletionCertifierV1().apply(broken, GoalCompletionGate())
        assert cert2["final_complete"] is False, cert2
        assert CompletionEngine().assess(broken).complete is False

        # Field-endurance is NOT required for this simple finite objective.
        assert state.metadata.get("requires_field_endurance_certification") is False

        report = {
            "status": "W6_ANTI99_PASS",
            "package": PACKAGE.name,
            "deterministic_final_complete": cert["final_complete"],
            "goal_audit_passed": state.metadata.get("goal_audit_passed"),
            "completion_engine_complete": assessment.complete,
            "scheduler_predicate_complete": True,
            "display_progress": display,
            "productive_pending": productive_pending,
            "control_pending": control_pending,
            "historical_audit_status": state.tasks["old-audit"].status.value,
            "missing_deliverable_fails_closed": cert2["final_complete"] is False,
            "field_endurance_required_for_simple_goal": False,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
