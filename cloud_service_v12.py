"""Production PAPER runtime v12: exact core continuity + resilient singleton lease.

V12 keeps every v11 safety invariant while separating critical durable state from the
heavier Supabase sync channels. PAPER actions are runtime-gated. Loss of lease or critical
persistence blocks PAPER immediately; same-process recovery requires durable reconciliation,
and process-start recovery requires exact autonomy-core plus exact financial restore.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from http.server import ThreadingHTTPServer

import cloud_service_v11 as base11
import cloud_service_v10 as base10
import cloud_service_v9 as base9
import cloud_service_v4 as base4
import radar_runtime_21_30_v1 as tasks2130
import radar_remote_evidence_21_30_v1 as remote_evidence
import radar_autonomy_core_v1 as autonomy_core
import radar_paper_engine_persistence_v1 as paper_persistence

REAL_TRADING=False
_CORE_LOCK=threading.RLock()
_CORE_RESTORED=False
_CORE_RESTORE_STATUS={'status':'NOT_STARTED','real_trading':False}
_TARGET_ENABLED=True
_DURABLE_SYNC={'status':'NOT_STARTED','real_trading':False}
_ORIGINALS={}


def _ready():
    with base11._LOCK:return base11._STATE.get('status')=='READY_EXACT_PAPER'


def _paper_ready():
    return _ready() and (_DURABLE_SYNC or {}).get('status')=='RECONCILED'


def _mark_blocked(reason, *, lease=None):
    with base11._LOCK:
        base11._STATE.update({'status':'BLOCKED_EXACT_RECOVERY','last_error':str(reason)[:900],
                              'lease':lease if lease is not None else base11._STATE.get('lease'),
                              'real_trading':False})
    print('[paper-v12] BLOCKED '+str(reason)[:700],flush=True)


def resilient_heartbeat_runtime_lease():
    with base10._LEASE_LOCK:
        owner=base10._LEASE_STATE.get('owner_id');session=base10._LEASE_STATE.get('session_id')
    if not owner or not session:return base10.acquire_runtime_lease()
    out=base10.runtime_lease.heartbeat(str(owner),str(session),ttl_seconds=180)
    if out.get('held') is not True:
        reacquire=base10.runtime_lease.acquire(str(owner),str(session),ttl_seconds=180)
        if reacquire.get('held') is True:
            out={**reacquire,'reacquired':True,'status':'HELD','real_trading':False}
        else:
            out={**out,'reacquired':False,'reacquire_error':reacquire.get('error'),'real_trading':False}
    with base10._LEASE_LOCK:
        base10._LEASE_STATE['last']=out;base10._LEASE_STATE['last_error']=out.get('error') or out.get('reacquire_error')
        base10._LEASE_STATE['started']=out.get('held') is True
    return out


base10.heartbeat_runtime_lease=resilient_heartbeat_runtime_lease


def _lease_local():
    with base10._LEASE_LOCK:
        last=dict(base10._LEASE_STATE.get('last') or {});owner=base10._LEASE_STATE.get('owner_id');session=base10._LEASE_STATE.get('session_id')
    raw=dict(last.get('lease') or {}) if isinstance(last.get('lease'),dict) else {}
    out={**raw,**last};out.setdefault('owner_id',owner);out.setdefault('session_id',session);out['real_trading']=False
    return out


def _restore_state():
    with base11._LOCK:return dict(base11._STATE.get('paper_restore') or {})


def _restore_autonomy_core_once():
    global _CORE_RESTORED,_CORE_RESTORE_STATUS,_TARGET_ENABLED
    with _CORE_LOCK:
        if _CORE_RESTORED:return dict(_CORE_RESTORE_STATUS)
        result=autonomy_core.restore_exact_core(base9.autonomous_paper.simulator)
        _CORE_RESTORE_STATUS=dict(result)
        if result.get('restored') is True:
            local=autonomy_core.local_state(base9.autonomous_paper.simulator)
            _TARGET_ENABLED=bool(local.get('enabled'))
            _CORE_RESTORED=True
            print('[paper-v12] autonomy core restored generation={} cycles={} experiments={}'.format(
                result.get('generation'),result.get('completed_cycles'),result.get('completed_experiments')),flush=True)
        else:
            _mark_blocked('exact durable autonomy core unavailable: '+str(result.get('error') or result.get('status')))
        return dict(_CORE_RESTORE_STATUS)


def _gate_paper_call(name, original, blocked_result):
    def wrapped(*args,**kwargs):
        if not _paper_ready():
            return {**blocked_result,'status':'BLOCKED_EXACT_RECOVERY','component':name,
                    'durable_sync':(_DURABLE_SYNC or {}).get('status'),'real_trading':False}
        return original(*args,**kwargs)
    return wrapped


def _install_runtime_guards():
    if _ORIGINALS:return
    rw=base9.base8.base7.base6.base5.base4.base3.base_v2.base.run_worker
    sim=base9.autonomous_paper.simulator
    for name in ('paper_authority_step','step_all_agents','safe_fast_cycle','safe_deep_cycle'):
        fn=getattr(rw,name,None)
        if callable(fn):
            _ORIGINALS['run_worker.'+name]=fn
            setattr(rw,name,_gate_paper_call(name,fn,{'can_trade':False,'paper_execution_allowed':False}))
    if callable(getattr(sim,'run_autonomous_cycle',None)):
        fn=sim.run_autonomous_cycle;_ORIGINALS['sim.run_autonomous_cycle']=fn
        sim.run_autonomous_cycle=_gate_paper_call('autonomous_simulator_cycle',fn,{'paper_execution_allowed':False})
    if callable(getattr(base4,'closed_loop_cycle',None)):
        fn=base4.closed_loop_cycle;_ORIGINALS['closed_loop_cycle']=fn
        def closed_guard(*args,**kwargs):
            if not _paper_ready():
                return {'status':'HOLD_EXACT_RECOVERY','forward_records':0,'optimizer':{'status':'HOLD_CASH'},
                        'champion_challenger':{'status':'BLOCKED'},'execution':{'status':'BLOCKED_EXACT_RECOVERY'},'real_trading':False}
            return fn(*args,**kwargs)
        base4.closed_loop_cycle=closed_guard


def _canon_hash(value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _learning_view(state):
    keys=('generation','completed_cycles','completed_experiments','last_cycle_at','last_research_at')
    return {k:(state or {}).get(k) for k in keys}


def _money_identity(value):
    if value is None:return None
    try:return format(float(value),'.10f')
    except (TypeError,ValueError):return str(value)


def _positions_hash(paper_positions,champion_positions):
    return paper_persistence.state_hash({'paper_agent_positions':paper_positions or [],'champion_paper_positions':champion_positions or []})


def _reconciliation_pair(remote=None):
    evidence=remote if isinstance(remote,dict) else remote_evidence.summary()
    admission=base11.admission_status();session=admission.get('session_id')
    try:local_cp=paper_persistence.engine_checkpoint()
    except Exception:return ({'real_trading':False},{'real_trading':False})
    tables=local_cp.get('tables') or {};marks=tables.get('champion_paper_marks') or [];mark=marks[-1] if marks else {}
    local_core=autonomy_core.local_state(base9.autonomous_paper.simulator)
    rcp=(evidence.get('checkpoint') or {}) if evidence.get('ok') else {};ra=(evidence.get('autonomy') or {}) if evidence.get('ok') else {}
    remote_core=ra.get('payload') if isinstance(ra.get('payload'),dict) else {};rlease=(evidence.get('lease') or {}) if evidence.get('ok') else {}
    local={'state_hash':local_cp.get('state_hash'),'session_id':session,'cycle':local_core.get('completed_cycles'),
           'cash':_money_identity(mark.get('cash')),'equity':_money_identity(mark.get('total')),
           'positions_hash':_positions_hash(tables.get('paper_agent_positions'),tables.get('champion_paper_positions')),
           'learning_hash':_canon_hash(_learning_view(local_core)),'observed_at':local_cp.get('observed_at'),
           'backfilled':False,'real_trading':False}
    remote={'state_hash':rcp.get('state_hash'),'session_id':rlease.get('session_id'),
            'cycle':remote_core.get('completed_cycles'),'cash':_money_identity(rcp.get('champion_cash')),'equity':_money_identity(rcp.get('champion_total')),
            'positions_hash':_positions_hash(rcp.get('paper_positions'),rcp.get('champion_positions')) if rcp else None,
            'learning_hash':_canon_hash(_learning_view(remote_core)) if remote_core else None,'observed_at':rcp.get('observed_at'),
            'backfilled':False,'real_trading':False}
    return local,remote


def _durable_sync_once(max_verify_attempts=4):
    global _DURABLE_SYNC,_TARGET_ENABLED
    lease=_lease_local()
    if lease.get('held') is not True:
        _DURABLE_SYNC={'status':'BLOCKED_LEASE','real_trading':False};return dict(_DURABLE_SYNC)
    local_core=autonomy_core.local_state(base9.autonomous_paper.simulator)
    if _ready():_TARGET_ENABLED=bool(local_core.get('enabled'))
    core=autonomy_core.persist_local_state(base9.autonomous_paper.simulator)
    checkpoint=paper_persistence.push_engine_checkpoint()
    checkpoint_ok=checkpoint.get('ok') is True or checkpoint.get('status') in {'PERSISTED_EXACT_PAPER_ENGINE','UPSERTED','OK','SYNCED'}
    rec={'status':'NOT_VERIFIED','real_trading':False};local={};remote={};evidence={};attempt=0
    for attempt in range(1,max(1,int(max_verify_attempts))+1):
        evidence=remote_evidence.summary();local,remote=_reconciliation_pair(evidence)
        complete=all(local.get(k) is not None and remote.get(k) is not None for k in ('state_hash','session_id','cycle','cash','equity','positions_hash','learning_hash','observed_at'))
        rec=tasks2130.hard.persistence_reconciliation_gate(local,remote) if complete else {'status':'NOT_VERIFIED','real_trading':False}
        if evidence.get('ok') is True and rec.get('status')=='RECONCILED':break
        if attempt<max_verify_attempts:time.sleep(min(3.0,float(attempt)))
    ok=core.get('ok') is True and checkpoint_ok and evidence.get('ok') is True and rec.get('status')=='RECONCILED'
    _DURABLE_SYNC={'status':'RECONCILED' if ok else 'DEGRADED','autonomy_core':core.get('status'),'checkpoint':checkpoint.get('status'),
                   'checkpoint_ok':checkpoint_ok,'checkpoint_hash':checkpoint.get('local_state_hash'),'reconciliation':rec,
                   'local_identity':local,'remote_identity':remote,'verify_attempts':attempt,'real_trading':False}
    if ok:print('[paper-v12] durable reconciliation RECONCILED cycle={} hash={}'.format(local.get('cycle'),str(local.get('state_hash') or '')[:12]),flush=True)
    else:print('[paper-v12] durable reconciliation DEGRADED blockers={} mismatches={}'.format(rec.get('blockers'),rec.get('mismatched_fields')),flush=True)
    return dict(_DURABLE_SYNC)


def runtime_board():
    sim=base9.autonomous_paper.simulator.simulator_status();milestones=base9.autonomous_paper.milestones();restore=_restore_state();lease=_lease_local()
    evidence=remote_evidence.summary();local,remote=_reconciliation_pair(evidence)
    b=tasks2130.board(simulator_status=sim,milestones=milestones,restore=restore,lease=lease,
                      reconciliation_local=local,reconciliation_remote=remote,disaster_results=[])
    b['admission']=base11.admission_status();b['autonomy_core_restore']=dict(_CORE_RESTORE_STATUS);b['durable_sync']=dict(_DURABLE_SYNC)
    b['runtime']='v12';b['live_execution_allowed']=False;b['real_trading']=False
    return b


def _resume_in_process_if_safe():
    global _TARGET_ENABLED
    lease=resilient_heartbeat_runtime_lease()
    if lease.get('held') is not True:return False
    sync=_durable_sync_once()
    prior=_restore_state()
    exact_prior=prior.get('status')=='RESTORED_EXACT_PAPER_ENGINE' and prior.get('verified') is True
    if sync.get('status')!='RECONCILED' or not exact_prior:return False
    if _TARGET_ENABLED:
        try:base9.autonomous_paper.simulator.set_enabled(True)
        except Exception:pass
    with base11._LOCK:
        base11._STATE.update({'status':'READY_EXACT_PAPER','last_error':None,'runtime_started':True,'lease':lease,'real_trading':False})
    print('[paper-v12] same-process durable reconciliation restored PAPER admission',flush=True)
    return True


def _supervision_loop():
    while True:
        try:
            if not _CORE_RESTORED:
                core=_restore_autonomy_core_once()
                if core.get('restored') is not True:time.sleep(15);continue
            if _ready():
                lease=resilient_heartbeat_runtime_lease()
                if lease.get('held') is not True:
                    _mark_blocked('distributed PAPER lease liveness lost; durable reconciliation required',lease=lease)
                else:
                    sync=_durable_sync_once()
                    if sync.get('status')!='RECONCILED':_mark_blocked('critical PAPER persistence divergence; durable reconciliation required',lease=lease)
            else:
                with base11._LOCK:workers_started=bool(base11._STATE.get('worker_started'))
                if workers_started:
                    _resume_in_process_if_safe()
                else:
                    result=base11.attempt_exact_admission()
                    if result.get('status')=='READY_EXACT_PAPER':
                        sync=_durable_sync_once()
                        if sync.get('status')=='RECONCILED':
                            if _TARGET_ENABLED:
                                try:base9.autonomous_paper.simulator.set_enabled(True)
                                except Exception:pass
                        else:_mark_blocked('post-restore durable reconciliation failed')
        except Exception as exc:_mark_blocked(f'v12 supervision: {type(exc).__name__}: {str(exc)[:700]}')
        time.sleep(30)


class ValidationV12Handler(base11.ValidationV11Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/tasks-21-30-v1':self._send(200,runtime_board());return
        if path=='/autonomous-simulator/lease-continuity-v2':
            self._send(200,{'lease':_lease_local(),'admission':base11.admission_status(),'autonomy_core_restore':dict(_CORE_RESTORE_STATUS),
                            'durable_sync':dict(_DURABLE_SYNC),'live_execution_allowed':False,'real_trading':False});return
        super().do_GET()


def main():
    _install_runtime_guards()
    threading.Thread(target=_supervision_loop,name='paper-v12-supervision',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV12Handler).serve_forever()


if __name__=='__main__':main()
