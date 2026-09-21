from __future__ import annotations
from dataclasses import dataclass,asdict
from .models import ProjectState,TaskStatus

@dataclass(slots=True)
class EnduranceMetrics:
    tasks:int
    terminal_failures:int
    replans:int
    interventions_required:int
    interventions_avoided:int
    autonomy_ratio:float
    avg_quality:float
    recovery_events:int

class AutonomousEnduranceBenchmark:
    def measure(self,state:ProjectState)->EnduranceMetrics:
        total=len(state.tasks);failed=sum(t.status==TaskStatus.FAILED for t in state.tasks.values());qs=[float(t.quality_score) for t in state.tasks.values() if t.quality_score is not None];req=state.human_interventions_required;avo=state.human_interventions_avoided;ratio=avo/max(1,avo+req)
        return EnduranceMetrics(total,failed,len(state.metadata.get('replan_history',[])),req,avo,round(ratio,4),round(sum(qs)/len(qs),4) if qs else 0.0,len(state.metadata.get('recovery_events',[])))
    def pass_gate(self,m:EnduranceMetrics,min_autonomy: float=.90)->bool:
        return m.terminal_failures==0 and m.autonomy_ratio>=float(min_autonomy)
