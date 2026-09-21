from __future__ import annotations

from .models import ProjectState, Task, TaskStatus
from .blocked_safe_state_v1 import preserve_blocked_safe


class TaskDecomposer:
    """Deterministic baseline decomposer.

    This is intentionally provider-agnostic. A real LLM planner can replace/augment
    `plan()` without changing the scheduler, state model, or UI contract.
    """

    DEFAULT_PHASES = [
        ("Clarify & lock goal", "Confirm objective, constraints and completion criteria."),
        ("Research & discovery", "Collect the information and alternatives needed to execute the goal."),
        ("Execution", "Produce the substantive work required by the goal."),
        ("Verification", "Independently check outputs, contradictions, failures and missing work."),
        ("Integration", "Combine verified outputs into a coherent final result."),
        ("Final audit", "Check completion criteria and create any corrective tasks required."),
    ]

    COMPACT_PHASES = [
        ("Clarify & lock goal", "Lock the requested output and completion condition."),
        ("Execution", "Produce the requested deliverable directly."),
        ("Final audit", "Verify the deliverable exists and satisfies the locked objective."),
    ]

    @staticmethod
    def _complexity_profile(goal: str) -> dict:
        text = " ".join((goal or "").strip().split())
        low = text.lower()

        complex_terms = (
            "research", "investigate", "compare", "audit", "analyse", "analyze",
            "multiple", "several", " all ", "systematic", "review ", "repository",
            "implement", "refactor", "deploy", "integrate", "across ", "pipeline",
            "database", "architecture", "migration", "benchmark", "experiment",
            "investiga", "compar", "audita", "sistemát", "sistemat", "repositorio",
            "implementa", "refactoriza", "despliega", "integra", "base de datos",
            "arquitectura", "migración", "migracion", "experimento", "múltiples",
            "multiples", "varios archivos", "todos los archivos",
        )
        simple_output_terms = (
            ".md", ".txt", ".json", ".csv", ".html",
            "short note", "status note", "brief note", "one sentence",
            "single file", "one file",
        )
        conjunctions = sum(low.count(token) for token in (" and ", ";", "\n-", "\n*"))
        complex_score = sum(1 for token in complex_terms if token in low)
        simple_score = sum(1 for token in simple_output_terms if token in low)

        # Stabilization invariant: verbosity is not complexity. A detailed
        # specification for exactly one explicit output file remains a bounded
        # single-deliverable goal regardless of character count. Actual complexity
        # terms still force the full decomposition.
        file_hits = sum(low.count(ext) for ext in (".md", ".txt", ".json", ".csv", ".html"))
        single_explicit_file = file_hits == 1
        bounded_single_output = bool(
            single_explicit_file
            and simple_score >= 1
            and complex_score == 0
        )
        compact = bool(
            bounded_single_output
            or (
                len(text) <= 260
                and complex_score == 0
                and conjunctions <= 2
                and simple_score >= 1
            )
        )
        return {
            "mode": "compact" if compact else "full",
            "characters": len(text),
            "complex_score": complex_score,
            "simple_output_score": simple_score,
            "conjunctions": conjunctions,
            "single_explicit_file": single_explicit_file,
            "bounded_single_output": bounded_single_output,
            "file_hits": file_hits,
        }

    def plan(self, goal: str) -> ProjectState:
        state = ProjectState(
            goal=goal.strip(),
            goal_definition=goal.strip(),
            completion_criteria=[
                "All required work units are completed or explicitly superseded.",
                "Verification phase reports no unresolved critical failure.",
                "Integrated deliverable satisfies the locked goal definition.",
            ],
        )

        profile = self._complexity_profile(goal)
        state.metadata["decomposition_profile"] = profile
        phases = self.COMPACT_PHASES if profile["mode"] == "compact" else self.DEFAULT_PHASES

        previous_root: str | None = None
        for phase_idx, (title, description) in enumerate(phases):
            root = Task(
                title=title,
                description=description,
                depth=0,
                priority=100 - phase_idx * 10,
                dependencies=[previous_root] if previous_root else [],
            )
            state.tasks[root.id] = root
            state.root_task_ids.append(root.id)

            # Each phase contains small atomic work units. The first implementation
            # demonstrates hierarchy + dependency scheduling; LLM decomposition will
            # later generate these dynamically.
            child_count = 1 if profile["mode"] == "compact" else (3 if title not in {"Execution", "Research & discovery"} else 6)
            last_child: str | None = None
            for i in range(child_count):
                deps = []
                if previous_root:
                    deps.append(previous_root)
                # Within verification/final audit keep some sequential checks to
                # exercise blocked dependencies; most work remains parallel.
                if title in {"Verification", "Final audit"} and last_child:
                    deps.append(last_child)
                child = Task(
                    title=f"{title} · work unit {i + 1}",
                    description=f"Atomic work unit {i + 1} for: {description}",
                    parent_id=root.id,
                    depth=1,
                    priority=root.priority - i,
                    dependencies=deps,
                    estimated_seconds=0.7 + (i % 3) * 0.35,
                    required_capabilities=["general"],
                    metadata={
                        "preferred_kind": "local" if title == "Clarify & lock goal" else "api",
                        "local_fallback_kind": "goal_lock" if title == "Clarify & lock goal" else None,
                        "task_type": title.lower().replace(" & ", "_").replace(" ", "_"),
                    },
                )
                state.tasks[child.id] = child
                root.children.append(child.id)
                last_child = child.id

            previous_root = root.id

        self.refresh_readiness(state)
        return state

    def refresh_readiness(self, state: ProjectState) -> None:
        # A root/group task completes when all children complete. Root tasks are not
        # executed by workers; only leaves are.
        for root_id in state.root_task_ids:
            root = state.tasks[root_id]
            if root.children and all(state.tasks[c].status in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY} for c in root.children):
                root.status = TaskStatus.COMPLETE
            elif any(state.tasks[c].status == TaskStatus.RUNNING for c in root.children):
                root.status = TaskStatus.RUNNING

        for task in state.leaf_tasks:
            if preserve_blocked_safe(task, source="decomposer_refresh"):
                continue
            if task.status not in {TaskStatus.WAITING, TaskStatus.BLOCKED, TaskStatus.RETRY}:
                continue
            deps_done = all(
                dep in state.tasks and state.tasks[dep].status in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}
                for dep in task.dependencies
            )
            task.status = TaskStatus.READY if deps_done else TaskStatus.BLOCKED
