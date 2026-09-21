from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE = REPO / "ceo-updates" / "CEO_1.5.88-rc1-provider-trust-integrity.zip"
ROOT = pathlib.Path(os.environ.get("CEO_DEV313_BUILD_ROOT", "/tmp/ceo-dev313-deterministic-completion"))
OLD_VERSION = "1.5.88-rc1-provider-trust-integrity"
VERSION = "1.5.89-rc1-deterministic-completion"


CERTIFIER = r'''from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from .models import ProjectState, TaskStatus
from .task_roles_v2 import is_productive
from .continuity_policy import task_for_decision, protected_human_gate


BLOCKING_PRODUCTIVE = {
    TaskStatus.READY,
    TaskStatus.RUNNING,
    TaskStatus.RETRY,
    TaskStatus.WAITING,
    TaskStatus.BLOCKED,
    TaskStatus.FAILED,
    TaskStatus.NEEDS_REVIEW,
}


@dataclass(slots=True)
class DeterministicCompletionCertificate:
    schema_version: int
    project_id: str
    work_complete: bool
    final_complete: bool
    evidence_refs: list[str]
    grounded_refs: list[str]
    blocking_productive_task_ids: list[str]
    non_certification_gaps: list[str]
    pending_certifications: list[str]
    deliverables: dict[str, Any]
    certificate_sha256: str
    issued_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeterministicCompletionCertifierV1:
    """Provider-independent completion/certification bridge.

    It can prove that autonomous *work* is finished from durable evidence without
    asking a language model to say PASS. External/field certification remains a
    separate gate and is never fabricated.
    """

    SCHEMA_VERSION = 1
    PENDING_FIELD = "field_endurance_certification_required"

    @staticmethod
    def _open_human_decisions(state: ProjectState) -> list[str]:
        rows: list[str] = []
        for decision in state.decisions.values():
            if getattr(decision.status, "value", decision.status) != "open":
                continue
            task = task_for_decision(state, decision)
            if task is None:
                rows.append(str(decision.id))
                continue
            if is_productive(task, state) or protected_human_gate(task, decision.metadata):
                rows.append(str(decision.id))
        return rows

    @staticmethod
    def _blocking_productive(state: ProjectState) -> list[str]:
        return [
            task.id
            for task in state.leaf_tasks
            if is_productive(task, state) and task.status in BLOCKING_PRODUCTIVE
        ]

    @staticmethod
    def _deliverable_snapshot(state: ProjectState) -> dict[str, Any]:
        rows = state.metadata.get("deliverable_evidence") or {}
        out: dict[str, Any] = {}
        for name in state.goal_deliverables:
            row = rows.get(name)
            if isinstance(row, dict):
                out[name] = {
                    "task_id": str(row.get("task_id") or ""),
                    "sha256": str(row.get("sha256") or ""),
                    "size_bytes": int(row.get("size_bytes") or 0),
                    "ref": str(row.get("ref") or row.get("path") or ""),
                }
            else:
                out[name] = None
        return out

    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return sha256(canonical).hexdigest()

    def assess(self, state: ProjectState, goal_gate) -> DeterministicCompletionCertificate:
        refs = goal_gate.auto_evidence_refs(state)
        verdict = goal_gate.evaluate(state, evidence_refs=refs)

        pending_certifications: list[str] = []
        non_certification_gaps: list[str] = []
        for gap in verdict.gaps:
            text = str(gap)
            if text.startswith("continuity_rounds:"):
                # Continuity rounds are a provider-era control mechanism. The
                # deterministic certificate replaces them when all evidence gates pass.
                continue
            if text == self.PENDING_FIELD:
                pending_certifications.append(text)
                continue
            non_certification_gaps.append(text)

        productive_blockers = self._blocking_productive(state)
        human_decisions = self._open_human_decisions(state)
        if human_decisions:
            non_certification_gaps.append(
                "open_human_decisions:" + ",".join(sorted(human_decisions)[:20])
            )

        work_complete = not non_certification_gaps and not productive_blockers
        final_complete = work_complete and not pending_certifications

        core = {
            "schema_version": self.SCHEMA_VERSION,
            "project_id": state.id,
            "goal": state.goal,
            "work_complete": work_complete,
            "final_complete": final_complete,
            "evidence_refs": list(verdict.evidence_refs),
            "grounded_refs": list(verdict.grounded_refs),
            "blocking_productive_task_ids": list(productive_blockers),
            "non_certification_gaps": list(non_certification_gaps),
            "pending_certifications": list(pending_certifications),
            "deliverables": self._deliverable_snapshot(state),
        }
        digest = self._hash_payload(core)
        return DeterministicCompletionCertificate(
            schema_version=self.SCHEMA_VERSION,
            project_id=state.id,
            work_complete=work_complete,
            final_complete=final_complete,
            evidence_refs=list(verdict.evidence_refs),
            grounded_refs=list(verdict.grounded_refs),
            blocking_productive_task_ids=list(productive_blockers),
            non_certification_gaps=list(non_certification_gaps),
            pending_certifications=list(pending_certifications),
            deliverables=core["deliverables"],
            certificate_sha256=digest,
            issued_at=datetime.now(timezone.utc).isoformat(),
        )

    def apply(self, state: ProjectState, goal_gate) -> dict[str, Any]:
        cert = self.assess(state, goal_gate)
        current = state.metadata.get("deterministic_completion_certificate_v1") or {}
        changed = str(current.get("certificate_sha256") or "") != cert.certificate_sha256

        if not cert.work_complete:
            if state.metadata.get("work_complete_certified_v1"):
                changed = True
            state.metadata["work_complete_certified_v1"] = False
            state.metadata["suppress_goal_continuity_audits_v1"] = False
            if state.metadata.get("goal_audit_evidence", {}).get("source") == "deterministic_completion_certificate_v1":
                state.metadata["goal_audit_passed"] = False
                state.metadata.pop("goal_audit_evidence", None)
            state.metadata["completion_phase_v1"] = "working"
        else:
            state.metadata["work_complete_certified_v1"] = True
            state.metadata["suppress_goal_continuity_audits_v1"] = True
            state.metadata.pop("autonomy_stalled", None)
            state.metadata.pop("operator_block_reason", None)

            retired: list[str] = []
            for task in state.leaf_tasks:
                if not task.metadata.get("goal_continuity_audit"):
                    continue
                if task.status in {
                    TaskStatus.READY, TaskStatus.RETRY, TaskStatus.WAITING,
                    TaskStatus.BLOCKED, TaskStatus.NEEDS_REVIEW, TaskStatus.FAILED,
                }:
                    task.status = TaskStatus.SUPERSEDED
                    task.worker_id = None
                    task.metadata["superseded_reason"] = "deterministic_completion_certificate_replaced_provider_audit"
                    retired.append(task.id)
            if retired:
                state.metadata["deterministic_completion_retired_audits_v1"] = retired[-50:]
                changed = True

            if cert.pending_certifications:
                state.metadata["completion_phase_v1"] = "work_complete_pending_certification"
                state.metadata["operator_productivity_state"] = "CERTIFICACIÓN PENDIENTE"
                state.metadata["goal_audit_passed"] = False
            else:
                state.metadata["completion_phase_v1"] = "deterministically_certified"
                state.metadata["operator_productivity_state"] = "COMPLETADO"
                state.metadata["goal_audit_passed"] = True
                state.metadata["goal_audit_evidence"] = {
                    "source": "deterministic_completion_certificate_v1",
                    "certificate_sha256": cert.certificate_sha256,
                    "verified_at": cert.issued_at,
                    "evidence_refs": list(cert.evidence_refs),
                    "grounded_refs": list(cert.grounded_refs),
                }
                supporting = (cert.grounded_refs or cert.evidence_refs)
                supporting_task = supporting[0] if supporting else None
                completion_evidence = state.metadata.setdefault("completion_evidence", {})
                for criterion in state.completion_criteria:
                    completion_evidence[criterion] = {
                        "task_id": supporting_task,
                        "source": "deterministic_completion_certificate_v1",
                        "evidence_refs": list(cert.evidence_refs),
                        "certificate_sha256": cert.certificate_sha256,
                    }

        if changed:
            state.metadata["deterministic_completion_certificate_v1"] = cert.to_dict()
            state.metadata["deterministic_completion_certificate_updated_at"] = cert.issued_at

        return {
            "changed": bool(changed),
            "work_complete": cert.work_complete,
            "final_complete": cert.final_complete,
            "pending_certifications": list(cert.pending_certifications),
            "non_certification_gaps": list(cert.non_certification_gaps),
            "blocking_productive_task_ids": list(cert.blocking_productive_task_ids),
            "certificate_sha256": cert.certificate_sha256,
        }
'''


