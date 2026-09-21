from __future__ import annotations

from .models import ProjectState, TaskStatus


class FinalReportBuilder:
    """Builds the project handoff: outcome, evidence, artifacts and unresolved work."""

    def build(self, state: ProjectState) -> str:
        terminal = {TaskStatus.COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY, TaskStatus.PARTIAL_COMPLETE}
        completed = [t for t in state.leaf_tasks if t.status in terminal]
        unresolved = [t for t in state.leaf_tasks if t.status not in terminal | {TaskStatus.SUPERSEDED}]
        completion = state.metadata.get("completion_assessment", {})
        artifacts: list[str] = []
        for task in state.leaf_tasks:
            for artifact in task.metadata.get("artifacts", []) or []:
                if artifact not in artifacts:
                    artifacts.append(str(artifact))
        lines = [
            "# CEO de IAs — Final Project Handoff\n",
            f"## Goal\n{state.goal}\n",
            f"## Definition of success\n{state.goal_success_definition or state.goal_definition or state.goal}\n",
            "## Status",
            f"- Progress: {state.progress}%",
            f"- Completion outcome: {completion.get('outcome', 'not yet assessed')}",
            f"- Completion confidence: {completion.get('confidence', '—')}",
            f"- Human interventions avoided: {state.human_interventions_avoided}",
            f"- Human interventions required: {state.human_interventions_required}",
            f"- API cost recorded: {state.metadata.get('cost_spent', 0.0)}",
        ]
        if state.goal_deliverables:
            lines.append("\n## Requested deliverables")
            lines.extend(f"- {x}" for x in state.goal_deliverables)
        if state.completion_criteria:
            evidence = state.metadata.get("completion_evidence", {})
            lines.append("\n## Completion criteria")
            for criterion in state.completion_criteria:
                mark = "✓" if evidence.get(criterion, completion.get("complete", False)) else "?"
                lines.append(f"- {mark} {criterion}")
        lines.append("\n## Completed work")
        if not completed:
            lines.append("- No completed work recorded.")
        for task in completed[:300]:
            status = task.status.value
            q = f" · quality {task.quality_score:.2f}" if task.quality_score is not None else ""
            lines.append(f"- **{task.title}** ({status}{q}) — {(task.result or '')[:900]}")
        if artifacts:
            lines.append("\n## Artifacts")
            lines.extend(f"- {item}" for item in artifacts[:300])
        if unresolved:
            lines.append("\n## Unresolved / follow-up")
            for task in unresolved[:150]:
                err = task.metadata.get("last_provider_error")
                suffix = f" — {err}" if err else ""
                lines.append(f"- {task.title}: {task.status.value}{suffix}")
        blockers = completion.get("blockers") or []
        if blockers:
            lines.append("\n## Completion blockers")
            lines.extend(f"- {x}" for x in blockers[:100])
        lines.append("\n## Provider summary")
        for provider, stats in (state.metadata.get("provider_stats") or {}).items():
            lines.append(f"- {provider}: {stats}")
        lines.append("\n## Audit note\nThis report reflects recorded execution evidence. Missing checks or external validations are not represented as completed.")
        return "\n".join(lines)
