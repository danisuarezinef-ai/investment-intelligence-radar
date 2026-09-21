from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
from .models import ProjectState

@dataclass(slots=True)
class CapabilityScore:
    provider:str;task_type:str;quality:float;latency:float;cost:float;success_rate:float
    @property
    def utility(self)->float:return self.quality*2+self.success_rate-min(1,self.latency/60)-min(1,self.cost*2)

class ModelCapabilityDiscoveryEngine:
    def ingest_probe(self,state:ProjectState,row:CapabilityScore)->None:
        state.metadata.setdefault('capability_discovery',{}).setdefault(row.provider,{})[row.task_type]=asdict(row)|{'utility':round(row.utility,4)}
    def best(self,state:ProjectState,task_type:str)->str|None:
        candidates=[]
        for p,types in state.metadata.get('capability_discovery',{}).items():
            if task_type in types:candidates.append((float(types[task_type]['utility']),p))
        return max(candidates)[1] if candidates else None

    def probe_plan(self,provider:str)->list[dict]:
        return [
            {'provider':provider,'task_type':'reasoning','prompt':'Solve a constrained multi-step reasoning task.'},
            {'provider':provider,'task_type':'code','prompt':'Implement and explain a small tested function.'},
            {'provider':provider,'task_type':'extraction','prompt':'Extract exact structured fields from supplied text.'},
            {'provider':provider,'task_type':'critique','prompt':'Find errors and unsupported claims in an answer.'},
            {'provider':provider,'task_type':'synthesis','prompt':'Synthesize multiple partially conflicting findings.'},
        ]

class ProviderArbitrageEngine:
    def choose(self,rows:list[CapabilityScore],mode:str='balanced')->CapabilityScore|None:
        if not rows:return None
        def score(r):
            if mode=='quality_max':return r.quality*3+r.success_rate-r.cost*.1
            if mode=='cost_min':return r.quality+r.success_rate-r.cost*3
            if mode=='speed':return r.quality+r.success_rate-r.latency/30
            return r.utility
        return max(rows,key=score)

class LocalModelManager:
    def discover(self,roots:list[str])->list[dict]:
        out=[]
        for root in roots:
            p=Path(root)
            if not p.exists():continue
            for f in p.rglob('*.gguf'):
                gb=f.stat().st_size/(1024**3);out.append({'path':str(f),'size_gb':round(gb,3),'estimated_ram_gb':round(gb*1.25,2)})
        return out
    def can_load(self,model:dict,free_ram_gb:float,free_vram_gb:float=0)->bool:return float(model.get('estimated_ram_gb',999))<=free_ram_gb+free_vram_gb*.7

class GPUWorkScheduler:
    def allocate(self,jobs:list[dict],free_vram_mb:float)->tuple[list[dict],list[dict]]:
        running=[];queued=[];left=free_vram_mb
        for job in sorted(jobs,key=lambda x:float(x.get('priority',0)),reverse=True):
            need=float(job.get('vram_mb',0));
            if need<=left:running.append(job);left-=need
            else:queued.append(job)
        return running,queued
