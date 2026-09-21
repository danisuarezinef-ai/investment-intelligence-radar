from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import ceil
from typing import Iterable

from .models import ProjectState, Task, TaskStatus
from .quality import SemanticDeduplicator
from .blocked_safe_state_v1 import is_blocked_safe


@dataclass(slots=True)
class ComplexityAssessment:
    score: float
    too_large: bool
    too_small: bool
    recommended_parts: int
    reasons: list[str]


class TaskComplexityEstimator:
    def assess(self,task:Task)->ComplexityAssessment:
        text=f"{task.title} {task.description}";words=len(text.split());criteria=len(task.acceptance_criteria);deps=len(task.dependencies);caps=len(task.required_capabilities)
        score=min(1.0,words/300+criteria*.08+deps*.04+caps*.06+float(task.metadata.get("historical_failure_rate",0))*.25)
        too_large=score>.68 or words>500;too_small=score<.08 and words<16 and criteria<=1 and deps<=1
        parts=max(2,min(20,ceil(score*10))) if too_large else 1
        reasons=[]
        if too_large:reasons.append("task_too_large")
        if too_small:reasons.append("coordination_overhead_risk")
        return ComplexityAssessment(round(score,4),too_large,too_small,parts,reasons)


class AdaptiveTaskDecomposer:
    def __init__(self)->None:self.estimator=TaskComplexityEstimator();self.dedupe=SemanticDeduplicator()
    def recommended_depth(self,state:ProjectState,task:Task)->int:
        c=self.estimator.assess(task);failures=int(task.metadata.get("failure_count",0));base=1+round((state.depth_percent/100)*3)
        return min(8,base+(2 if failures>=2 else 0)+(1 if c.score>.7 else 0))
    def split(self,state:ProjectState,task:Task,parts:int|None=None)->list[Task]:
        # Continuity audits are control-plane protocol tasks.  They are intentionally
        # atomic: adaptive/failure splitting would remove their protocol metadata
        # from descendants and can deadlock the autonomous loop.
        if is_blocked_safe(task):
            task.metadata["split_refused_blocked_safe"] = True
            return []
        if task.metadata.get("goal_continuity_audit") or task.metadata.get("control_plane_atomic"):
            task.metadata["split_refused_control_plane"] = True
            return []
        c=self.estimator.assess(task);n=parts or c.recommended_parts
        if n<=1:return []
        children=[]
        for i in range(n):
            ch=Task(title=f"{task.title} · part {i+1}/{n}",description=f"Resolve a distinct, non-overlapping slice ({i+1}/{n}) of: {task.description}",parent_id=task.id,depth=task.depth+1,priority=max(1,task.priority-i),dependencies=list(task.dependencies),estimated_seconds=max(.1,task.estimated_seconds/n),required_capabilities=list(task.required_capabilities),acceptance_criteria=list(task.acceptance_criteria),metadata={"adaptive_split_of":task.id,"family_key":task.metadata.get("family_key",task.title.lower()[:80])})
            state.tasks[ch.id]=ch;task.children.append(ch.id);children.append(ch)
        task.status=TaskStatus.BLOCKED;task.metadata["group_task"]=True
        return children
    def refine_state(self,state:ProjectState,max_splits:int=50)->int:
        """Split only clearly oversized leaves; bounded to avoid planning explosions."""
        changed=0
        for task in list(state.leaf_tasks):
            if changed>=max_splits:break
            assessment=self.estimator.assess(task)
            if assessment.too_large and not task.metadata.get("adaptive_split_of"):
                self.split(state,task,assessment.recommended_parts);changed+=1
        return changed

    def split_failed(self,state:ProjectState,task:Task)->list[Task]:
        if task.metadata.get("goal_continuity_audit") or task.metadata.get("control_plane_atomic"):
            task.metadata["failure_split_refused_control_plane"] = True
            return []
        if int(task.metadata.get("failure_count",0))<2:return []
        # Bound recursive recovery: a failing child must not create an exponential
        # decomposition tree forever. Projects may raise this deliberately.
        max_depth=max(0,int(state.metadata.get("max_failure_split_depth",2)))
        if task.depth>=max_depth or task.metadata.get("failure_split_exhausted"):
            task.metadata["failure_split_exhausted"]=True
            return []
        return self.split(state,task,parts=max(2,min(6,int(task.metadata.get("failure_count",0))*2)))


class TaskFamilyManager:
    def family_key(self,task:Task)->str:
        return str(task.metadata.get("family_key") or " ".join(task.title.lower().split())[:80])
    def index(self,state:ProjectState)->dict[str,list[str]]:
        fam:dict[str,list[str]]=defaultdict(list)
        for t in state.leaf_tasks:fam[self.family_key(t)].append(t.id)
        state.metadata["task_families"]={k:v for k,v in fam.items()};return dict(fam)
    def merge_microtasks(self,state:ProjectState,max_group:int=8)->int:
        fam=self.index(state);merged=0
        for key,ids in fam.items():
            candidates=[state.tasks[i] for i in ids if state.tasks[i].status in {TaskStatus.WAITING,TaskStatus.READY,TaskStatus.BLOCKED} and not is_blocked_safe(state.tasks[i])]
            tiny=[t for t in candidates if t.estimated_seconds<=.25 and len((t.description or '').split())<40]
            if len(tiny)<2 or not BatchPolicy().should_batch(state,tiny):continue
            for chunk_i in range(0,len(tiny),max_group):
                chunk=tiny[chunk_i:chunk_i+max_group]
                if len(chunk)<2:continue
                batch=Task(title=f"Batch: {chunk[0].title[:90]}",description="Resolve these compatible microtasks in one response:\n"+"\n".join(f"- {t.id}: {t.title}" for t in chunk),priority=max(t.priority for t in chunk),dependencies=sorted({d for t in chunk for d in t.dependencies}),estimated_seconds=sum(t.estimated_seconds for t in chunk)*.7,required_capabilities=sorted({c for t in chunk for c in t.required_capabilities}),metadata={"batch_task":True,"batched_task_ids":[t.id for t in chunk],"family_key":key})
                state.tasks[batch.id]=batch;state.root_task_ids.append(batch.id)
                for t in chunk:t.status=TaskStatus.SUPERSEDED;t.metadata["batched_into"]=batch.id;merged+=1
        return merged


class BatchPolicy:
    def should_batch(self,state:ProjectState,tasks:Iterable[Task])->bool:
        rows=list(tasks)
        if len(rows)<2:return False
        stats=state.metadata.get("batch_stats",{});single=float(stats.get("single_seconds",1));batch=float(stats.get("batch_seconds_per_item",single))
        return batch <= single*.9 or all(t.estimated_seconds<.3 for t in rows)
