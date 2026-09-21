from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from .models import ProjectState, Task, TaskStatus
from .task_roles_v2 import TaskRole, task_role


TERMINAL_OK = {
    TaskStatus.COMPLETE,
    TaskStatus.PARTIAL_COMPLETE,
    TaskStatus.COMPLETE_WITH_UNCERTAINTY,
}


@dataclass(slots=True)
class GoalAuditVerdict:
    eligible: bool
    evidence_refs: list[str]
    grounded_refs: list[str]
    gaps: list[str]
    generation: int
    required_generation: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GoalCompletionGate:
    """Evidence gate for autonomous project completion.

    The continuity auditor may *verify* existing work, but it must never create the
    evidence that it is supposed to verify.  This prevents a language-model answer
    containing a magic PASS phrase from circularly completing a broad real-world
    project.
    """

    def _valid_ref_task(self, state: ProjectState, ref: str) -> Task | None:
        task = state.tasks.get(str(ref))
        if task is None:
            return None
        if task.metadata.get("goal_continuity_audit"):
            return None
        if task_role(task, state) == TaskRole.CONTROL:
            return None
        if task.status not in TERMINAL_OK:
            return None
        if not (task.result or "").strip() and not task.metadata.get("artifacts"):
            return None
        return task

    @staticmethod
    def _grounded(task: Task) -> bool:
        md = task.metadata or {}
        if md.get("artifacts"):
            return True
        if md.get("sources") or md.get("source_ids"):
            return True
        if md.get("test_ref") or md.get("implementation_refs"):
            return True
        if md.get("independently_verified") or md.get("verification_application"):
            return True
        if md.get("acceptance_evidence") or md.get("criteria_satisfied"):
            return True
        if md.get("provenance") or md.get("procedure_steps"):
            return True
        return False

    def evidence_candidates(self, state: ProjectState, *, limit: int = 40) -> list[dict[str, Any]]:
        """Expose concrete existing evidence with stable task IDs to the auditor."""
        rows: list[dict[str, Any]] = []
        for task in state.leaf_tasks:
            if self._valid_ref_task(state, task.id) is None:
                continue
            md = task.metadata or {}
            row = {
                "task_id": task.id,
                "title": task.title,
                "status": task.status.value,
                "grounded": self._grounded(task),
                "artifacts": [str(x) for x in md.get("artifacts", [])][:8],
                "verified_artifacts": [str(x) for x in md.get("verified_artifacts", [])][:8],
                "independently_verified": bool(md.get("independently_verified") or md.get("verification_application")),
                "sources": [str(x) for x in (md.get("sources") or md.get("source_ids") or [])][:8],
                "result_excerpt": (task.result or "")[:500],
            }
            rows.append(row)
        rows.sort(
            key=lambda r: (
                bool(r["artifacts"] or r["verified_artifacts"]),
                bool(r["independently_verified"]),
                bool(r["grounded"]),
            ),
            reverse=True,
        )
        return rows[: max(1, int(limit))]

    def auto_evidence_refs(self, state: ProjectState) -> list[str]:
        """Deterministically select real evidence; never manufacture task IDs."""
        candidates = self.evidence_candidates(state, limit=100)
        wanted = max(1, int(state.metadata.get("min_goal_audit_evidence_refs", 1)))
        selected: list[str] = []

        def add(row: dict[str, Any]) -> None:
            tid = str(row.get("task_id") or "")
            if tid and tid not in selected:
                selected.append(tid)

        for row in candidates:
            if row.get("artifacts") or row.get("verified_artifacts"):
                add(row)
                break
        for row in candidates:
            if row.get("independently_verified"):
                add(row)
                break
        for row in candidates:
            if row.get("grounded"):
                add(row)
            if len(selected) >= wanted:
                break
        for row in candidates:
            add(row)
            if len(selected) >= wanted:
                break
        return selected

    @staticmethod
    def _bounded_single_deliverable(state: ProjectState) -> bool:
        """Return True only for a genuinely bounded one-output objective.

        A single report produced by a broad research/migration project must not
        inherit the lightweight completion policy merely because it ends in one
        file. Explicit compact decomposition or an intake contract that says the
        job itself is a single deliverable is required.
        """
        if len(state.goal_deliverables) != 1:
            return False
        profile = dict(state.metadata.get("decomposition_profile") or {})
        if profile.get("mode") == "compact" or profile.get("bounded_single_output") is True:
            return True
        intake = dict(state.metadata.get("real_work_intake_v1") or {})
        kind = str(intake.get("kind") or intake.get("profile") or "").strip().lower()
        if kind in {"single_deliverable", "single_file", "bounded_single_deliverable"}:
            return True
        return False

    def evaluate(self, state: ProjectState, *, evidence_refs: list[str] | None = None) -> GoalAuditVerdict:
        refs: list[str] = []
        for raw in evidence_refs or []:
            ref = str(raw).strip()
            if ref and ref not in refs:
                refs.append(ref)

        valid_tasks = []
        valid_refs = []
        for ref in refs:
            task = self._valid_ref_task(state, ref)
            if task is not None:
                valid_tasks.append(task)
                valid_refs.append(ref)
        grounded_refs = [t.id for t in valid_tasks if self._grounded(t)]

        strict = bool(state.metadata.get("strict_goal_completion_gate", state.metadata.get("real_work_intake_v1") is not None))
        bounded_single = bool(strict and self._bounded_single_deliverable(state))

        # Completion evidence is proportional to the objective. For one bounded
        # file, a concrete artifact plus an independent verification are stronger
        # evidence than repeatedly asking a language model to audit the same work.
        # Broad/multi-output real work keeps the stricter three-ref/continuity gate.
        default_refs = 2 if bounded_single else (3 if strict else 1)
        default_grounded = 2 if bounded_single else (2 if strict else 0)
        default_generations = 0 if bounded_single else (3 if strict else 1)
        min_refs = int(state.metadata.get("min_goal_audit_evidence_refs", default_refs))
        min_grounded = int(state.metadata.get("min_goal_audit_grounded_refs", default_grounded))
        generation = int(state.metadata.get("goal_continuity_generation", 0))
        required_generation = int(state.metadata.get("min_goal_continuity_generations", default_generations))
        gaps: list[str] = []

        if generation < required_generation:
            gaps.append(f"continuity_rounds:{generation}<{required_generation}")
        if len(valid_refs) < min_refs:
            gaps.append(f"valid_evidence_refs:{len(valid_refs)}<{min_refs}")
        if len(grounded_refs) < min_grounded:
            gaps.append(f"grounded_evidence_refs:{len(grounded_refs)}<{min_grounded}")
        artifact_refs = [t.id for t in valid_tasks if (t.metadata.get("artifacts") or t.metadata.get("implementation_refs") or t.metadata.get("test_ref"))]
        verification_refs = [t.id for t in valid_tasks if (t.metadata.get("independently_verified") or t.metadata.get("verification_application"))]
        if strict and not artifact_refs:
            gaps.append("artifact_or_implementation_evidence_missing")
        if strict and not verification_refs:
            gaps.append("independent_verification_evidence_missing")

        # Generic default completion criteria are not objective-specific evidence.
        # A strict real-work project therefore needs either explicit deliverables,
        # a success definition, or a measurable completion contract created earlier.
        has_specific_contract = bool(
            state.goal_deliverables
            or (state.goal_success_definition or "").strip()
            or state.metadata.get("autonomous_completion_contract")
        )
        if strict and not has_specific_contract:
            gaps.append("objective_specific_completion_contract_missing")

        # Criterion evidence is optional at this gate because the audit may map
        # already-grounded evidence refs to generic completion criteria after PASS.
        # Circular evidence from an older audit is never accepted as proof.
        criterion_map = state.metadata.get("completion_evidence") or {}
        for criterion, row in criterion_map.items():
            if isinstance(row, dict) and str(row.get("source") or "") == "goal_continuity_audit":
                gaps.append(f"circular_criterion_evidence:{str(criterion)[:80]}")

        deliverables = state.metadata.get("deliverable_evidence") or {}
        for deliverable in state.goal_deliverables:
            row = deliverables.get(deliverable)
            if not row:
                gaps.append(f"deliverable_unproven:{deliverable[:80]}")
                continue
            if isinstance(row, dict):
                task_id = str(row.get("task_id") or "")
                if self._valid_ref_task(state, task_id) is None:
                    gaps.append(f"deliverable_not_independent:{deliverable[:80]}")

        if bool(state.metadata.get("requires_field_endurance_certification", False)) and not bool(state.metadata.get("field_endurance_certified", False)):
            gaps.append("field_endurance_certification_required")

        return GoalAuditVerdict(
            eligible=not gaps,
            evidence_refs=valid_refs,
            grounded_refs=grounded_refs,
            gaps=gaps,
            generation=generation,
            required_generation=required_generation,
        )

    def migrate_invalid_legacy_pass(self, state: ProjectState) -> dict[str, Any]:
        """Reopen completion states produced by the old circular audit logic."""
        if not state.metadata.get("goal_audit_passed"):
            return {"changed": False, "reason": "no_prior_pass"}
        evidence = state.metadata.get("goal_audit_evidence") or {}
        refs = list(evidence.get("evidence_refs") or []) if isinstance(evidence, dict) else []
        verdict = self.evaluate(state, evidence_refs=refs)
        if verdict.eligible:
            return {"changed": False, "reason": "grounded_pass", "verdict": verdict.to_dict()}

        state.metadata["goal_audit_passed"] = False
        state.completed_at = None
        state.metadata["goal_audit_invalidated"] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "reason": "legacy_or_ungrounded_completion_pass",
            "gaps": list(verdict.gaps),
        }
        state.metadata["last_goal_audit_rejection"] = verdict.to_dict()

        # Remove only circular criterion evidence created by the old audit. Keep all
        # genuine evidence rows untouched.
        criterion_map = state.metadata.get("completion_evidence") or {}
        cleaned = {}
        for criterion, row in criterion_map.items():
            if isinstance(row, dict) and str(row.get("source") or "") == "goal_continuity_audit":
                continue
            cleaned[criterion] = row
        state.metadata["completion_evidence"] = cleaned

        for task in state.tasks.values():
            if task.metadata.get("goal_continuity_audit") and task.status == TaskStatus.COMPLETE:
                if "CEO_GOAL_AUDIT: PASS" in (task.result or ""):
                    task.status = TaskStatus.SUPERSEDED
                    task.metadata["completion_pass_invalidated"] = True
                    task.metadata["completion_pass_gaps"] = list(verdict.gaps)

        return {"changed": True, "reason": "invalid_pass_reopened", "verdict": verdict.to_dict()}