def patch_scheduler() -> None:
    p = ROOT / "ceo_core" / "scheduler.py"
    s = p.read_text(encoding="utf-8")

    import_anchor = "from .deliverable_evidence_engine_v1 import DeliverableEvidenceEngineV1\n"
    import_new = import_anchor + "from .deterministic_completion_certifier_v1 import DeterministicCompletionCertifierV1\n"
    if s.count(import_anchor) != 1:
        raise RuntimeError(f"scheduler certifier import anchor={s.count(import_anchor)}")
    s = s.replace(import_anchor, import_new, 1)

    init_anchor = "        self.deliverable_evidence_v1 = DeliverableEvidenceEngineV1()\n"
    init_new = init_anchor + "        self.deterministic_completion_certifier_v1 = DeterministicCompletionCertifierV1()\n"
    if s.count(init_anchor) != 1:
        raise RuntimeError(f"scheduler certifier init anchor={s.count(init_anchor)}")
    s = s.replace(init_anchor, init_new, 1)

    loop_anchor = '''            self._collect_finished()
            reconcile = self.scheduler_reconciler_v1.reconcile(
'''
    loop_new = '''            self._collect_finished()
            deterministic_completion = self.deterministic_completion_certifier_v1.apply(
                self.state, self.goal_completion_gate
            )
            self.state.metadata["deterministic_completion_certifier_last_v1"] = deterministic_completion
            reconcile = self.scheduler_reconciler_v1.reconcile(
'''
    if s.count(loop_anchor) != 1:
        raise RuntimeError(f"scheduler certifier loop anchor={s.count(loop_anchor)}")
    s = s.replace(loop_anchor, loop_new, 1)

    p.write_text(s, encoding="utf-8")


