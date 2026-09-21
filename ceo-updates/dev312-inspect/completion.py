from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from .claims import ClaimRegistry, ClaimStatus
from .models import ProjectState, Task, TaskStatus
from .task_roles_v2 import is_productive
from .continuity_policy import task_for_decision, protected_human_gate


def _is_control_plane(task: Task) -> bool:
    return not is_productive(task)



class CompletionOutcome(str, Enum):
    INCOMPLETE="incomplete"
    PARTIAL_COMPLETE="partial_complete"
    COMPLETE_WITH_UNCERTAINTY="complete_with_uncertainty"
    COMPLETE="complete"


@dataclass(slots=True)
class CompletionAssessment:
    complete: bool
    confidence: float
    blockers: list[str]
    reasons: list[str]
    outcome: CompletionOutcome = CompletionOutcome.INCOMPLETE
    level: str = "project"
    evidence: dict[str, bool] = field(default_factory=dict)


class MarginalYieldTracker:
    """Tracks whether more work still produces meaningful new knowledge."""
    def record(self,state:ProjectState,novelty:float)->None:
        w=state.metadata.setdefault("marginal_yield_window",[]);w.append(max(0.0,min(1.0,float(novelty))))
        if len(w)>30:del w[:-30]
    def score(self,state:ProjectState)->float:
        w=state.metadata.get("marginal_yield_window",[])
        return sum(w[-10:])/len(w[-10:]) if w else 1.0
    def saturated(self,state:ProjectState,threshold:float=0.08,min_samples:int=8)->bool:
        w=state.metadata.get("marginal_yield_window",[])
        return len(w)>=min_samples and self.score(state)<threshold


class CompletionAuditor:
    """Independent guard against premature COMPLETE declarations."""
    def audit_task(self,task:Task)->tuple[bool,list[str]]:
        reasons=[]
        if not (task.result or "").strip():reasons.append("missing_result")
        if task.acceptance_criteria and not task.metadata.get("acceptance_evidence"):
            # Legacy workers may provide criteria evidence in result protocol.
            if not task.metadata.get("criteria_satisfied",False): reasons.append("acceptance_evidence_missing")
        if task.quality_score is not None and task.quality_score<float(task.metadata.get("quality_threshold",0.50)):reasons.append("quality_below_threshold")
        return not reasons,reasons


