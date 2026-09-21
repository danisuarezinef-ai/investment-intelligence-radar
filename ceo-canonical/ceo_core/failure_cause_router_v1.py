from __future__ import annotations
from dataclasses import asdict,dataclass
from typing import Any
from .models import ProjectState,Task,TaskStatus
from .task_roles_v2 import is_productive

@dataclass(slots=True)
class FailureRoute:
    category:str; action:str; provider_related:bool; requires_human:bool; reason:str
    def to_dict(self)->dict[str,Any]:return asdict(self)

class FailureCauseRouterV1:
    KEY='failure_cause_router_v1'
    def classify(self,task:Task)->FailureRoute:
        text=str(task.metadata.get('last_provider_error') or task.result or '').lower()
        if any(x in text for x in ('429','quota','resource_exhausted')):
            return FailureRoute('provider_quota','fallback_or_defer',True,False,'provider quota/rate limit')
        if '404' in text and 'model' in text:
            return FailureRoute('provider_model','rotate_model',True,False,'configured model unavailable')
        if any(x in text for x in ('timeout','timed out','503','502','connection reset','temporarily unavailable')):
            return FailureRoute('provider_transient','fresh_context_or_fallback',True,False,'transient provider/transport failure')
        if any(x in text for x in ('401','403','invalid api key','unauthorized','permission_denied')):
            return FailureRoute('authentication','human_gate',True,True,'provider authentication requires operator action')
        if any(x in text for x in ('billing','payment','purchase','credit')):
            return FailureRoute('billing','human_gate',True,True,'billing is never auto-resolved')
        if task.status==TaskStatus.BLOCKED and task.dependencies:
            return FailureRoute('dependency','repair_dependency_graph',False,False,'blocked dependency graph')
        if task.attempts>=task.max_attempts:
            return FailureRoute('execution_dead_end','rebuild_work_unit',False,False,'same work unit exhausted its attempts')
        return FailureRoute('unknown','replan',False,False,'failure needs a different execution strategy')
    def summarize(self,state:ProjectState)->dict[str,Any]:
        rows=[]
        for t in state.leaf_tasks:
            if not is_productive(t,state) or t.status not in {TaskStatus.FAILED,TaskStatus.BLOCKED,TaskStatus.NEEDS_REVIEW,TaskStatus.RETRY}:continue
            r=self.classify(t);rows.append({'task_id':t.id,'title':t.title,**r.to_dict()})
        out={'routes':rows[:50],'provider_related':sum(bool(r['provider_related']) for r in rows),'human_gates':sum(bool(r['requires_human']) for r in rows)}
        state.metadata[self.KEY]=out;return out
