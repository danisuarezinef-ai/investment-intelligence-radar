from __future__ import annotations
from dataclasses import asdict,dataclass
from .models import ProjectState,TaskStatus
from .productive_truth_v2 import ProductiveTruthV2
from .recovery_churn_fuse_v2 import RecoveryChurnFuseV2
from .productive_fallback_orchestrator_v1 import ProductiveFallbackOrchestratorV1

@dataclass(slots=True)
class UsefulOutputWatchdogReport:
    status:str; stalled:bool; recoveries_without_progress:int; fuse_open:bool; fallback_action:str; repaired_units:int
    def to_dict(self):return asdict(self)

class UsefulOutputWatchdogV2:
    KEY='useful_output_watchdog_v2'
    def __init__(self):
        self.truth=ProductiveTruthV2(recovery_trip=4);self.fuse=RecoveryChurnFuseV2(max_attempts=4);self.fallback=ProductiveFallbackOrchestratorV1()
    def tick(self,state:ProjectState)->UsefulOutputWatchdogReport:
        truth=self.truth.assess(state)
        provider_wait=dict(state.metadata.get('provider_wait_v1') or {})

        # DEV308 executable-route invariant: queued/running productive work is
        # itself an executable route. Recovery history must never convert it into
        # a global BLOQUEADO state merely because no worker is active at this exact
        # scheduler tick.
        if truth.productive_running or truth.productive_ready:
            fuse=self.fuse.apply(
                state,
                attempts_without_progress=truth.worker_recoveries,
                stalled=False,
            )
            state.metadata.pop('autonomy_stalled',None)
            state.metadata.pop('operator_block_reason',None)
            state.metadata.pop('productive_stall_escape_required',None)
            state.metadata.pop('suppress_new_internal_recovery',None)
            operator='TRABAJANDO' if truth.productive_running else 'PLANIFICANDO'
            state.metadata['operator_productivity_state']=operator
            out=UsefulOutputWatchdogReport(
                operator,False,truth.worker_recoveries,fuse.open,'executable_route',0
            )
            state.metadata[self.KEY]=out.to_dict()
            return out

        # Provider backoff is not a broken route. Give it precedence over any stale
        # fuse/operator state left by a previous cycle and do not invoke fallback.
        if provider_wait.get('active') and truth.status=='waiting_provider':
            state.metadata.pop('productive_stall_escape_required',None)
            state.metadata.pop('suppress_new_internal_recovery',None)
            state.metadata['operator_productivity_state']='ESPERANDO PROVEEDOR'
            state.metadata['operator_block_reason']=(
                'Proveedor temporalmente no disponible; reintento acotado sin consumir recuperaciones.'
            )
            out=UsefulOutputWatchdogReport(
                'ESPERANDO PROVEEDOR',False,truth.worker_recoveries,False,'provider_wait',0
            )
            state.metadata[self.KEY]=out.to_dict()
            return out
        fuse=self.fuse.apply(state,attempts_without_progress=truth.worker_recoveries,stalled=truth.stalled)
        action='none';repaired=0
        # Trigger a real strategy change immediately when the fuse opens. Do not
        # manufacture another recovery wrapper.
        if fuse.open:
            fb=self.fallback.apply(state);action=fb.action;repaired=fb.rebuilt+fb.provider_deferred
            if repaired:
                state.metadata.pop('suppress_new_internal_recovery',None)
                state.metadata.pop('autonomy_stalled',None)
                state.metadata['productivity_kick_requested']=True
                state.metadata['operator_productivity_state']='REPLANIFICANDO'
            else:
                state.metadata['operator_productivity_state']='BLOQUEADO'
                blocked=[
                    t for t in state.leaf_tasks
                    if t.status in {TaskStatus.BLOCKED,TaskStatus.FAILED,TaskStatus.NEEDS_REVIEW}
                ] if hasattr(TaskStatus,'BLOCKED') else []
                reason='; '.join(
                    str(t.result or t.metadata.get('blocked_safe_reason') or t.title)
                    for t in blocked[:3]
                )
                state.metadata['operator_block_reason']=reason or 'No existe una ruta ejecutable después del fallback.'
        elif truth.stalled:
            state.metadata['operator_productivity_state']='ATASCADO'
        elif truth.status=='working':
            state.metadata['operator_productivity_state']='TRABAJANDO'
        elif truth.status=='planning':
            state.metadata['operator_productivity_state']='PLANIFICANDO'
        else:
            state.metadata['operator_productivity_state']=truth.status.upper()
        out=UsefulOutputWatchdogReport(state.metadata['operator_productivity_state'],truth.stalled,truth.worker_recoveries,fuse.open,action,repaired)
        state.metadata[self.KEY]=out.to_dict();return out
