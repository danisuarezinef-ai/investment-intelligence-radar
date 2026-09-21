from __future__ import annotations
from dataclasses import dataclass,asdict
from typing import Any
from .models import ProjectState,TaskStatus
from .task_roles_v2 import is_productive

TERMINAL={TaskStatus.COMPLETE,TaskStatus.PARTIAL_COMPLETE,TaskStatus.COMPLETE_WITH_UNCERTAINTY,TaskStatus.SUPERSEDED}
@dataclass(slots=True)
class CriticalPathETA:
    remaining_work_seconds:float; critical_path_seconds:float; effective_workers:float
    eta_seconds:float; p10_seconds:float; p90_seconds:float; confidence:float; critical_path_task_ids:list[str]
    def to_dict(self)->dict[str,Any]: return asdict(self)

class CriticalPathETAV3:
    KEY='critical_path_eta_v3'
    def estimate(self,state:ProjectState,*,workers:int=1)->CriticalPathETA:
        tasks={t.id:t for t in state.leaf_tasks if is_productive(t,state) and t.status not in TERMINAL}
        observed=[float(t.actual_seconds) for t in state.leaf_tasks if t.actual_seconds and is_productive(t,state) and t.status in TERMINAL]
        fallback=(sorted(observed)[len(observed)//2] if observed else 30.0)
        duration={tid:max(.05,float(t.actual_seconds or t.estimated_seconds or fallback)) for tid,t in tasks.items()}
        memo={}; pathmemo={}
        def cp(tid,stack=None):
            if tid in memo:return memo[tid],pathmemo[tid]
            stack=set(stack or ())
            if tid in stack:return 0.0,[]
            stack.add(tid); t=tasks[tid]
            deps=[d for d in t.dependencies if d in tasks]
            if not deps: val,p=duration[tid],[tid]
            else:
                best=max((cp(d,stack) for d in deps),key=lambda x:x[0],default=(0.0,[]))
                val,p=best[0]+duration[tid],best[1]+[tid]
            memo[tid]=val;pathmemo[tid]=p;return val,p
        best=(0.0,[])
        for tid in tasks: best=max(best,cp(tid),key=lambda x:x[0])
        total=sum(duration.values()); w=max(1,int(workers)); efficiency=.82 if w>1 else 1.0
        eta=max(best[0],total/max(1.0,w*efficiency)); conf=min(.95,.45+len(observed)*.025)
        out=CriticalPathETA(round(total,2),round(best[0],2),round(w*efficiency,2),round(eta,2),round(eta*.8,2),round(eta*1.35,2),round(conf,3),best[1])
        state.metadata[self.KEY]=out.to_dict();return out
