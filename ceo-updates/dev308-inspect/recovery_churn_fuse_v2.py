from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any
from .continuity_policy import protected_human_gate
from .models import ProjectState, TaskStatus
from .task_roles_v2 import is_internal

@dataclass(slots=True)
class RecoveryChurnFuseReport:
    open: bool
    attempts_without_progress: int
    retired: int
    reason: str
    def to_dict(self)->dict[str,Any]: return asdict(self)

class RecoveryChurnFuseV2:
    """Hard fuse: repeated recovery may not masquerade as progress."""
    KEY='recovery_churn_fuse_v2'
    def __init__(self,*,max_attempts:int=4): self.max_attempts=max(2,int(max_attempts))
    def apply(self,state:ProjectState,*,attempts_without_progress:int,stalled:bool)->RecoveryChurnFuseReport:
        open_state=bool(stalled and attempts_without_progress>=self.max_attempts)
        retired=0
        if open_state:
            active=[t for t in state.leaf_tasks if is_internal(t,state) and not protected_human_gate(t) and t.status in {TaskStatus.READY,TaskStatus.RETRY,TaskStatus.BLOCKED,TaskStatus.NEEDS_REVIEW}]
            # Keep at most one atomic control item for diagnostics; retire the rest.
            active.sort(key=lambda t:(int(t.priority),t.created_at),reverse=True)
            for t in active[1:]:
                t.status=TaskStatus.SUPERSEDED
                t.metadata['superseded_reason']='recovery_churn_fuse_v2'
                retired+=1
            state.metadata['suppress_new_internal_recovery']=True
            state.metadata['productive_stall_escape_required']=True
        elif not stalled:
            state.metadata.pop('productive_stall_escape_required',None)
        row=RecoveryChurnFuseReport(open_state,int(attempts_without_progress),retired,'recovery budget exhausted without useful output' if open_state else 'within recovery budget')
        state.metadata[self.KEY]=row.to_dict();return row
