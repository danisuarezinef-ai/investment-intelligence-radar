from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import ProjectState, Task


class ProviderPolicy:
    def stats(self,state:ProjectState,provider:str)->dict:
        return state.metadata.setdefault('provider_stats',{}).setdefault(provider,{'runs':0,'failures':0,'total_seconds':0.0,'quality_total':0.0,'rate_limits':0,'cost':0.0,'circuit_open_until':0.0})
    def task_stats(self,state:ProjectState,provider:str,task_type:str)->dict:
        return state.metadata.setdefault('provider_task_stats',{}).setdefault(provider,{}).setdefault(task_type,{'runs':0,'successes':0,'failures':0,'seconds':0.0,'quality':0.0,'turns':0,'completion_rejections':0,'cost':0.0})
    def task_type(self,task:Task)->str:return str(task.metadata.get('task_type') or (task.required_capabilities[0] if task.required_capabilities else 'general'))
    def score(self,state:ProjectState,provider:str,task:Task|None=None)->float:
        s=self.stats(state,provider);runs=max(1,int(s.get('runs',0)));failure=float(s.get('failures',0))/runs;latency=float(s.get('total_seconds',0))/runs;quality=float(s.get('quality_total',0))/runs if s.get('quality_total') else .5;rate=min(1,float(s.get('rate_limits',0))/runs);cost=float(s.get('cost',0))/runs
        if task is not None:
            ts=self.task_stats(state,provider,self.task_type(task));tr=max(1,int(ts.get('runs',0)));specific_q=float(ts.get('quality',0))/tr if ts.get('quality') else quality;specific_fail=float(ts.get('failures',0))/tr
            quality=.6*specific_q+.4*quality;failure=.6*specific_fail+.4*failure;latency=.6*(float(ts.get('seconds',0))/tr)+.4*latency;cost=.6*(float(ts.get('cost',0))/tr)+.4*cost
        mode=state.priority_mode
        if mode=='quality_max':return quality*3.2-failure*1.2-rate-min(.5,latency/240)
        if mode=='cost_min':return quality-failure-rate-min(2,cost*10)
        if mode=='speed':return quality-failure-rate-min(2,latency/30)
        return quality*2-failure-rate-min(1,latency/120)-min(.5,cost*2)
    def circuit_open(self,state:ProjectState,provider:str)->bool:return float(self.stats(state,provider).get('circuit_open_until',0))>datetime.now(timezone.utc).timestamp()
    def record_failure(self,state:ProjectState,provider:str,*,rate_limited:bool=False)->None:
        s=self.stats(state,provider)
        if rate_limited:s['rate_limits']=int(s.get('rate_limits',0))+1
        failures=int(s.get('failures',0));
        if failures>=3:s['circuit_open_until']=datetime.now(timezone.utc).timestamp()+min(300,15*failures)
    def record_quality(self,state:ProjectState,provider:str,quality:float)->None:
        s=self.stats(state,provider);s['quality_total']=float(s.get('quality_total',0))+quality
    def record_task_outcome(self,state:ProjectState,provider:str,task:Task,*,success:bool,seconds:float,quality:float=0.0,turns:int=1,cost:float=0.0,completion_rejected:bool=False)->None:
        ts=self.task_stats(state,provider,self.task_type(task));ts['runs']+=1;ts['successes']+=int(success);ts['failures']+=int(not success);ts['seconds']+=seconds;ts['quality']+=quality;ts['turns']+=turns;ts['cost']+=cost;ts['completion_rejections']+=int(completion_rejected)
    def utility(self,state:ProjectState,provider:str,task_type:str)->float:
        s=self.task_stats(state,provider,task_type);r=max(1,s['runs']);quality=s['quality']/r if s['quality'] else .5;success=s['successes']/r;lat=s['seconds']/r;cost=s['cost']/r;reject=s['completion_rejections']/r
        return quality*2+success*1.5-min(1,lat/120)-min(1,cost*3)-reject
    def champion(self,state:ProjectState,task_type:str,candidates:list[str])->str|None:
        if not candidates:return None
        return max(candidates,key=lambda p:self.utility(state,p,task_type))
    def challenger_fraction(self,state:ProjectState)->float:return max(.02,min(.20,float(state.metadata.get('challenger_fraction',.08))))
    def capability_profile(self,state:ProjectState,provider:str)->dict[str,float]:
        rows=state.metadata.get('provider_task_stats',{}).get(provider,{})
        return {task_type:round(self.utility(state,provider,task_type),4) for task_type in rows}
