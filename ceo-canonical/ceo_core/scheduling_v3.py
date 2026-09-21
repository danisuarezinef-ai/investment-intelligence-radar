from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from typing import Any

from .graph import TaskGraph
from .models import ProjectState, Task, TaskStatus


class TaskValueModel:
    """Priority = urgency + downstream impact + critical path + information value - cost/time."""
    @staticmethod
    def _formula(task:Task,downstream:int,critical:bool)->float:
        uncertainty=1-float(task.confidence if task.confidence is not None else task.metadata.get("confidence_prior",.5))
        information=float(task.metadata.get("information_value",uncertainty))
        relevance=float(task.metadata.get("relevance",1.0))
        cost=float(task.cost_estimate or 0.0);duration=float(task.estimated_seconds or .1)
        speculative_penalty=.15 if task.metadata.get("speculative") else 0.0
        return relevance*((task.priority/100)*3+min(3,downstream*.15)+(2 if critical else 0)+information*1.4)-(min(2,duration/120)+min(2,cost*2)+speculative_penalty)
    def score(self,state:ProjectState,task:Task,graph:TaskGraph)->float:
        return self._formula(task,graph.downstream_count(state,task.id),task.id in set(graph.remaining_critical_path(state).get("task_ids",[])))
    def score_many(self,state:ProjectState,tasks:list[Task],graph:TaskGraph)->dict[str,float]:
        # Scalable batch scoring: build reverse immediate-dependency counts and critical path once.
        reverse_counts={tid:0 for tid in state.tasks}
        for row in state.tasks.values():
            for dep in row.dependencies:
                if dep in reverse_counts:reverse_counts[dep]+=1
        critical=set(graph.remaining_critical_path(state).get("task_ids",[]))
        return {t.id:self._formula(t,reverse_counts.get(t.id,0),t.id in critical) for t in tasks}


class BackpressureManager:
    def limits(self,state:ProjectState)->dict[str,int]:
        power=max(1,state.power_percent);base=max(100, power*25)
        return {"total_ready":base,"per_branch":max(25,base//8)}
    def saturated(self,state:ProjectState)->bool:
        lim=self.limits(state);ready=[t for t in state.leaf_tasks if t.status==TaskStatus.READY]
        if len(ready)>lim["total_ready"]:return True
        by=defaultdict(int)
        for t in ready:by[t.parent_id]+=1
        return any(v>lim["per_branch"] for v in by.values())


class SpeculativeExecutionManager:
    def candidates(self,state:ProjectState,limit:int=5)->list[Task]:
        if state.exploration_percent<50:return []
        rows=[t for t in state.leaf_tasks if t.status==TaskStatus.BLOCKED and t.metadata.get("speculative_safe")]
        rows.sort(key=lambda t:float(t.metadata.get("probability_needed",.5))*float(t.metadata.get("information_value",.5)),reverse=True)
        return rows[:limit]
    def cancel_irrelevant(self,state:ProjectState)->int:
        n=0
        for t in state.leaf_tasks:
            if t.metadata.get("speculative") and float(t.metadata.get("relevance",1))<.15 and t.status not in {TaskStatus.COMPLETE,TaskStatus.SUPERSEDED}:
                t.status=TaskStatus.SUPERSEDED;t.metadata["superseded_reason"]="speculation_no_longer_relevant";n+=1
        return n


@dataclass(slots=True)
class ConcurrencyObservation:
    workers:int;throughput:float;failure_rate:float;latency:float


class AdaptiveConcurrencyOptimizer:
    def record(self,state:ProjectState,workers:int,throughput:float,failure_rate:float,latency:float)->None:
        rows=state.metadata.setdefault("concurrency_observations",[]);rows.append({"workers":workers,"throughput":throughput,"failure_rate":failure_rate,"latency":latency})
        if len(rows)>200:del rows[:-200]
    def optimal(self,state:ProjectState,hardware_cap:int)->int:
        rows=state.metadata.get("concurrency_observations",[])
        healthy=[r for r in rows if float(r.get("failure_rate",0))<.15]
        if not healthy:return max(1,min(hardware_cap,round(hardware_cap*state.power_percent/100)))
        best=max(healthy,key=lambda r:float(r.get("throughput",0))/(1+float(r.get("latency",0))/1000))
        return max(1,min(hardware_cap,int(best.get("workers",1))))
    def saturation_point(self,state:ProjectState)->int|None:
        rows=sorted(state.metadata.get("concurrency_observations",[]),key=lambda r:int(r.get("workers",0)))
        best=None
        for prev,cur in zip(rows,rows[1:]):
            wp,wc=int(prev["workers"]),int(cur["workers"]);tp,tc=float(prev["throughput"]),float(cur["throughput"])
            if wc>wp and tc <= tp*1.05:return wp
            best=wc
        return best


class WorkloadPools:
    KINDS=("api","browser","local","file")
    def classify(self,task:Task)->str:
        kind=str(task.metadata.get("preferred_kind","api"))
        return kind if kind in self.KINDS else "api"
    def counts(self,state:ProjectState)->dict[str,int]:
        out={k:0 for k in self.KINDS}
        for t in state.leaf_tasks:
            if t.status==TaskStatus.RUNNING:out[self.classify(t)]+=1
        return out
