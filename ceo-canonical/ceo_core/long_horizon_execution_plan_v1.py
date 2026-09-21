from __future__ import annotations
from dataclasses import dataclass,asdict
from .models import ProjectState,TaskStatus
from .task_roles_v2 import is_productive
@dataclass(slots=True)
class ExecutionWave:
    index:int; task_ids:list[str]; estimated_seconds:float; total_value:float
    def to_dict(self):return asdict(self)
class LongHorizonExecutionPlanV1:
    KEY='long_horizon_execution_plan_v1'
    def build(self,state:ProjectState,*,workers:int=4,max_tasks:int=100)->list[ExecutionWave]:
        remaining={t.id:t for t in state.leaf_tasks if is_productive(t,state) and t.status not in {TaskStatus.COMPLETE,TaskStatus.SUPERSEDED}}
        done={t.id for t in state.leaf_tasks if t.status in {TaskStatus.COMPLETE,TaskStatus.SUPERSEDED,TaskStatus.PARTIAL_COMPLETE,TaskStatus.COMPLETE_WITH_UNCERTAINTY}}
        waves=[];idx=1
        while remaining and sum(len(w.task_ids) for w in waves)<max_tasks:
            ready=[t for t in remaining.values() if all(d in done or d not in state.tasks for d in t.dependencies)]
            if not ready: break
            ready.sort(key=lambda t:(-(float(t.metadata.get('value_score',t.priority))),float(t.estimated_seconds),t.id))
            chosen=ready[:max(1,int(workers))]
            waves.append(ExecutionWave(idx,[t.id for t in chosen],round(max(float(t.estimated_seconds or 0) for t in chosen),2),round(sum(float(t.metadata.get('value_score',t.priority)) for t in chosen),2)))
            for t in chosen: done.add(t.id);remaining.pop(t.id,None)
            idx+=1
        state.metadata[self.KEY]={'waves':[w.to_dict() for w in waves],'unplanned':sorted(remaining)}
        return waves
