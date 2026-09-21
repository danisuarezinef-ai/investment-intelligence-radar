from __future__ import annotations
from dataclasses import dataclass,asdict
from hashlib import sha256
from .models import ProjectState

@dataclass(slots=True)
class PromptVariant:
    id:str;template:str;provider:str;task_type:str

class PromptOptimizationEngine:
    def register(self,state:ProjectState,template:str,provider:str,task_type:str)->PromptVariant:
        pid=sha256(f'{provider}|{task_type}|{template}'.encode()).hexdigest()[:16];v=PromptVariant(pid,template,provider,task_type);state.metadata.setdefault('prompt_variants',{})[pid]=asdict(v)|{'runs':0,'quality':0.0,'failures':0};return v
    def record(self,state:ProjectState,prompt_id:str,quality:float,success:bool)->None:
        row=state.metadata.setdefault('prompt_variants',{}).setdefault(prompt_id,{'runs':0,'quality':0.0,'failures':0});row['runs']+=1;row['quality']+=float(quality);row['failures']+=int(not success)
    def score(self,state:ProjectState,prompt_id:str)->float:
        r=state.metadata.get('prompt_variants',{}).get(prompt_id,{});n=max(1,int(r.get('runs',0)));return float(r.get('quality',0))/n-float(r.get('failures',0))/n
    def champion(self,state:ProjectState,provider:str,task_type:str)->str|None:
        rows=[(self.score(state,pid),pid) for pid,r in state.metadata.get('prompt_variants',{}).items() if r.get('provider')==provider and r.get('task_type')==task_type]
        return max(rows)[1] if rows else None
    def promote(self,state:ProjectState,champion:str,challenger:str,min_runs:int=5,margin:float=.05)->bool:
        c=state.metadata.get('prompt_variants',{}).get(challenger,{});ok=int(c.get('runs',0))>=min_runs and self.score(state,challenger)>self.score(state,champion)+margin
        if ok:state.metadata.setdefault('prompt_promotions',[]).append({'from':champion,'to':challenger})
        return ok
