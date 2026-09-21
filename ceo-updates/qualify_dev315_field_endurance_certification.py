from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ["CEO_DEV315_BUILD_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))

from ceo_core.deterministic_completion_certifier_v1 import DeterministicCompletionCertifierV1
from ceo_core.field_endurance_certification_v1 import FieldEnduranceCertificationV1
from ceo_core.goal_completion_gate import GoalCompletionGate
from ceo_core.models import ProjectState, Task, TaskStatus


def make_completed_state() -> ProjectState:
    create = Task(
        id="create",
        title="Create AUTONOMY_GATE_1.md",
        status=TaskStatus.COMPLETE,
        result="Created deliverable.",
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
        quality_score=0.95,
        required_capabilities=["verification"],
        metadata={
            "independently_verified": True,
            "verification_application": {"task_id": "verify"},
            "acceptance_evidence": True,
        },
    )
    return ProjectState(
        id="dev315-project",
        goal="Create and verify AUTONOMY_GATE_1.md",
        goal_success_definition="File exists and is independently verified.",
        completion_criteria=["file exists", "verification passed"],
        goal_deliverables=["AUTONOMY_GATE_1.md"],
        tasks={"create": create, "verify": verify},
        root_task_ids=["create", "verify"],
        metadata={
            "strict_goal_completion_gate": True,
            "require_goal_audit": True,
            "min_goal_audit_evidence_refs": 2,
            "min_goal_audit_grounded_refs": 2,
            "min_goal_continuity_generations": 3,
            "goal_continuity_generation": 0,
            "requires_field_endurance_certification": True,
            "field_endurance_certified": False,
            "deliverable_evidence": {
                "AUTONOMY_GATE_1.md": {
                    "task_id": "create",
                    "kind": "file",
                    "ref": "AUTONOMY_GATE_1.md",
                    "sha256": "a" * 64,
                    "size_bytes": 600,
                }
            },
        },
    )


def prepare_work_complete(state: ProjectState):
    row = DeterministicCompletionCertifierV1().apply(state, GoalCompletionGate())
    assert row["work_complete"] is True, row
    assert row["final_complete"] is False, row
    assert state.metadata["completion_phase_v1"] == "work_complete_pending_certification"
    return row


def test_active_time_only_and_sleep_gap_ignored():
    state = make_completed_state()
    prepare_work_complete(state)
    engine = FieldEnduranceCertificationV1(
        min_active_seconds=3.0, min_samples=4, max_sample_gap_seconds=1.0
    )
    a = engine.observe(state, now_monotonic=10.0, now_utc="2026-09-21T12:00:00+00:00")
    b = engine.observe(state, now_monotonic=11.0, now_utc="2026-09-21T12:00:01+00:00")
    c = engine.observe(state, now_monotonic=111.0, now_utc="2026-09-21T12:01:41+00:00")
    assert b["active_seconds"] == 1.0, b
    assert c["active_seconds"] == 2.0, c
    assert c["sleep_or_offline_seconds_ignored"] >= 99.0, c
    d = engine.observe(state, now_monotonic=112.0, now_utc="2026-09-21T12:01:42+00:00")
    assert d["active_seconds"] == 3.0, d
    assert d["certified"] is True, d
    return {
        "active_seconds": d["active_seconds"],
        "ignored_seconds": d["sleep_or_offline_seconds_ignored"],
        "certified": d["certified"],
    }


def test_pause_does_not_accumulate():
    state = make_completed_state()
    prepare_work_complete(state)
    engine = FieldEnduranceCertificationV1(
        min_active_seconds=2.0, min_samples=3, max_sample_gap_seconds=1.0
    )
    engine.observe(state, now_monotonic=1.0, now_utc="2026-09-21T12:00:00+00:00")
    state.paused = True
    paused = engine.observe(state, now_monotonic=2.0, now_utc="2026-09-21T12:00:01+00:00")
    assert paused["active_seconds"] == 0.0, paused
    assert "operator_paused" in paused["blocking_reasons"]
    state.paused = False
    resumed = engine.observe(state, now_monotonic=3.0, now_utc="2026-09-21T12:00:02+00:00")
    assert resumed["active_seconds"] == 1.0, resumed
    return {"paused_not_counted": True, "after_resume_seconds": resumed["active_seconds"]}


def test_scheduler_crash_blocks_certificate():
    state = make_completed_state()
    prepare_work_complete(state)
    engine = FieldEnduranceCertificationV1(
        min_active_seconds=1.0, min_samples=2, max_sample_gap_seconds=1.0
    )
    engine.observe(state, now_monotonic=1.0, now_utc="2026-09-21T12:00:00+00:00")
    state.metadata.setdefault("scheduler_crash_history", []).append(
        {"ts": "2026-09-21T12:00:00.5+00:00", "error": "synthetic crash"}
    )
    row = engine.observe(state, now_monotonic=2.0, now_utc="2026-09-21T12:00:01+00:00")
    assert row["certified"] is False, row
    assert row["new_scheduler_crashes"] == 1, row
    assert "scheduler_crash_observed" in row["blocking_reasons"], row
    return row


def test_recovery_storm_blocks_certificate():
    state = make_completed_state()
    prepare_work_complete(state)
    state.metadata["global_recovery_storm_breaker"] = {"open": True}
    engine = FieldEnduranceCertificationV1(
        min_active_seconds=1.0, min_samples=2, max_sample_gap_seconds=1.0
    )
    engine.observe(state, now_monotonic=1.0, now_utc="2026-09-21T12:00:00+00:00")
    row = engine.observe(state, now_monotonic=2.0, now_utc="2026-09-21T12:00:01+00:00")
    assert row["certified"] is False, row
    assert "recovery_storm_active" in row["blocking_reasons"], row
    return {"blocked": True, "reasons": row["blocking_reasons"]}


def test_cannot_certify_before_work_complete():
    state = make_completed_state()
    engine = FieldEnduranceCertificationV1(
        min_active_seconds=1.0, min_samples=2, max_sample_gap_seconds=1.0
    )
    engine.observe(state, now_monotonic=1.0, now_utc="2026-09-21T12:00:00+00:00")
    row = engine.observe(state, now_monotonic=2.0, now_utc="2026-09-21T12:00:01+00:00")
    assert row["certified"] is False, row
    assert "work_not_yet_complete" in row["blocking_reasons"], row
    return row


def test_field_certificate_promotes_final_without_provider():
    state = make_completed_state()
    certifier = DeterministicCompletionCertifierV1()
    first = certifier.apply(state, GoalCompletionGate())
    assert first["work_complete"] is True and first["final_complete"] is False

    engine = FieldEnduranceCertificationV1(
        min_active_seconds=1.0, min_samples=2, max_sample_gap_seconds=1.0
    )
    engine.observe(state, now_monotonic=10.0, now_utc="2026-09-21T12:00:00+00:00")
    field = engine.observe(state, now_monotonic=11.0, now_utc="2026-09-21T12:00:01+00:00")
    assert field["certified"] is True, field
    receipt = state.metadata["field_endurance_certificate_v1"]
    assert receipt["provider_assertion_used"] is False
    assert receipt["human_override_used"] is False
    assert len(receipt["certificate_sha256"]) == 64

    final = certifier.apply(state, GoalCompletionGate())
    assert final["final_complete"] is True, final
    assert state.metadata["goal_audit_passed"] is True
    assert state.metadata["completion_phase_v1"] == "deterministically_certified"
    return {
        "field_certified": True,
        "provider_assertion_used": receipt["provider_assertion_used"],
        "final_complete": final["final_complete"],
        "field_certificate": receipt["certificate_sha256"],
    }


def test_epoch_reset_invalidates_old_field_cert():
    state = make_completed_state()
    state.metadata["field_endurance_certified"] = True
    state.metadata["field_endurance_telemetry_v1"] = {
        "epoch": "old-epoch",
        "certified": True,
        "active_seconds": 99999,
    }
    state.metadata["field_endurance_certificate_v1"] = {"certificate_sha256": "f" * 64}
    engine = FieldEnduranceCertificationV1(
        min_active_seconds=10.0, min_samples=3, max_sample_gap_seconds=1.0
    )
    row = engine.observe(state, now_monotonic=50.0, now_utc="2026-09-21T12:00:00+00:00")
    assert row["certified"] is False
    assert state.metadata["field_endurance_certified"] is False
    assert "field_endurance_certificate_v1" not in state.metadata
    assert row["active_seconds"] == 0.0
    return {"old_certificate_invalidated": True, "active_seconds": row["active_seconds"]}


def test_packaging_and_ui():
    scheduler = (ROOT / "ceo_core" / "scheduler.py").read_text(encoding="utf-8")
    ui = (ROOT / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")
    contract = (ROOT / "CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8")
    engine_text = (ROOT / "ceo_core" / "field_endurance_certification_v1.py").read_text(encoding="utf-8")
    assert "FieldEnduranceCertificationV1" in scheduler
    assert "field_endurance_last_v1" in scheduler
    assert "re-evaluate deterministic" in scheduler
    assert "field_endurance" in ui
    assert "El tiempo con el PC suspendido no cuenta" in ui
    assert "ceo_core/field_endurance_certification_v1.py" in contract
    assert "provider_assertion_used" in engine_text
    assert "MAX_COUNTED_SAMPLE_GAP_SECONDS" in engine_text
    return {
        "scheduler_integrated": True,
        "ui_progress": True,
        "package_contract": True,
        "provider_independent": True,
    }


def main():
    rows = {
        "active_time": test_active_time_only_and_sleep_gap_ignored(),
        "pause": test_pause_does_not_accumulate(),
        "crash": test_scheduler_crash_blocks_certificate(),
        "storm": test_recovery_storm_blocks_certificate(),
        "premature": test_cannot_certify_before_work_complete(),
        "promotion": test_field_certificate_promotes_final_without_provider(),
        "epoch_reset": test_epoch_reset_invalidates_old_field_cert(),
        "packaging": test_packaging_and_ui(),
    }
    print("DEV315_FIELD_ENDURANCE_CERTIFICATION_PASS")
    print(rows)


if __name__ == "__main__":
    main()
