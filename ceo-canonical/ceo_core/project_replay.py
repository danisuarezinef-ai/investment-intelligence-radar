from __future__ import annotations
from dataclasses import dataclass,asdict
from .models import ProjectState

class ProjectReplayEngine:
    def timeline(self,state:ProjectState)->list[dict]:
        rows=[]
        for e in state.metadata.get('audit_log',[]):rows.append({'kind':'audit',**e})
        for e in state.metadata.get('replan_history',[]):rows.append({'kind':'replan',**e})
        for e in state.metadata.get('notification_delivery',[]):rows.append({'kind':'notification',**e})
        rows.sort(key=lambda x:str(x.get('ts') or x.get('timestamp') or ''))
        return rows

class CounterfactualProjectAnalysis:
    def simulate(self,state:ProjectState,*,workers_factor:float=1.0,cost_factor:float=1.0,quality_factor:float=1.0)->dict:
        tel=state.metadata.get('telemetry',{});seconds=float(tel.get('elapsed_seconds',0) or sum(float(t.actual_seconds or 0) for t in state.tasks.values()))
        cost=float(state.metadata.get('cost_spent',0));quality=[float(t.quality_score) for t in state.tasks.values() if t.quality_score is not None];q=sum(quality)/len(quality) if quality else .5
        return {'estimated_seconds':round(seconds/max(.1,workers_factor),3),'estimated_cost':round(cost*cost_factor,4),'estimated_quality':round(min(1,q*quality_factor),4)}

class AutonomousRetrospective:
    def evaluate(self,state:ProjectState)->dict:
        failed=sum(t.status.value=='failed' for t in state.tasks.values());retries=sum(t.attempts>1 for t in state.tasks.values());replans=len(state.metadata.get('replan_history',[]));
        lessons=[]
        if failed:lessons.append('Improve provider fallback and task decomposition for failed work.')
        if retries>max(2,len(state.tasks)*.1):lessons.append('High retry rate: refine prompts or provider routing.')
        if replans>10:lessons.append('High replanning frequency: improve initial meta-plan.')
        if not lessons:lessons.append('Current strategy was stable; preserve as a candidate procedure.')
        row={'failed':failed,'retried_tasks':retries,'replans':replans,'lessons':lessons};state.metadata['autonomous_retrospective']=row;return row
