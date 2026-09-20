from __future__ import annotations
from dataclasses import asdict,dataclass
from .blocked_unit_rebuilder_v2 import BlockedUnitRebuilderV2
from .failure_cause_router_v1 import FailureCauseRouterV1
from .models import ProjectState,TaskStatus
from .task_roles_v2 import is_productive
from .blocked_safe_state_v1 import is_blocked_safe

@dataclass(slots=True)
class FallbackReport:
    action:str; localized:int; rebuilt:int; provider_deferred:int; human_gates:int
    def to_dict(self):return asdict(self)

class ProductiveFallbackOrchestratorV1:
    KEY='productive_fallback_orchestrator_v1'
    def __init__(self):self.router=FailureCauseRouterV1();self.rebuilder=BlockedUnitRebuilderV2()
    def apply(self,state:ProjectState)->FallbackReport:
        localized=rebuilt=deferred=human=0
        candidates=[t for t in state.leaf_tasks if is_productive(t,state) and t.status in {TaskStatus.FAILED,TaskStatus.BLOCKED,TaskStatus.RETRY,TaskStatus.NEEDS_REVIEW} and not t.metadata.get('explicit_human_gate') and not is_blocked_safe(t) and not t.metadata.get('waiting_provider_v1')]
        # First, remove the deterministic goal-lock task from the external-provider
        # critical path. This is enough to escape the exact real-world DEV271 stall.
        for t in list(candidates):
            if str(t.title).lower().startswith('clarify & lock goal'):
                self.rebuilder.replace(state,t,preferred_kind='local',preferred_provider='ceo-local-goal-lock',reason='goal_lock_local_fallback')
                localized+=1;rebuilt+=1
        # For other exhausted work, replace the unit rather than blindly retrying
        # the same provider conversation. Authentication/billing stay human gates.
        for t in candidates:
            if t.status==TaskStatus.SUPERSEDED:continue
            route=self.router.classify(t)
            if route.requires_human:
                human+=1;continue
            if route.provider_related and t.attempts<t.max_attempts:
                t.status=TaskStatus.RETRY;t.metadata['fresh_provider_context']=True;t.metadata['retry_strategy_changed']=route.action;deferred+=1
            elif t.attempts>=t.max_attempts or route.category in {'execution_dead_end','dependency'}:
                self.rebuilder.replace(state,t,reason=f'strategy_change:{route.category}');rebuilt+=1
        out=FallbackReport('fallback_applied' if (localized or rebuilt or deferred) else 'noop',localized,rebuilt,deferred,human)
        state.metadata[self.KEY]=out.to_dict();return out