class CompletionEngine:
    """Completion at task/branch/phase/project levels, with uncertainty and explicit evidence."""
    TERMINAL={TaskStatus.COMPLETE,TaskStatus.PARTIAL_COMPLETE,TaskStatus.COMPLETE_WITH_UNCERTAINTY,TaskStatus.SUPERSEDED}
    HARD_BLOCKING={TaskStatus.FAILED,TaskStatus.NEEDS_REVIEW,TaskStatus.RUNNING,TaskStatus.READY,TaskStatus.RETRY,TaskStatus.BLOCKED,TaskStatus.WAITING}
    def __init__(self)->None:
        self.claims=ClaimRegistry();self.auditor=CompletionAuditor();self.yield_tracker=MarginalYieldTracker()

    def assess_task(self,task:Task)->CompletionAssessment:
        ok,reasons=self.auditor.audit_task(task)
        terminal=task.status in self.TERMINAL
        conf=float(task.quality_score if task.quality_score is not None else task.confidence if task.confidence is not None else (0.7 if terminal else 0.0))
        blockers=[] if (terminal and ok) else reasons or [f"status:{task.status.value}"]
        outcome=CompletionOutcome.COMPLETE if terminal and ok else CompletionOutcome.INCOMPLETE
        if task.status==TaskStatus.PARTIAL_COMPLETE:outcome=CompletionOutcome.PARTIAL_COMPLETE
        if task.status==TaskStatus.COMPLETE_WITH_UNCERTAINTY:outcome=CompletionOutcome.COMPLETE_WITH_UNCERTAINTY
        return CompletionAssessment(outcome in {CompletionOutcome.COMPLETE,CompletionOutcome.COMPLETE_WITH_UNCERTAINTY},conf,blockers,reasons,outcome,"task")

    def assess_branch(self,state:ProjectState,task_id:str,level:str="branch")->CompletionAssessment:
        root=state.tasks.get(task_id)
        if not root:return CompletionAssessment(False,0,["missing_task"],[],level=level)
        ids=[];stack=[task_id]
        while stack:
            tid=stack.pop();t=state.tasks.get(tid)
            if not t:continue
            if not t.children:ids.append(tid)
            else:stack.extend(t.children)
        leaves=[state.tasks[i] for i in ids]
        return self._assess_leaves(state,leaves,level)

    def _assess_leaves(self,state:ProjectState,leaves:Iterable[Task],level:str)->CompletionAssessment:
        leaves=list(leaves)
        if not leaves:return CompletionAssessment(False,0,["no_leaf_tasks"],[],level=level)
        blockers=[f"{t.id}:{t.status.value}" for t in leaves if t.status in self.HARD_BLOCKING]
        qualities=[float(t.quality_score) for t in leaves if t.quality_score is not None and t.status in self.TERMINAL]
        conf=sum(qualities)/len(qualities) if qualities else (1.0 if not blockers else .25)
        uncertain=sum(t.status in {TaskStatus.PARTIAL_COMPLETE,TaskStatus.COMPLETE_WITH_UNCERTAINTY} for t in leaves)
        terminal=all(t.status in self.TERMINAL for t in leaves)
        outcome=CompletionOutcome.INCOMPLETE
        if terminal and not blockers:
            outcome=CompletionOutcome.COMPLETE_WITH_UNCERTAINTY if uncertain else CompletionOutcome.COMPLETE
        return CompletionAssessment(outcome in {CompletionOutcome.COMPLETE,CompletionOutcome.COMPLETE_WITH_UNCERTAINTY},round(conf,4),blockers,["all_leaf_tasks_terminal"] if terminal else [],outcome,level)

    def assess(self,state:ProjectState)->CompletionAssessment:
        # Project completion is a statement about domain work, not about the
        # scheduler's own recovery/audit machinery. Including control-plane leaves
        # here makes every failed recovery wrapper a new project blocker and changes
        # the deadlock signature indefinitely.
        productive_leaves=[t for t in state.leaf_tasks if not _is_control_plane(t)]
        base=self._assess_leaves(state,productive_leaves,"project")
        blockers=list(base.blockers);reasons=list(base.reasons);evidence:dict[str,bool]={}
        real_open_decisions = []
        for decision in state.decisions.values():
            if decision.status.value != "open":
                continue
            task = task_for_decision(state, decision)
            if task is not None and not is_productive(task, state) and not protected_human_gate(task, decision.metadata):
                continue
            real_open_decisions.append(decision)
        if real_open_decisions:
            blockers.append("open_decisions")
        min_conf=float(state.metadata.get("completion_confidence_threshold",.45))
        if base.confidence<min_conf:blockers.append("confidence_below_threshold")
        evidence_map=state.metadata.get("completion_evidence",{})
        for criterion in state.completion_criteria:
            covered=bool(evidence_map.get(criterion,False)) if evidence_map else base.complete
            evidence[criterion]=covered
            if not covered:blockers.append(f"criterion:{criterion}")

        # A locked GoalContract may require concrete deliverables.  Finishing every
        # leaf task is not enough if the requested output was never actually produced.
        deliverable_evidence = state.metadata.get("deliverable_evidence", {})
        for deliverable in state.goal_deliverables:
            covered = bool(deliverable_evidence.get(deliverable))
            evidence[f"deliverable:{deliverable}"] = covered
            if not covered:
                blockers.append(f"deliverable:{deliverable}")

        unresolved_critical=[c for c in self.claims.unresolved(state) if float(c.get("confidence",0.5))>=float(state.metadata.get("critical_claim_confidence",0.7))]
        if unresolved_critical:blockers.append(f"unresolved_critical_claims:{len(unresolved_critical)}")

        # Real-work projects must not be declared complete merely because the current
        # finite task batch reached terminal states.  A locked high-level goal can be
        # much larger than its first decomposition.  When enabled, an explicit goal
        # audit must verify the locked objective before project completion is allowed.
        if bool(state.metadata.get("require_goal_audit", False)) and not bool(state.metadata.get("goal_audit_passed", False)):
            blockers.append("goal_audit_required")

        outcome=base.outcome
        if blockers:outcome=CompletionOutcome.PARTIAL_COMPLETE if base.outcome!=CompletionOutcome.INCOMPLETE else CompletionOutcome.INCOMPLETE
        elif unresolved_critical:outcome=CompletionOutcome.COMPLETE_WITH_UNCERTAINTY
        complete=outcome in {CompletionOutcome.COMPLETE,CompletionOutcome.COMPLETE_WITH_UNCERTAINTY}
        assessment=CompletionAssessment(complete,base.confidence,blockers,reasons,outcome,"project",evidence)
        hist=state.metadata.setdefault("completion_history",[]);hist.append({"outcome":outcome.value,"confidence":base.confidence,"blockers":len(blockers)})
        if len(hist)>200:del hist[:-200]
        return assessment
