from __future__ import annotations

from ceo_core.contracts import ControllerAction, ControllerDecision, WorkerResult
from ceo_core.models import Decision, ProjectState, Task, TaskStatus
from ceo_core.notifications import NotificationHub
from ceo_core.result_protocol import extract_directive, strip_directive
from hashlib import sha256
from ceo_core.autonomy import AutonomyEngine
from ceo_core.preferences import PreferenceLearningEngine
from ceo_core.continuity_policy import is_goal_audit_lineage, protected_human_gate


class ConversationController:
    """Turns each AI response into an explicit autonomous next action."""

    def __init__(self, max_dynamic_tasks: int = 10_000, notifications: NotificationHub | None = None, max_turns: int = 24, stagnation_limit: int = 3, decision_learning=None) -> None:
        self.max_dynamic_tasks = max_dynamic_tasks
        self.notifications = notifications or NotificationHub()
        self.max_turns = max_turns
        self.stagnation_limit = stagnation_limit
        self.decision_learning = decision_learning
        self.autonomy_engine = AutonomyEngine()
        self.preference_engine = PreferenceLearningEngine()

    def decide(self, state: ProjectState, task: Task, result: WorkerResult) -> ControllerDecision:
        if not result.success:
            return ControllerDecision(action=ControllerAction.RETRY, reason=result.error or "Worker reported failure.")
        if task.conversation_turns >= self.max_turns:
            return ControllerDecision(action=ControllerAction.REVIEW, reason="Conversation turn limit reached; independent review required.")
        digest = sha256(strip_directive(result.text).strip().encode()).hexdigest()
        prior = task.metadata.get("last_result_digest")
        stagnant = int(task.metadata.get("stagnant_turns", 0)) + 1 if prior == digest else 0
        task.metadata["pending_result_digest"] = digest
        task.metadata["pending_stagnant_turns"] = stagnant
        if stagnant >= self.stagnation_limit:
            return ControllerDecision(action=ControllerAction.REVIEW, reason="Worker appears stuck/repetitive; independent review required.")

        directive = extract_directive(result.text)
        if directive:
            mapping = {
                "complete": ControllerAction.COMPLETE,
                "continue": ControllerAction.CONTINUE,
                "correct": ControllerAction.CORRECT,
                "deepen": ControllerAction.DEEPEN,
                "spawn": ControllerAction.SPAWN,
                "review": ControllerAction.REVIEW,
                "escalate": ControllerAction.ESCALATE,
                "retry": ControllerAction.RETRY,
            }
            action = mapping[directive.status]
            if not state.autonomy_enabled and action in {
                ControllerAction.CONTINUE,
                ControllerAction.CORRECT,
                ControllerAction.DEEPEN,
                ControllerAction.SPAWN,
            }:
                return ControllerDecision(
                    action=ControllerAction.ESCALATE,
                    reason=directive.reason or f"Autonomy is OFF; CEO would normally {action.value}.",
                    confidence=directive.confidence,
                    requires_user=True,
                    metadata={
                        "decision_title": f"Continue: {task.title}",
                        "decision_options": ["Continue", "Keep paused"],
                        "recommendation": "Continue",
                        "timeout_seconds": directive.timeout_seconds,
                    },
                )
            return ControllerDecision(
                action=action,
                reason=directive.reason,
                confidence=directive.confidence,
                next_instruction=directive.next_instruction,
                spawned_tasks=list(directive.followups),
                requires_user=directive.requires_user,
                metadata={
                    "decision_title": directive.decision_title,
                    "decision_options": directive.decision_options,
                    "recommendation": directive.recommendation,
                    "timeout_seconds": directive.timeout_seconds,
                },
            )

        suggestions = [s.strip() for s in result.suggested_followups if s.strip()]
        if suggestions:
            return ControllerDecision(
                action=ControllerAction.SPAWN,
                reason="Worker completed the turn and identified follow-up work.",
                spawned_tasks=suggestions,
            )
        return ControllerDecision(action=ControllerAction.COMPLETE, reason="No control footer; conservative completion fallback.")

    def apply(self, state: ProjectState, task: Task, result: WorkerResult, decision: ControllerDecision) -> list[Task]:
        task.result = strip_directive(result.text)
        if "pending_result_digest" in task.metadata:
            task.metadata["last_result_digest"] = task.metadata.pop("pending_result_digest")
            task.metadata["stagnant_turns"] = task.metadata.pop("pending_stagnant_turns", 0)
        if result.conversation_id:
            task.conversation_id = result.conversation_id
        task.provider_name = result.provider
        if result.artifacts:
            task.metadata.setdefault("artifacts", []).extend(a for a in result.artifacts if a not in task.metadata.setdefault("artifacts", []))
        if result.metadata.get("sources"):
            task.metadata.setdefault("sources", []).extend(s for s in result.metadata.get("sources", []) if s not in task.metadata.setdefault("sources", []))
        task.conversation_turns += 1
        action = decision.action

        if action == ControllerAction.COMPLETE:
            task.status = TaskStatus.COMPLETE
            return []
        if action == ControllerAction.SPAWN:
            task.status = TaskStatus.COMPLETE
            state.human_interventions_avoided += 1
            return self._spawn(state, task, decision.spawned_tasks)
        if action in {ControllerAction.CONTINUE, ControllerAction.CORRECT, ControllerAction.DEEPEN}:
            task.status = TaskStatus.READY
            if decision.next_instruction:
                task.metadata["next_instruction"] = decision.next_instruction
            task.metadata["controller_action"] = action.value
            state.human_interventions_avoided += 1
            return []
        if action == ControllerAction.REVIEW:
            if state.autonomy_enabled and is_goal_audit_lineage(state, task) and not protected_human_gate(task, decision.metadata):
                task.status = TaskStatus.RETRY
                task.max_attempts = max(int(task.max_attempts), int(task.attempts) + 2)
                task.metadata["internal_continuity_review_suppressed"] = True
                task.metadata["next_instruction"] = (
                    "Internal continuity audit: continue autonomously and create concrete follow-up work if the goal is incomplete. "
                    "Do not request human review for ordinary continuity."
                )
                state.human_interventions_avoided += 1
                return []
            task.status = TaskStatus.NEEDS_REVIEW
            return []
        if action == ControllerAction.ESCALATE:
            if state.autonomy_enabled and is_goal_audit_lineage(state, task) and not protected_human_gate(task, decision.metadata):
                task.status = TaskStatus.RETRY
                task.max_attempts = max(int(task.max_attempts), int(task.attempts) + 2)
                task.metadata["internal_continuity_escalation_suppressed"] = True
                task.metadata.pop("requires_user", None)
                task.metadata["next_instruction"] = (
                    "Internal continuity audit: continue autonomously. Escalate only a genuine protected human-only action "
                    "such as spending, destructive/external effects, authentication, or remote promotion."
                )
                state.human_interventions_avoided += 1
                return []
            task.status = TaskStatus.NEEDS_REVIEW
            task.metadata["requires_user"] = decision.requires_user
            if decision.requires_user:
                options = [str(v) for v in decision.metadata.get("decision_options") or []]
                if not options:
                    options = ["Proceed with CEO recommendation", "Keep task paused"]
                title = decision.metadata.get("decision_title") or f"Decision: {task.title}"
                recommendation = decision.metadata.get("recommendation") or options[0]
                if self.decision_learning:
                    learned = self.decision_learning.preference(title)
                    if learned in options:
                        recommendation = learned
                preference, preference_confidence = self.preference_engine.annotate_recommendation(state, title, options, recommendation)
                if preference in options and preference_confidence >= .7:
                    recommendation = preference
                decision_metadata = dict(decision.metadata)
                decision_metadata.update({
                    "preference_confidence": preference_confidence,
                    "source_task_id": task.id,
                    "source_internal_continuity": is_goal_audit_lineage(state, task),
                    "external_effect": bool(task.metadata.get("external_effect") or task.metadata.get("external_action")),
                    "irreversibility": float(task.metadata.get("irreversibility") or (1.0 if task.metadata.get("irreversible") else 0.0)),
                    "cost": float(task.cost_estimate or 0.0),
                })
                d = Decision(
                    title=title,
                    description=decision.reason or "CEO needs a decision to continue this branch.",
                    options=options,
                    recommendation=recommendation,
                    confidence=decision.confidence,
                    timeout_seconds=int(decision.metadata.get("timeout_seconds") or 60),
                    metadata=decision_metadata,
                )
                autonomy = self.autonomy_engine.annotate(state, d)
                if autonomy.auto_resolve and recommendation:
                    d.timeout_seconds = min(d.timeout_seconds, max(1, autonomy.timeout_seconds))
                state.decisions[d.id] = d
                task.metadata["decision_id"] = d.id
                if state.notifications_enabled:
                    self.notifications.emit(
                        state,
                        title=d.title,
                        body=f"CEO recommends: {recommendation}. Auto-resolution in {d.timeout_seconds}s.",
                        severity="decision",
                        data={"decision_id": d.id},
                    )
            return []
        if action == ControllerAction.RETRY:
            task.status = TaskStatus.RETRY if task.attempts < task.max_attempts else TaskStatus.FAILED
            if task.status == TaskStatus.RETRY:
                state.human_interventions_avoided += 1
            return []
        raise RuntimeError(f"Unsupported controller action: {action}")

    def integrate(self, state: ProjectState, completed_task: Task, result: WorkerResult) -> list[Task]:
        return self.apply(state, completed_task, result, self.decide(state, completed_task, result))

    def _spawn(self, state: ProjectState, completed_task: Task, suggestions: list[str]) -> list[Task]:
        suggestions = [s.strip() for s in suggestions if s.strip()]
        if not suggestions or len(state.tasks) >= self.max_dynamic_tasks:
            return []
        if state.metadata.get("knowledge_saturated") and not completed_task.metadata.get("critical_followups"):
            state.metadata.setdefault("deferred_followups",[]).extend(suggestions[:100])
            return []
        pending=sum(t.status in {TaskStatus.WAITING,TaskStatus.READY,TaskStatus.BLOCKED,TaskStatus.RETRY} for t in state.leaf_tasks)
        queue_limit=int(state.metadata.get("dynamic_queue_limit", max(100, state.power_percent*25)))
        if pending >= queue_limit:
            state.metadata["dynamic_backpressure_drops"] = int(state.metadata.get("dynamic_backpressure_drops",0)) + len(suggestions)
            state.metadata.setdefault("deferred_followups",[]).extend(suggestions[:100])
            return []
        parent_id = completed_task.parent_id
        branch_pending=sum(t.parent_id==parent_id and t.status in {TaskStatus.WAITING,TaskStatus.READY,TaskStatus.BLOCKED,TaskStatus.RETRY} for t in state.leaf_tasks)
        branch_limit=max(25, queue_limit//8)
        if branch_pending >= branch_limit:
            state.metadata["branch_backpressure_drops"] = int(state.metadata.get("branch_backpressure_drops",0)) + len(suggestions)
            state.metadata.setdefault("deferred_followups",[]).extend(suggestions[:100])
            return []
        spawned: list[Task] = []
        for index, suggestion in enumerate(suggestions):
            if len(state.tasks) >= self.max_dynamic_tasks:
                break
            followup = Task(
                title=suggestion[:180],
                description=f"Dynamically spawned from '{completed_task.title}'.",
                parent_id=parent_id,
                depth=completed_task.depth,
                priority=max(1, completed_task.priority - index),
                dependencies=[completed_task.id],
                status=TaskStatus.WAITING,
                estimated_seconds=max(0.2, completed_task.estimated_seconds),
                required_capabilities=list(completed_task.required_capabilities),
                acceptance_criteria=list(completed_task.acceptance_criteria),
                metadata={"spawned_by": completed_task.id, "dynamic": True, **({"preferred_kind": completed_task.metadata.get("preferred_kind")} if completed_task.metadata.get("preferred_kind") else {})},
            )
            state.tasks[followup.id] = followup
            if parent_id and parent_id in state.tasks:
                state.tasks[parent_id].children.append(followup.id)
            else:
                state.root_task_ids.append(followup.id)
            spawned.append(followup)
        return spawned
