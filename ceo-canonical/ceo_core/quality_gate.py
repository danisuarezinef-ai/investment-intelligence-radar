from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any

from .models import ProjectState, Task, TaskStatus
from .task_roles_v2 import is_productive


_TERMINAL_SUCCESS = {
    TaskStatus.COMPLETE,
    TaskStatus.PARTIAL_COMPLETE,
    TaskStatus.COMPLETE_WITH_UNCERTAINTY,
}


def _has_durable_evidence(task: Task) -> bool:
    md = task.metadata
    return bool(
        md.get("artifacts")
        or md.get("sources")
        or md.get("test_ref")
        or md.get("evidence_refs")
        or md.get("verification_application")
        or md.get("implementation_refs")
    )


def _unsafe_to_repeat(task: Task) -> bool:
    md = task.metadata
    return bool(
        md.get("external_action")
        or md.get("irreversible")
        or md.get("destructive")
        or md.get("spending")
        or md.get("purchase")
        or md.get("public_release")
        or md.get("git_network_action")
    )


@dataclass(slots=True)
class QualityGateVerdict:
    accepted: bool
    score: float
    threshold: float
    reasons: list[str]
    action: str = "accept"
    retry_safe: bool = True
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AutomaticQualityGate:
    """Deterministic last-mile gate before a task result becomes durable knowledge.

    It deliberately does not attempt semantic truth checking. It checks the things the
    runtime can establish locally: usable result/evidence, explicit task contract flags,
    quality threshold, required artifacts/tests and completion consistency. Semantic
    verification remains the responsibility of independent verification tasks/providers.
    """

    def evaluate(self, state: ProjectState, task: Task, *, quality: float | None = None) -> QualityGateVerdict:
        reasons: list[str] = []
        md = task.metadata
        threshold = float(md.get("quality_gate_threshold", md.get("quality_threshold", 0.55)))
        measured = float(quality if quality is not None else (task.quality_score if task.quality_score is not None else 0.0))

        result_text = (task.result or "").strip()
        if not result_text and not md.get("artifacts"):
            reasons.append("no_usable_result")
        if result_text.upper().startswith("ERROR:"):
            reasons.append("error_result")
        if md.get("requires_evidence") and not _has_durable_evidence(task):
            reasons.append("required_evidence_missing")
        if md.get("requires_artifact") and not md.get("artifacts"):
            reasons.append("required_artifact_missing")
        if md.get("requires_test") and not (md.get("test_ref") or md.get("tests_passed")):
            reasons.append("required_test_missing")
        if measured < threshold:
            reasons.append("quality_below_threshold")
        if task.acceptance_criteria and md.get("acceptance_criteria_checked") is False:
            reasons.append("acceptance_criteria_explicitly_unmet")
        if md.get("verification_required") and not (md.get("verified") or md.get("verification_application")):
            reasons.append("verification_required_missing")
        if md.get("known_contradiction") and not md.get("conflict_resolved"):
            reasons.append("known_contradiction_unresolved")

        # Internal control/verification work has a specialized deterministic gate.
        # Do not apply a domain-quality threshold to protocol payloads, while still
        # enforcing usable result, explicit evidence/test requirements and safety.
        if not is_productive(task, state):
            reasons = [r for r in reasons if r not in {"quality_below_threshold"}]

        accepted = not reasons
        retry_safe = not _unsafe_to_repeat(task)
        if accepted:
            action = "accept"
        elif retry_safe:
            action = "retry_or_repair"
        else:
            action = "human_gate"

        signature_input = "|".join(sorted(reasons)) + f"|{task.id}|{threshold:.4f}"
        signature = sha256(signature_input.encode("utf-8")).hexdigest()[:20]
        verdict = QualityGateVerdict(
            accepted=accepted,
            score=round(measured, 4),
            threshold=round(threshold, 4),
            reasons=reasons,
            action=action,
            retry_safe=retry_safe,
            signature=signature,
        )
        task.metadata["quality_gate"] = verdict.to_dict()
        ledger = state.metadata.setdefault("quality_gate_history", [])
        ledger.append({"task_id": task.id, **verdict.to_dict()})
        del ledger[:-300]
        return verdict

    @staticmethod
    def should_gate(task: Task) -> bool:
        return task.status in _TERMINAL_SUCCESS
