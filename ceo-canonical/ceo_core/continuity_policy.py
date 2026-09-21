from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import Decision, DecisionStatus, ProjectState, Task, TaskStatus
from .blocked_safe_state_v1 import is_blocked_safe


_PROTECTED_GATE_TOKENS = {
    "payment", "payments", "spend", "purchase", "billing", "subscription", "credit",
    "destructive", "delete", "irreversible", "external", "publish", "promotion", "promote",
    "login", "captcha", "mfa", "credential", "credentials", "authorization", "legal",
}


def is_goal_audit_lineage(state: ProjectState, task: Task | None) -> bool:
    """True when task is the internal goal-continuity control plane or its legacy child."""
    current = task
    seen: set[str] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        if current.metadata.get("goal_continuity_audit") or current.metadata.get("control_plane_atomic"):
            return True
        if str(current.title or "").startswith("Goal continuity audit #"):
            return True
        current = state.tasks.get(current.parent_id) if current.parent_id else None
    return False


def is_internal_continuity_task(state: ProjectState, task: Task | None) -> bool:
    """True for internal continuity audits and their bounded recovery work.

    DEV189 correctly treated the atomic goal audit itself as internal, but the
    fallback recovery batch was intentionally emitted as root tasks with
    ``continuity_gap_recovery`` metadata.  That meant an internal verification
    leaf could later enter NEEDS_REVIEW and be misclassified as a human gate.
    This helper recognizes that persisted form without converting ordinary user
    or safety gates into autonomous work.
    """
    if task is None:
        return False
    if is_goal_audit_lineage(state, task):
        return True
    md = task.metadata or {}
    if not md.get("continuity_gap_recovery"):
        return False
    spawned_by = str(md.get("spawned_by") or "")
    if spawned_by:
        parent = state.tasks.get(spawned_by)
        if parent is not None and is_goal_audit_lineage(state, parent):
            return True
    # Legacy persisted recovery leaves may outlive/prune their spawning audit.
    # Require both the explicit internal marker and the canonical title prefix.
    return str(task.title or "").startswith("Continuity recovery:")



def should_override_cognitive_early_abort(state: ProjectState, task: Task | None) -> bool:
    """Return True when an early-abort belongs to CEO's internal control plane.

    Internal continuity/control/verification tasks must not be escalated to a human
    merely because the cognitive strategy has accumulated failures.  They should
    execute, fail normally if their bounded attempts are exhausted, and let the
    autonomous recovery ladder handle the result.  Genuine protected actions keep
    their human gate.
    """
    if task is None:
        return False
    try:
        from .task_roles_v2 import is_internal
        internal = bool(is_internal(task, state))
    except Exception:
        internal = False
    internal = internal or is_internal_continuity_task(state, task)
    return bool(internal and not protected_human_gate(task, task.metadata))

def task_for_decision(state: ProjectState, decision: Decision) -> Task | None:
    source_task_id = str(decision.metadata.get("source_task_id") or "")
    if source_task_id:
        task = state.tasks.get(source_task_id)
        if task is not None:
            return task
    for task in state.tasks.values():
        if str(task.metadata.get("decision_id") or "") == decision.id:
            return task
    return None


def protected_human_gate(task: Task | None, metadata: dict[str, Any] | None = None) -> bool:
    """Keep genuine human-only / safety gates out of continuity auto-recovery.

    This intentionally relies on explicit structured risk markers. A bare
    ``requires_user`` from a continuity worker is not sufficient because that is
    the historical false-escalation failure this policy repairs.
    """
    md: dict[str, Any] = dict(metadata or {})
    if task is not None:
        for key, value in task.metadata.items():
            md.setdefault(key, value)
        if float(task.cost_estimate or 0.0) > 0:
            md.setdefault("cost", float(task.cost_estimate))

    if str(md.get("autonomy_class") or "").lower() == "critical":
        return True
    if any(bool(md.get(k)) for k in (
        "human_only", "requires_explicit_human", "explicit_human_gate", "external_effect", "external_action",
        "irreversible", "destructive", "spend", "payment", "purchase", "billing", "requires_login",
        "requires_mfa", "requires_captcha", "remote_git_write", "promotion_action",
    )):
        return True
    try:
        if float(md.get("irreversibility") or 0.0) > 0:
            return True
        if float(md.get("cost") or 0.0) > 0:
            return True
    except (TypeError, ValueError):
        return True

    for key in ("decision_type", "gate_type", "action_category", "action"):
        value = str(md.get(key) or "").lower().replace("_", " ").replace("-", " ")
        tokens = set(value.split())
        if tokens & _PROTECTED_GATE_TOKENS:
            return True
    return False


def recover_internal_continuity_decisions(state: ProjectState) -> int:
    """Close stale false human decisions created by internal continuity audits.

    Genuine protected gates remain OPEN. Recovery is immediate because an internal
    control-plane audit must never wait on the operator merely to continue itself.
    """
    if not state.autonomy_enabled:
        return 0
    recovered = 0
    now = datetime.now(timezone.utc).isoformat()
    for decision in state.decisions.values():
        if decision.status != DecisionStatus.OPEN:
            continue
        task = task_for_decision(state, decision)
        if task is None or not is_internal_continuity_task(state, task):
            continue
        if is_blocked_safe(task):
            continue
        if protected_human_gate(task, decision.metadata):
            continue

        selected = decision.recommendation or (decision.options[0] if decision.options else None) or "Continue autonomously"
        decision.selected = selected
        decision.status = DecisionStatus.AUTO_RESOLVED
        decision.metadata["auto_resolution_reason"] = "internal_continuity_false_human_gate_recovered"
        decision.metadata["auto_resolved_at"] = now
        decision.metadata["source_task_id"] = task.id

        task.metadata["internal_continuity_decision_recovered"] = now
        task.metadata["recovered_decision_id"] = decision.id
        task.metadata.pop("decision_id", None)
        task.metadata.pop("requires_user", None)
        task.max_attempts = max(int(task.max_attempts), int(task.attempts) + 2)
        if task.status == TaskStatus.NEEDS_REVIEW:
            task.status = TaskStatus.RETRY
            task.metadata["next_instruction"] = (
                "Internal continuity control-plane work: continue autonomously. "
                "If the locked goal is incomplete, create concrete executable follow-up tasks. "
                "Escalate only a genuine protected human-only action."
            )

        state.human_interventions_avoided += 1
        state.metadata.setdefault("decision_history", []).append({
            "id": decision.id,
            "selected": selected,
            "source": "internal_continuity_recovery",
            "recommendation": decision.recommendation,
        })
        recovered += 1
    if recovered:
        state.metadata["internal_continuity_decisions_recovered"] = int(
            state.metadata.get("internal_continuity_decisions_recovered", 0)
        ) + recovered
        state.metadata.pop("autonomy_stalled", None)
        state.metadata["autonomy_stall_cycles"] = 0
    return recovered
