from __future__ import annotations
from dataclasses import dataclass,asdict
@dataclass(slots=True)
class ConcurrencyDecision:
    current:int; target:int; reason:str
    def to_dict(self):return asdict(self)
class AdaptiveConcurrencyGovernorV2:
    def decide(self,*,current:int,max_workers:int,throughput:float,failure_rate:float,restart_pressure:float,queue_depth:int)->ConcurrencyDecision:
        cur=max(1,int(current)); cap=max(1,int(max_workers)); target=cur;reason='hold'
        if failure_rate>.25 or restart_pressure>.20:
            target=max(1,cur-1);reason='reduce_instability'
        elif queue_depth>cur and failure_rate<.08 and restart_pressure<.05 and throughput>0:
            target=min(cap,cur+1);reason='increase_safe_capacity'
        elif queue_depth==0:
            target=max(1,min(cur,2));reason='idle_trim'
        return ConcurrencyDecision(cur,target,reason)