def patch_autonomous_loop() -> None:
    p = ROOT / "ceo_core" / "autonomous_loop.py"
    s = p.read_text(encoding="utf-8")

    tick_anchor = '''    def tick(self, state: ProjectState, *, decomposer=None) -> dict:
        tree = self.director.rebuild(state)
'''
    tick_new = '''    def tick(self, state: ProjectState, *, decomposer=None) -> dict:
        if state.metadata.get("work_complete_certified_v1") and state.metadata.get("suppress_goal_continuity_audits_v1"):
            watchdog = self.ensure_progress(state, decomposer=decomposer)
            state.metadata["autonomous_loop"] = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "directors": 0,
                "knowledge": {},
                "replan_actions": 0,
                "replan_changes": 0,
                "recursive_planning": {},
                "watchdog": watchdog,
                "deterministic_completion_hold": True,
            }
            return dict(state.metadata["autonomous_loop"])

        tree = self.director.rebuild(state)
'''
    if s.count(tick_anchor) != 1:
        raise RuntimeError(f"autonomous loop tick hold anchor={s.count(tick_anchor)}")
    s = s.replace(tick_anchor, tick_new, 1)

    ensure_anchor = '''    def ensure_progress(self, state: ProjectState, *, decomposer=None) -> dict:
        if state.paused or state.completed_at is not None:
            return {"status": "inactive", "created": 0, "changed": 0}

'''
    ensure_new = '''    def ensure_progress(self, state: ProjectState, *, decomposer=None) -> dict:
        if state.paused or state.completed_at is not None:
            return {"status": "inactive", "created": 0, "changed": 0}

        if state.metadata.get("work_complete_certified_v1") and state.metadata.get("suppress_goal_continuity_audits_v1"):
            pending = list(
                (state.metadata.get("deterministic_completion_certificate_v1") or {}).get("pending_certifications") or []
            )
            return {
                "status": (
                    "work_complete_pending_certification"
                    if pending else "deterministically_certified"
                ),
                "created": 0,
                "changed": 0,
                "pending_certifications": pending,
                "certificate_sha256": (
                    state.metadata.get("deterministic_completion_certificate_v1") or {}
                ).get("certificate_sha256"),
            }

'''
    if s.count(ensure_anchor) != 1:
        raise RuntimeError(f"autonomous loop ensure hold anchor={s.count(ensure_anchor)}")
    s = s.replace(ensure_anchor, ensure_new, 1)
    p.write_text(s, encoding="utf-8")


