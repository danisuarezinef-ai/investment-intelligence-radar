from __future__ import annotations
from dataclasses import asdict,dataclass
from .models import ProjectState,Task,TaskStatus

@dataclass(slots=True)
class RebuildReport:
    rebuilt:int; rewired_dependencies:int; rewired_parent_children:int; replacements:list[str]
    def to_dict(self):return asdict(self)

class BlockedUnitRebuilderV2:
    KEY='blocked_unit_rebuilder_v2'
    def replace(self,state:ProjectState,target:Task,*,preferred_kind:str|None=None,preferred_provider:str|None=None,reason:str='stalled_work_unit')->Task:
        md={**target.metadata,'rebuilt_from':target.id,'rebuild_reason':reason,'stall_replan_generation':int(target.metadata.get('stall_replan_generation',0))+1,'task_role':'productive'}
        for k in ('last_provider_error','provider_errors','retry_after_ts','incident_circuit_open','worker_watchdog_timeout'):
            md.pop(k,None)
        if preferred_kind: md['preferred_kind']=preferred_kind
        if preferred_provider: md['preferred_provider']=preferred_provider
        md['avoid_providers']=[]
        replacement=Task(title=target.title,description=target.description,parent_id=target.parent_id,depth=target.depth,priority=target.priority,status=TaskStatus.READY,dependencies=list(target.dependencies),estimated_seconds=target.estimated_seconds,required_capabilities=list(target.required_capabilities),acceptance_criteria=list(target.acceptance_criteria),max_attempts=max(3,target.max_attempts),metadata=md)
        state.tasks[replacement.id]=replacement
        dep_count=0
        for other in state.tasks.values():
            if other.id==replacement.id or target.id not in other.dependencies:continue
            other.dependencies=[replacement.id if d==target.id else d for d in other.dependencies]
            other.metadata['dependency_rewired_from']=target.id;other.metadata['dependency_rewired_to']=replacement.id;dep_count+=1
        parent_count=0
        if target.parent_id and target.parent_id in state.tasks:
            parent=state.tasks[target.parent_id]
            if target.id in parent.children:
                parent.children=[replacement.id if x==target.id else x for x in parent.children]
                parent_count=1
        else:
            state.root_task_ids=[replacement.id if x==target.id else x for x in state.root_task_ids]
        target.status=TaskStatus.SUPERSEDED;target.metadata['replacement_task_id']=replacement.id;target.metadata['superseded_reason']=reason
        hist=state.metadata.setdefault(self.KEY,[]);hist.append({'old':target.id,'new':replacement.id,'dependencies':dep_count,'parent_children':parent_count,'reason':reason});del hist[:-100]
        return replacement
