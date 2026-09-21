from __future__ import annotations
from dataclasses import dataclass,asdict
from .models import ProjectState,TaskStatus
from .task_roles_v2 import is_productive
@dataclass(slots=True)
class UsefulMilestone:
    task_id:str; title:str; eta_seconds:float; value:float; value_per_second:float
    def to_dict(self):return asdict(self)
class UsefulMilestoneEngineV1:
    KEY='useful_milestone_engine_v1'
    def rank(self,state:ProjectState,*,limit:int=8)->list[UsefulMilestone]:
        rows=[]
        for t in state.leaf_tasks:
            if not is_productive(t,state) or t.status in {TaskStatus.COMPLETE,TaskStatus.SUPERSEDED}: continue
            eta=max(.05,float(t.actual_seconds or t.estimated_seconds or 1.0)); value=float(t.metadata.get('value_score',t.priority))
            rows.append(UsefulMilestone(t.id,t.title,round(eta,2),round(value,2),round(value/eta,4)))
        rows.sort(key=lambda x:(-x.value_per_second,x.eta_seconds,x.task_id)); rows=rows[:max(1,limit)]
        state.metadata[self.KEY]={'milestones':[r.to_dict() for r in rows]};return rows
