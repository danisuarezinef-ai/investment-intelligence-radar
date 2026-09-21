from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(os.environ["CEO_DEV309_BUILD_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))

from ceo_core.goal_engine import GoalEngine
from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.result_protocol import extract_directive
from ceo_core.goal_completion_gate import GoalCompletionGate
from ceo_core.scheduler import RELIABILITY_EPOCH, _apply_reliability_epoch_migration, _promote_provider_artifact_to_deliverable
from ceo_core.autonomous_loop import AutonomousProjectLoop
from ceo_core.self_hosting_tools import FilesystemOperations, ArtifactExchangeLayer
from ceo_core.deliverable_evidence_engine_v1 import DeliverableEvidenceEngineV1

EXPECTED_EPOCH = "dev309-closure-convergence-v1"
FIELD_GOAL = (
    "Crea en tu espacio de trabajo un archivo AUTONOMY_GATE_1.md. Debe contener tu "
    "versión activa, estado del proveedor IA, estado del scheduler, número de tareas "
    "creadas, completadas y bloqueadas, recuperaciones utilizadas durante este objetivo "
    "y una conclusión indicando si el objetivo se completó sin intervención humana. "
    "Comprueba que el archivo existe y tiene contenido antes de dar el objetivo por terminado."
)


def add(state: ProjectState, task: Task) -> Task:
    state.tasks[task.id] = task
    state.root_task_ids.append(task.id)
    return task


def test_goal_deliverable_inference():
    g = GoalEngine().lock(FIELD_GOAL)
    assert g.deliverables == ["AUTONOMY_GATE_1.md"], g.deliverables
    return g.deliverables


def test_protocol_write_files_and_evidence_refs():
    text = """Resultado sustantivo.
<CEO_RESULT>{"status":"complete","reason":"done","evidence_refs":["abc123"],"write_files":[{"path":"AUTONOMY_GATE_1.md","content":"# Gate OK"}]}</CEO_RESULT>"""
    d = extract_directive(text)
    assert d is not None
    assert d.evidence_refs == ["abc123"]
    assert len(d.write_files) == 1
    assert d.write_files[0].path == "AUTONOMY_GATE_1.md"
    assert "# Gate" in d.write_files[0].content
    return {"evidence_refs": d.evidence_refs, "path": d.write_files[0].path}


def test_guarded_workspace_write_and_evidence():
    state = ProjectState(goal=FIELD_GOAL, goal_deliverables=["AUTONOMY_GATE_1.md"])
    task = add(state, Task(title="Create file", status=TaskStatus.COMPLETE, metadata={"task_role":"productive"}))
    with tempfile.TemporaryDirectory(prefix="dev309-ws-") as td:
        fs = FilesystemOperations(td)
        row = fs.write_text("AUTONOMY_GATE_1.md", "# AUTONOMY GATE\nstatus: ok\n")
        assert row["size_bytes"] > 0
        exchange = ArtifactExchangeLayer(td)
        reg = exchange.register(state, "AUTONOMY_GATE_1.md", task_id=task.id, direction="worker_output")
        ev = DeliverableEvidenceEngineV1().record_file(
            state, task, pathlib.Path(td) / "AUTONOMY_GATE_1.md", root=td
        )
        assert reg["verified_exists"] is True
        assert ev.size_bytes > 0

        escaped = False
        try:
            fs.write_text("../escape.md", "bad")
        except Exception:
            escaped = True
        assert escaped, "workspace guard allowed escape"
        return {"sha256": row["sha256"], "size_bytes": row["size_bytes"], "artifact_id": reg["artifact_id"]}


def test_provider_artifact_promotion():
    with tempfile.TemporaryDirectory(prefix="dev309-promote-ws-") as ws, tempfile.TemporaryDirectory(prefix="dev309-provider-art-") as out:
        source = pathlib.Path(out) / "opaque-task-id.md"
        source.write_text("# Gate\n\nBOOTSTRAP PASS\n", encoding="utf-8")
        row = _promote_provider_artifact_to_deliverable(
            ws, "AUTONOMY_GATE_1.md", [str(source)]
        )
        target = pathlib.Path(ws) / "AUTONOMY_GATE_1.md"
        assert row["promoted"] is True, row
        assert target.is_file()
        assert "BOOTSTRAP PASS" in target.read_text(encoding="utf-8")

        none = _promote_provider_artifact_to_deliverable(
            ws, "second.md", [str(pathlib.Path(out) / "missing.md")]
        )
        assert none["promoted"] is False, none

        escaped = False
        try:
            _promote_provider_artifact_to_deliverable(
                ws, "../escape.md", [str(source)]
            )
        except Exception:
            escaped = True
        assert escaped, "promotion allowed workspace escape"
        return {"promoted": row, "missing_source": none, "escape_blocked": escaped}


def test_evidence_candidates_and_auto_selection():
    state = ProjectState(goal=FIELD_GOAL, goal_deliverables=["AUTONOMY_GATE_1.md"])
    state.metadata.update({
        "strict_goal_completion_gate": True,
        "min_goal_audit_evidence_refs": 2,
        "min_goal_audit_grounded_refs": 2,
        "min_goal_continuity_generations": 1,
        "goal_continuity_generation": 1,
    })
    artifact = add(state, Task(
        title="Create AUTONOMY_GATE_1.md",
        status=TaskStatus.COMPLETE,
        result="file produced",
        metadata={"task_role":"productive","artifacts":["AUTONOMY_GATE_1.md"],"acceptance_evidence":True},
    ))
    verify = add(state, Task(
        title="Verify AUTONOMY_GATE_1.md",
        status=TaskStatus.COMPLETE,
        result="exists and non-empty",
        required_capabilities=["verification"],
        metadata={"task_role":"verification","independently_verified":True,"acceptance_evidence":True},
    ))
    state.metadata["deliverable_evidence"] = {
        "AUTONOMY_GATE_1.md": {"task_id": artifact.id, "artifact":"AUTONOMY_GATE_1.md"}
    }
    gate = GoalCompletionGate()
    candidates = gate.evidence_candidates(state)
    refs = gate.auto_evidence_refs(state)
    assert artifact.id in refs, refs
    assert verify.id in refs, refs
    verdict = gate.evaluate(state, evidence_refs=refs)
    assert verdict.eligible is True, verdict
    return {"refs": refs, "verdict": verdict.to_dict(), "candidates": candidates}


def test_field_173_migration():
    state = ProjectState(goal=FIELD_GOAL)
    state.metadata.update({
        "worker_recoveries": 0,
        "goal_continuity_generation": 173,
        "goal_audit_passed": False,
        "continuity_nonspawn_rejections": 1,
        "reliability_epoch_v1": {"epoch":"dev308-executable-route-integrity-v1"},
    })
    for i in range(195):
        add(state, Task(
            title=f"Completed work {i}",
            status=TaskStatus.COMPLETE,
            result="done",
            metadata={"task_role":"productive" if i < 10 else "control"},
        ))
    audit = add(state, Task(
        title="Goal continuity audit #173: plan the next autonomous work batch",
        status=TaskStatus.RETRY,
        metadata={"goal_continuity_audit":True,"control_plane_atomic":True,"task_role":"control"},
    ))
    out = _apply_reliability_epoch_migration(state)
    assert RELIABILITY_EPOCH == EXPECTED_EPOCH
    assert out["changed"] is True
    assert state.goal_deliverables == ["AUTONOMY_GATE_1.md"], state.goal_deliverables
    assert state.metadata["closure_profile_v1"]["profile"] == "bounded_single_artifact"
    assert state.metadata["min_goal_audit_evidence_refs"] == 2
    assert state.metadata["min_goal_audit_grounded_refs"] == 2
    assert state.metadata["min_goal_continuity_generations"] == 1
    assert state.metadata["max_goal_continuity_generations"] == 4
    assert state.metadata["historical_goal_continuity_generation"] == 173
    assert state.metadata["goal_continuity_generation"] == 0
    assert audit.status == TaskStatus.SUPERSEDED
    return {
        "migration": out,
        "closure_profile": state.metadata["closure_profile_v1"],
        "historical_generation": state.metadata["historical_goal_continuity_generation"],
        "current_generation": state.metadata["goal_continuity_generation"],
    }


def test_generation_cap_fail_closed():
    state = ProjectState(goal="bounded closure", goal_deliverables=["out.md"])
    state.metadata.update({
        "require_goal_audit": True,
        "goal_audit_passed": False,
        "goal_continuity_generation": 4,
        "max_goal_continuity_generations": 4,
        "last_goal_audit_rejection": {"gaps":["deliverable_unproven:out.md"]},
    })
    add(state, Task(
        title="Domain work",
        status=TaskStatus.COMPLETE,
        result="done",
        metadata={"task_role":"productive","acceptance_evidence":True},
    ))
    out = AutonomousProjectLoop().ensure_progress(state)
    assert out["status"] == "closure_bounded_stall", out
    assert state.metadata["operator_productivity_state"] == "BLOQUEADO"
    assert "agotado" in state.metadata["operator_block_reason"].lower()
    return out


def source_semantics():
    result_protocol = (ROOT/"ceo_core/result_protocol.py").read_text(encoding="utf-8")
    ai_worker = (ROOT/"ceo_core/ai_worker.py").read_text(encoding="utf-8")
    scheduler = (ROOT/"ceo_core/scheduler.py").read_text(encoding="utf-8")
    gate = (ROOT/"ceo_core/goal_completion_gate.py").read_text(encoding="utf-8")
    loop = (ROOT/"ceo_core/autonomous_loop.py").read_text(encoding="utf-8")

    assert "write_files" in result_protocol
    assert "evidence_refs" in ai_worker and "write_files" in ai_worker
    assert "FilesystemOperations" in scheduler
    assert "goal_audit_evidence_candidates" in scheduler
    assert "workspace_artifact_written" in scheduler
    assert "_promote_provider_artifact_to_deliverable" in scheduler
    assert "closure_artifact_promoted" in scheduler
    assert "auto_evidence_refs" in gate
    assert "max_goal_continuity_generations" in loop
    return True


def main():
    rows = {
        "deliverable_inference": test_goal_deliverable_inference(),
        "protocol": test_protocol_write_files_and_evidence_refs(),
        "workspace": test_guarded_workspace_write_and_evidence(),
        "provider_artifact_promotion": test_provider_artifact_promotion(),
        "evidence": test_evidence_candidates_and_auto_selection(),
        "field_173": test_field_173_migration(),
        "generation_cap": test_generation_cap_fail_closed(),
        "source_semantics": source_semantics(),
    }
    print("DEV309_CLOSURE_CONVERGENCE_PASS")
    print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
