from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any
from .models import ProjectState, TaskStatus
from .task_roles_v2 import is_productive

TERMINAL={TaskStatus.COMPLETE,TaskStatus.PARTIAL_COMPLETE,TaskStatus.COMPLETE_WITH_UNCERTAINTY}

def _now(): return datetime.now(timezone.utc).isoformat()

@dataclass(slots=True)
class ThroughputSnapshot:
    productive_completed:int; productive_running:int; productive_ready:int
    control_active:int; useful_outputs:int; recoveries:int; productivity_ratio:float
    completions_per_100_events:float; stalled:bool
    def to_dict(self)->dict[str,Any]: return asdict(self)

class ProductiveThroughputLedgerV1:
    KEY='productive_throughput_ledger_v1'
    def snapshot(self,state:ProjectState,*,persist:bool=True)->ThroughputSnapshot:
        leaves=[t for t in state.leaf_tasks if t.status!=TaskStatus.SUPERSEDED]
        prod=[t for t in leaves if is_productive(t,state)]
        done=[t for t in prod if t.status in TERMINAL]
        running=[t for t in prod if t.status==TaskStatus.RUNNING]
        ready=[t for t in prod if t.status in {TaskStatus.READY,TaskStatus.RETRY}]
        control=[t for t in leaves if not is_productive(t,state) and t.status in {TaskStatus.READY,TaskStatus.RETRY,TaskStatus.RUNNING,TaskStatus.NEEDS_REVIEW,TaskStatus.BLOCKED}]
        evidence=state.metadata.get('deliverable_evidence_v1',[]) or []
        recoveries=int(state.metadata.get('autonomy_recovery_tasks_created',0) or 0)
        events=list(state.metadata.get('activity_timeline',[]) or [])
        recent=events[-100:]
        productive_events=sum(1 for e in recent if str(e.get('kind','')).lower() in {'task_complete','provider_returned','productive_complete','deliverable_recorded'})
        ratio=len(done)/max(1,len(done)+recoveries+len(control))
        stalled=bool((ready or control) and not running and len(done)==int((state.metadata.get(self.KEY) or {}).get('last_completed',len(done))) and len(recent)>=20)
        snap=ThroughputSnapshot(len(done),len(running),len(ready),len(control),len(evidence),recoveries,round(ratio,4),round(productive_events,2),stalled)
        if persist:
            meta=state.metadata.setdefault(self.KEY,{})
            meta.update({**snap.to_dict(),'last_completed':len(done),'updated_at':_now()})
        return snap
