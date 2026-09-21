from __future__ import annotations
from dataclasses import dataclass,asdict,field
from .models import ProjectState,Task,TaskStatus
from .blocked_safe_state_v1 import is_blocked_safe

@dataclass(slots=True)
class DirectorAgent:
    id:str
    goal:str
    task_ids:list[str]
    budget:float=0.0
    memory:dict=field(default_factory=dict)
    specialists:list[str]=field(default_factory=list)

class HierarchicalDirectorV2:
    def build(self,state:ProjectState,team_size:int=24)->dict[str,dict]:
        leaves=[t for t in state.leaf_tasks if t.status not in {TaskStatus.COMPLETE,TaskStatus.SUPERSEDED}]
        groups:dict[str,list[Task]]={}
        for t in leaves:
            key=str(t.metadata.get('domain') or t.metadata.get('task_type') or t.parent_id or 'general')
            groups.setdefault(key,[]).append(t)
        directors={}
        for key,tasks in groups.items():
            for i in range(0,len(tasks),team_size):
                chunk=tasks[i:i+team_size];did=f'director2:{key}:{i//team_size}'
                d=DirectorAgent(did,f'Deliver {key}',[t.id for t in chunk],sum(float(t.cost_estimate or 0) for t in chunk),{'open':len(chunk)},sorted({c for t in chunk for c in t.required_capabilities}))
                directors[did]=asdict(d)
        state.metadata['director_v2']=directors
        return directors

    def local_replan(self,state:ProjectState,director_id:str)->dict:
        row=(state.metadata.get('director_v2') or {}).get(director_id)
        if not row:return {'changed':0,'reason':'unknown_director'}
        changed=0
        for tid in row.get('task_ids',[]):
            t=state.tasks.get(tid)
            if not t:continue
            if t.status==TaskStatus.BLOCKED and not t.dependencies and not is_blocked_safe(t):
                t.status=TaskStatus.READY;changed+=1
            if t.status==TaskStatus.FAILED and t.attempts<t.max_attempts:
                t.status=TaskStatus.RETRY;changed+=1
        row.setdefault('memory',{})['last_local_replan']={'changed':changed}
        return {'changed':changed,'director_id':director_id}

class TeamReorganizer:
    def rebalance(self,state:ProjectState,max_team:int=32,min_team:int=4)->dict:
        tree=dict(state.metadata.get('director_v2') or {})
        # regenerate if teams are overloaded or highly imbalanced
        sizes=[len(v.get('task_ids',[])) for v in tree.values()]
        overloaded=any(s>max_team for s in sizes)
        imbalanced=bool(sizes and max(sizes)>max(min_team,2*max(1,min(sizes))))
        if overloaded or imbalanced: tree=HierarchicalDirectorV2().build(state,team_size=max_team)
        state.metadata['team_reorganization']={'overloaded':overloaded,'imbalanced':imbalanced,'teams':len(tree)}
        return tree

class DelegationEngine:
    def strategy(self,task:Task)->str:
        risk=float(task.metadata.get('risk',0.2));uncert=float(task.metadata.get('uncertainty',0.2));complexity=float(task.metadata.get('complexity',0.5))
        if risk>.75 or uncert>.75:return 'independent_panel'
        if complexity>.8:return 'specialist_team'
        if complexity<.25 and risk<.4:return 'single_worker'
        return 'worker_plus_verifier'
