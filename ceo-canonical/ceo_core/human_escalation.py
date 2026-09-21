from __future__ import annotations
from dataclasses import dataclass,asdict
from .models import ProjectState,Decision

class HumanEscalationEngine:
    def should_escalate(self,state:ProjectState,decision:Decision,threshold:float=.65)->bool:
        if not state.autonomy_enabled:return True
        confidence=float(decision.confidence or 0.0);irreversible=bool(decision.metadata.get('irreversible'));high_cost=bool(decision.metadata.get('high_cost'));return irreversible or high_cost or confidence<threshold
    def card(self,decision:Decision,blocked_tasks:int=0)->dict:
        consequence=f'{blocked_tasks} task(s) wait for this decision.' if blocked_tasks else 'Independent work can continue.'
        return {'decision_id':decision.id,'title':decision.title,'context':decision.description[:500],'options':decision.options,'recommendation':decision.recommendation,'confidence':decision.confidence,'consequence':consequence,'timeout_seconds':decision.timeout_seconds}

class InterruptionLearningEngine:
    def record(self,state:ProjectState,decision:Decision,changed_outcome:bool)->None:
        bucket=str(decision.metadata.get('category','general'));r=state.metadata.setdefault('interruption_learning',{}).setdefault(bucket,{'asked':0,'useful':0});r['asked']+=1;r['useful']+=int(changed_outcome)
    def ask_threshold(self,state:ProjectState,category:str)->float:
        r=state.metadata.get('interruption_learning',{}).get(category)
        if not r:return .65
        usefulness=float(r['useful'])/max(1,int(r['asked']));return round(max(.35,min(.9,.85-.4*usefulness)),3)

class NotificationIntelligence:
    def route(self,event:dict)->str:
        sev=str(event.get('severity','info'));urgent=bool(event.get('urgent'))
        if urgent or sev in {'critical','error'}:return 'immediate'
        if sev in {'decision','milestone'}:return 'digest_soon'
        return 'summary'
    def digest(self,events:list[dict])->dict:
        return {'count':len(events),'critical':sum(self.route(e)=='immediate' for e in events),'decisions':sum(e.get('severity')=='decision' for e in events),'titles':[str(e.get('title','')) for e in events[:10]]}
