from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable
from .models import ProjectState, Task

@dataclass(slots=True)
class PlanCandidate:
    name: str
    estimated_cost: float
    estimated_seconds: float
    expected_quality: float
    risk: float
    breadth: float = .5
    depth: float = .5

    @property
    def utility(self) -> float:
        return self.expected_quality * 3.0 - self.risk * 1.5 - min(1.0, self.estimated_cost) - min(1.0, self.estimated_seconds / 3600.0) + .2 * (self.breadth + self.depth)

class MetaPlanningEngine:
    """Compares alternative planning strategies before committing project resources."""
    def choose(self, state: ProjectState, candidates: Iterable[PlanCandidate]) -> PlanCandidate:
        rows=list(candidates)
        if not rows: raise ValueError("At least one planning strategy is required")
        mode=state.priority_mode
        def score(c:PlanCandidate)->float:
            if mode=='quality_max': return c.expected_quality*4-c.risk-c.estimated_cost*.2
            if mode=='cost_min': return c.expected_quality*2-c.risk-c.estimated_cost*2
            if mode=='speed': return c.expected_quality*2-c.risk-min(3,c.estimated_seconds/600)
            return c.utility
        winner=max(rows,key=score)
        state.metadata['meta_plan']={'selected':winner.name,'candidates':[asdict(c)|{'utility':round(score(c),4)} for c in rows]}
        return winner

class MultiObjectivePlanner:
    """Scores tasks while respecting hard constraints and weighted soft objectives."""
    def score(self, task: Task, *, objectives: dict[str,float], hard_constraints: dict[str,float|bool]) -> float:
        m=task.metadata
        for key,limit in hard_constraints.items():
            value=m.get(key)
            if isinstance(limit,bool) and bool(value)!=limit:return float('-inf')
            if isinstance(limit,(int,float)) and value is not None and float(value)>float(limit):return float('-inf')
        score=float(task.priority)/100.0
        for key,weight in objectives.items(): score += float(weight)*float(m.get(key,0.0) or 0.0)
        return score

@dataclass(slots=True)
class ScenarioBranch:
    id: str
    label: str
    probability: float
    value: float
    cost: float
    active: bool=True

class ScenarioPlanner:
    def prune(self,state:ProjectState,branches:list[ScenarioBranch],keep:int=2)->list[ScenarioBranch]:
        ranked=sorted(branches,key=lambda b:b.probability*b.value-b.cost,reverse=True)
        kept=ranked[:max(1,keep)]
        keep_ids={b.id for b in kept}
        for b in branches:b.active=b.id in keep_ids
        state.metadata['scenario_branches']=[asdict(b) for b in branches]
        return kept
