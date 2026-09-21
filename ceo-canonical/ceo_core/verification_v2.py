from __future__ import annotations

from dataclasses import dataclass
import json
import re

from .models import ProjectState, Task, TaskStatus
from .quality import AdversarialVerifier


_VERIFY_RE = re.compile(r"<CEO_VERIFY>\s*(\{.*?\})\s*</CEO_VERIFY>", re.IGNORECASE | re.DOTALL)


@dataclass(slots=True)
class VerificationPlan:
    independent_checks: int
    adversarial: bool
    source_independence_required: bool
    reason: str


@dataclass(slots=True)
class VerificationVerdict:
    verdict: str
    confidence: float | None = None
    reason: str = ""


class LayeredVerificationEngine:
    """Allocates verification effort and feeds explicit verifier verdicts back.

    Verification workers are independent tasks, but a verifier must not merely
    finish successfully: an explicit FAIL is now allowed to invalidate the target
    and an explicit UNCERTAIN verdict lowers the target's completion certainty.
    """

    def __init__(self) -> None:
        self.adversarial = AdversarialVerifier()

    def plan(self, state: ProjectState, task: Task) -> VerificationPlan:
        importance = float(task.metadata.get("importance", task.priority / 100))
        uncertainty = 1.0 - float(task.confidence if task.confidence is not None else .5)
        verification = state.verification_percent / 100
        risk = min(1.0, importance * .45 + uncertainty * .35 + verification * .35)
        checks = 0 if risk < .35 else 1 if risk < .72 else 2
        adversarial = risk >= .82 or bool(task.metadata.get("critical_claim"))
        return VerificationPlan(checks, adversarial, risk >= .55, f"risk={risk:.3f}")

    @staticmethod
    def verifier_instruction() -> str:
        return (
            "Return an independent verdict and finish with exactly one machine-readable marker: "
            '<CEO_VERIFY>{"verdict":"pass|fail|uncertain","confidence":0.0,"reason":"short reason"}</CEO_VERIFY>. '
            "Use fail only when the target conclusion/result is materially wrong; use uncertain when evidence is insufficient."
        )

    def build_tasks(self, state: ProjectState, target: Task) -> list[Task]:
        plan = self.plan(state, target)
        out: list[Task] = []
        for i in range(plan.independent_checks):
            out.append(Task(
                title=f"Independent verification {i + 1}: {target.title}",
                description=(
                    "Verify the target result independently. Prefer different primary sources and explicitly test unsupported claims. "
                    + self.verifier_instruction()
                ),
                parent_id=target.parent_id,
                depth=target.depth,
                priority=min(100, target.priority + 10 + i),
                dependencies=[target.id],
                required_capabilities=list(target.required_capabilities),
                acceptance_criteria=[
                    "Independent verdict",
                    "Source independence assessed",
                    "Unsupported claims listed",
                    "CEO_VERIFY marker returned",
                ],
                metadata={
                    "verification_task": True,
                    "verifies": target.id,
                    "verification_layer": "independent",
                    "avoid_providers": [target.provider_name] if target.provider_name else [],
                },
            ))
        if plan.adversarial:
            task = self.adversarial.build_task(target)
            task.description += " " + self.verifier_instruction()
            task.acceptance_criteria.append("CEO_VERIFY marker returned")
            out.append(task)
        return out

    def parse_verdict(self, text: str | None) -> VerificationVerdict | None:
        match = _VERIFY_RE.search(text or "")
        if not match:
            return None
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        verdict = str(payload.get("verdict", "")).strip().lower()
        if verdict not in {"pass", "fail", "uncertain"}:
            return None
        confidence = payload.get("confidence")
        try:
            confidence = None if confidence is None else max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = None
        return VerificationVerdict(verdict, confidence, str(payload.get("reason", ""))[:1000])

    def apply_result(self, state: ProjectState, verification_task: Task) -> dict:
        if not verification_task.metadata.get("verification_task"):
            return {"applied": False, "reason": "not_verification_task"}
        target_id = str(verification_task.metadata.get("verifies") or "")
        target = state.tasks.get(target_id)
        if not target:
            return {"applied": False, "reason": "target_missing"}

        parsed = self.parse_verdict(verification_task.result)
        strict = bool(state.metadata.get("strict_verification_gate", False))
        if parsed is None:
            record = {
                "task_id": verification_task.id,
                "verdict": "unclassified",
                "confidence": None,
                "reason": "missing_or_invalid_CEO_VERIFY",
            }
            if strict:
                target.status = TaskStatus.NEEDS_REVIEW
                target.metadata["verification_failed"] = record
        else:
            record = {
                "task_id": verification_task.id,
                "verdict": parsed.verdict,
                "confidence": parsed.confidence,
                "reason": parsed.reason,
            }
            if parsed.verdict == "fail":
                target.status = TaskStatus.NEEDS_REVIEW
                target.metadata["verification_failed"] = record
                target.metadata["verified"] = False
            elif parsed.verdict == "uncertain":
                if target.status == TaskStatus.COMPLETE:
                    target.status = TaskStatus.COMPLETE_WITH_UNCERTAINTY
                target.metadata["verified"] = False
                target.metadata["verification_uncertain"] = record
            elif parsed.verdict == "pass":
                target.metadata.pop("verification_failed", None)

        records = target.metadata.setdefault("verification_records", [])
        # Idempotent replacement if the same verifier task is reloaded/replayed.
        records[:] = [r for r in records if r.get("task_id") != verification_task.id]
        records.append(record)
        del records[:-50]

        scheduled = [str(x) for x in target.metadata.get("verification_scheduled", [])]
        relevant = [r for r in records if not scheduled or r.get("task_id") in scheduled]
        expected = len(scheduled) if scheduled else 1
        explicit_passes = sum(r.get("verdict") == "pass" for r in relevant)
        explicit_fails = sum(r.get("verdict") == "fail" for r in relevant)
        unclassified = sum(r.get("verdict") == "unclassified" for r in relevant)
        target.metadata["verification_summary"] = {
            "expected": expected,
            "recorded": len(relevant),
            "passes": explicit_passes,
            "fails": explicit_fails,
            "unclassified": unclassified,
        }
        if explicit_fails == 0 and explicit_passes >= expected and expected > 0:
            target.metadata["verified"] = True
            target.metadata["verification_depth"] = 1.0
        return {"applied": True, **record, "target_id": target.id}
