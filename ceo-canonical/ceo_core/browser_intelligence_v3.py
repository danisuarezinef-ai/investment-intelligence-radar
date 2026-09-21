from __future__ import annotations
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
from .models import ProjectState

@dataclass(slots=True)
class ElementCandidate:
    role:str|None=None;label:str|None=None;text:str|None=None;placeholder:str|None=None;score:float=0.0

class BrowserIntelligenceV3:
    """Semantic element-ranking layer; adapters can map candidates to Playwright locators."""
    def rank(self,elements:list[dict],intent:str)->list[ElementCandidate]:
        tokens=set(intent.lower().split());rows=[]
        for e in elements:
            text=' '.join(str(e.get(k,'')).lower() for k in ('role','label','text','placeholder'));et=set(text.split());score=len(tokens&et)/max(1,len(tokens))
            if any(w in text for w in tokens):score+=.2
            rows.append(ElementCandidate(e.get('role'),e.get('label'),e.get('text'),e.get('placeholder'),round(score,4)))
        return sorted(rows,key=lambda x:x.score,reverse=True)
    def locator_plan(self,candidate:ElementCandidate)->list[dict]:
        plans=[]
        if candidate.role and candidate.label:plans.append({'strategy':'role','role':candidate.role,'name':candidate.label})
        if candidate.label:plans.append({'strategy':'label','value':candidate.label})
        if candidate.placeholder:plans.append({'strategy':'placeholder','value':candidate.placeholder})
        if candidate.text:plans.append({'strategy':'text','value':candidate.text})
        return plans

class BrowserRecoveryEngine:
    def recover(self,state:ProjectState,service:str,page_state:dict)->str:
        if page_state.get('captcha'):action='needs_user'
        elif page_state.get('login_required'):action='needs_user'
        elif page_state.get('modal'):action='close_modal_retry'
        elif page_state.get('load_error'):action='reload_with_backoff'
        elif page_state.get('unexpected_page'):action='navigate_home_recover'
        else:action='continue'
        state.metadata.setdefault('browser_recovery',[]).append({'service':service,'action':action})
        return action

class BrowserSessionHealthMonitor:
    def update(self,state:ProjectState,service:str,authenticated:bool,latency_ms:float=0,error:str|None=None)->dict:
        status='healthy' if authenticated and not error else 'needs_login' if not authenticated else 'degraded'
        row={'status':status,'authenticated':authenticated,'latency_ms':latency_ms,'error':error,'checked_at':datetime.now(timezone.utc).isoformat()}
        state.metadata.setdefault('browser_session_health',{})[service]=row;return row
    def unhealthy(self,state:ProjectState)->list[str]:
        return [name for name,row in state.metadata.get('browser_session_health',{}).items() if row.get('status')!='healthy']
    def preflight(self,state:ProjectState,required_services:list[str])->dict:
        health=state.metadata.get('browser_session_health',{});missing=[s for s in required_services if health.get(s,{}).get('status')!='healthy'];return {'ready':not missing,'needs_attention':missing}
