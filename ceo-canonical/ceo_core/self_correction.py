from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .models import ProjectState, Task, TaskStatus
from .quality_gate import QualityGateVerdict


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unsafe(task: Task) -> bool:
    md = task.metadata
    return bool(md.get("external_action") or md.get("irreversible") or md.get("destructive") or md.get("spending") or md.get("purchase") or md.get("public_release") or md.get("git_network_action"))


class SelfCorrectionEngine:
    """Turns deterministic quality/failure findings into bounded autonomous repairs."""

    def recover_quality_failure(self, state: ProjectState, task: Task, verdict: QualityGateVerdict) -> dict[str, Any]:
        history = task.metadata.setdefault("self_correction_history", [])
        same_signature = sum(1 for row in history if row.get("signature") == verdict.signature)
        max_inline = max(1, int(state.metadata.get("max_inline_quality_corrections", 2)))
        generation = int(task.metadata.get("repair_generation", 0) or 0)
        max_generations = max(1, int(state.metadata.get("max_quality_repair_generations", 2)))
        lineage_root = str(task.metadata.get("quality_repair_root_id") or task.id)
        task.metadata["quality_repair_root_id"] = lineage_root
        event: dict[str, Any] = {
            "ts": _utcnow(),
            "task_id": task.id,
            "signature": verdict.signature,
            "reasons": list(verdict.reasons),
            "same_signature_seen": same_signature,
        }

        if _unsafe(task):
            task.status = TaskStatus.NEEDS_REVIEW
            task.metadata["explicit_human_gate"] = True
            task.metadata["human_gate_reason"] = "quality_gate_rejected_external_or_irreversible_result"
            event["action"] = "human_gate"
            self._record(state, task, event)
            return event

        if same_signature < max_inline and task.attempts < task.max_attempts:
            task.status = TaskStatus.RETRY
            task.metadata["retry_after_ts"] = 0
            task.metadata["quality_correction_pending"] = True
            task.metadata["next_instruction"] = self._repair_instruction(task, verdict)
            event["action"] = "inline_retry"
            self._record(state, task, event)
            return event

        # Bound the entire repair lineage, not only retries of one task id.
        # 1.5.82 changed the quality signature when a replacement received a new
        # task id, allowing an unbounded Repair -> Repair -> Repair chain.
        if generation >= max_generations:
            task.status = TaskStatus.FAILED
            task.metadata["quality_repair_exhausted"] = True
            task.metadata["quality_repair_generation"] = generation
            task.metadata["quality_repair_root_id"] = lineage_root
            task.result = (
                (task.result or "")
                + " Quality repair lineage exhausted; handing control to autonomous replanning."
            ).strip()
            event["action"] = "bounded_quality_failure"
            event["repair_generation"] = generation
            event["max_quality_repair_generations"] = max_generations
            self._record(state, task, event)
            return event

        replacement = self._spawn_replacement(state, task, verdict)
        replacement.metadata["quality_repair_root_id"] = lineage_root
        replacement.metadata["quality_repair_generation"] = generation + 1
        event["action"] = "replacement_task"
        event["replacement_task_id"] = replacement.id
        event["repair_generation"] = generation + 1
        self._record(state, task, event)
        return event

    def recover_terminal_failure(self, state: ProjectState, task: Task, *, reason: str) -> Task | None:
        if _unsafe(task) or task.metadata.get("control_plane_atomic"):
            return None
        max_replacements = max(1, int(state.metadata.get("max_failure_replacements", 2)))
        generation = int(task.metadata.get("repair_generation", 0) or 0)
        if generation >= max_replacements:
            return None
        pseudo = QualityGateVerdict(False, 0.0, 1.0, [reason], "retry_or_repair", True, f"terminal-{generation}")
        return self._spawn_replacement(state, task, pseudo)

    def _spawn_replacement(self, state: ProjectState, task: Task, verdict: QualityGateVerdict) -> Task:
        generation = int(task.metadata.get("repair_generation", 0) or 0) + 1
        md = deepcopy(task.metadata)
        for key in (
            "dispatch_token", "dispatch_session_id", "dispatch_batch_id", "dispatch_persisted_at",
            "quality_gate", "quality_correction_pending", "provider_stage", "provider_stage_ts",
            "last_provider_error", "retry_after_ts", "empty_provider_response",
            "self_correction_history",
        ):
            md.pop(key, None)
        md["self_correction_replacement_of"] = task.id
        md["repair_generation"] = generation
        md["quality_repair_reasons"] = list(verdict.reasons)
        md["avoid_providers"] = list(dict.fromkeys([*(md.get("avoid_providers") or []), *([task.provider_name] if task.provider_name else [])]))

        replacement = Task(
            title=f"Repair: {task.title}",
            description=(
                f"Re-execute the intended work of task {task.id}, correcting these verified deficiencies: "
                + "; ".join(verdict.reasons)
                + f". Original description: {task.description}"
            ),
            parent_id=task.parent_id,
            depth=task.depth,
            priority=min(100, int(task.priority) + 8),
            dependencies=list(task.dependencies),
            estimated_seconds=max(float(task.estimated_seconds or 0.1), 0.1),
            required_capabilities=list(task.required_capabilities),
            acceptance_criteria=list(task.acceptance_criteria),
            max_attempts=max(2, int(task.max_attempts)),
            cost_estimate=float(task.cost_estimate or 0.0),
            metadata=md,
        )
        state.tasks[replacement.id] = replacement
        if replacement.parent_id and replacement.parent_id in state.tasks:
            parent = state.tasks[replacement.parent_id]
            if replacement.id not in parent.children:
                parent.children.append(replacement.id)
        elif replacement.id not in state.root_task_ids:
            state.root_task_ids.append(replacement.id)

        task.status = TaskStatus.SUPERSEDED
        task.metadata["superseded_reason"] = "automatic_self_correction_replacement"
        task.metadata["superseded_by"] = replacement.id
        return replacement

    @staticmethod
    def _repair_instruction(task: Task, verdict: QualityGateVerdict) -> str:
        criteria = "; ".join(task.acceptance_criteria) if task.acceptance_criteria else "the original task contract"
        return (
            "The deterministic CEO quality gate rejected the previous result. Correct it autonomously. "
            f"Verified deficiencies: {', '.join(verdict.reasons)}. "
            f"Acceptance target: {criteria}. Do not claim completion until the deficiencies are actually resolved."
        )

    def _record(self, state: ProjectState, task: Task, event: dict[str, Any]) -> None:
        history = task.metadata.setdefault("self_correction_history", [])
        history.append(dict(event))
        del history[:-20]
        rows = state.metadata.setdefault("self_correction_events", [])
        rows.append(dict(event))
        del rows[:-300]