def patch_work_mode() -> None:
    p = ROOT / "scripts" / "ceo_stdlib_work_mode.py"
    s = p.read_text(encoding="utf-8")

    snapshot_anchor = '''            "field_endurance_required": bool(state.metadata.get("requires_field_endurance_certification", False)),
            "field_endurance_certified": bool(state.metadata.get("field_endurance_certified", False)),
            "metrics": {
'''
    snapshot_new = '''            "field_endurance_required": bool(state.metadata.get("requires_field_endurance_certification", False)),
            "field_endurance_certified": bool(state.metadata.get("field_endurance_certified", False)),
            "work_complete_certified": bool(state.metadata.get("work_complete_certified_v1", False)),
            "completion_phase": str(state.metadata.get("completion_phase_v1") or ""),
            "deterministic_completion_certificate": state.metadata.get("deterministic_completion_certificate_v1"),
            "metrics": {
'''
    if s.count(snapshot_anchor) != 1:
        raise RuntimeError(f"work mode snapshot cert anchor={s.count(snapshot_anchor)}")
    s = s.replace(snapshot_anchor, snapshot_new, 1)

    banner_anchor = """else if(!live){$('actionBanner').className='banner warnb';$('actionBanner').textContent='Gemini no está activo. CEO no está trabajando.'}
"""
    banner_new = """else if(s.work_complete_certified&&s.completion_phase==='work_complete_pending_certification'){$('actionBanner').className='banner infob';$('actionBanner').textContent='✓ Trabajo del objetivo completado con evidencia determinista. Solo queda la certificación de resistencia en Windows; CEO no gastará llamadas IA ni creará nuevas auditorías mientras espera.'}
else if(!live){$('actionBanner').className='banner warnb';$('actionBanner').textContent='Gemini no está activo. CEO no está trabajando.'}
"""
    if s.count(banner_anchor) != 1:
        raise RuntimeError(f"work mode banner cert anchor={s.count(banner_anchor)}")
    s = s.replace(banner_anchor, banner_new, 1)

    field_anchor = """else if(s.field_endurance_required&&!s.field_endurance_certified){$('actionBanner').className='banner infob';$('actionBanner').textContent='ℹ Certificación desatendida pendiente: es una prueba posterior de resistencia en Windows. Solo impide declarar el objetivo FINALMENTE completado; no debe detener el trabajo actual.'}
"""
    field_new = """else if(s.field_endurance_required&&!s.field_endurance_certified){$('actionBanner').className='banner infob';$('actionBanner').textContent='ℹ Certificación de resistencia pendiente. El trabajo productivo puede continuar; cuando todo el trabajo quede probado, CEO esperará esta certificación sin consumir proveedor IA.'}
"""
    if s.count(field_anchor) != 1:
        raise RuntimeError(f"work mode field banner anchor={s.count(field_anchor)}")
    s = s.replace(field_anchor, field_new, 1)

    p.write_text(s, encoding="utf-8")


def update_contract() -> None:
    for rel in ("scripts/ceo_stdlib_work_mode.py", "scripts/install_windows_bootstrap.py"):
        p = ROOT / rel
        if p.is_file():
            p.write_text(p.read_text(encoding="utf-8").replace(OLD_VERSION, VERSION), encoding="utf-8")

    cpath = ROOT / "CEO_UPDATE_PACKAGE.json"
    contract = json.loads(cpath.read_text(encoding="utf-8"))
    contract["app_version"] = VERSION
    req = list(contract.get("required_paths") or [])
    new_rel = "ceo_core/deterministic_completion_certifier_v1.py"
    if new_rel not in req:
        req.append(new_rel)
    contract["required_paths"] = sorted(req)
    hashes = dict(contract.get("file_hashes") or {})
    for rel in contract["required_paths"]:
        fp = ROOT / rel
        if not fp.is_file():
            raise RuntimeError(f"missing contract path {rel}")
        hashes[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
    contract["file_hashes"] = hashes
    cpath.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    if not BASE.is_file():
        raise RuntimeError(f"missing base {BASE}")
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)
    with zipfile.ZipFile(BASE) as z:
        z.extractall(ROOT)

    (ROOT / "ceo_core" / "deterministic_completion_certifier_v1.py").write_text(CERTIFIER, encoding="utf-8")
    patch_scheduler()
    patch_autonomous_loop()
    patch_work_mode()
    update_contract()

    print(json.dumps({
        "ok": True,
        "base": OLD_VERSION,
        "version": VERSION,
        "root": str(ROOT),
        "invariants": [
            "provider_independent_completion_certificate",
            "continuity_rounds_not_required_when_durable_evidence_is_sufficient",
            "field_endurance_remains_non_bypassable",
            "work_complete_pending_certification_does_not_spawn_ai_audits",
            "deterministic_certificate_is_hash_bound_to_current_evidence",
            "dev311_and_dev312_fixes_inherited",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
