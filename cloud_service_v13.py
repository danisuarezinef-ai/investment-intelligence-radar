"""Production PAPER runtime v13: v12 recovery + operational evidence gates 31-40.

V13 is observational/governance hardening on top of v12. It cannot authorize live trading,
automatic promotion/release, or Setup 1.6. Tasks 28 and 29 remain mandatory blockers for 40.
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import ThreadingHTTPServer

import cloud_service_v12 as base12
import radar_runtime_31_40_v1 as tasks3140
import radar_remote_evidence_21_30_v1 as remote_evidence
import radar_disaster_probes_v1 as disaster_probes

REAL_TRADING=False
_FORWARD_LOCK=threading.RLock()
_FORWARD_PREVIOUS=None
_PROBE_RESULT={'status':'NOT_RUN','real_trading':False}


def _task(board,n):
    for row in (board or {}).get('tasks') or []:
        if row.get('task')==n:return row
    return {}


def runtime_board_21_30():
    """Overlay v12 board with durable disaster evidence from Supabase."""
    b=base12.runtime_board();e=remote_evidence.summary()
    tasks=list(b.get('tasks') or [])
    disasters=(e.get('disasters') or []) if e.get('ok') else []
    t29=base12.tasks2130.task29_disaster_evidence(disasters)
    tasks=[t29 if x.get('task')==29 else x for x in tasks]
    pre30=[x for x in tasks if x.get('task')!=30]
    t30=base12.tasks2130.task30_composite(pre30)
    tasks=[t30 if x.get('task')==30 else x for x in tasks]
    return {**b,'tasks':tasks,'durable_disaster_rows':len(disasters),'runtime':'v13-overlay',
            'live_execution_allowed':False,'automatic_promotion':False,'automatic_release':False,
            'setup_1_6_allowed':False,'real_trading':False}


def _horizon_rows(evidence):
    raw=(evidence or {}).get('horizons') or []
    if isinstance(raw,dict):return [v for v in raw.values() if isinstance(v,dict)]
    return [v for v in raw if isinstance(v,dict)]


def _forward_snapshot(evidence):
    rows=_horizon_rows(evidence)
    return {'records':sum(int((v or {}).get('n',0) or 0) for v in rows),
            'matured':sum(int((v or {}).get('matured',0) or 0) for v in rows),
            'capture_started_at':min((v.get('first_created') for v in rows if v.get('first_created')),default=None),
            'backfill_used':False,'reconstructed':False,'real_trading':False}


def runtime_board_31_40():
    global _FORWARD_PREVIOUS
    b21=runtime_board_21_30();e=remote_evidence.summary()
    t28=_task(b21,28);t29=_task(b21,29)
    reconciliation=(base12._DURABLE_SYNC or {}).get('reconciliation') or t28
    lease=base12._lease_local();core=dict(base12._CORE_RESTORE_STATUS);checkpoint=base12._restore_state()
    current=_forward_snapshot(e if e.get('ok') else {})
    with _FORWARD_LOCK:
        previous=dict(_FORWARD_PREVIOUS or current);_FORWARD_PREVIOUS=dict(current)
    journal=(e.get('journal') or {}) if e.get('ok') else {}
    horizons={str(x.get('horizon')):x for x in _horizon_rows(e)} if e.get('ok') else {}
    deps=[
        {'name':'distributed_lease','critical':True,'status':'OK' if lease.get('held') is True else 'ERROR'},
        {'name':'durable_sync','critical':True,'status':'RECONCILED' if (base12._DURABLE_SYNC or {}).get('status')=='RECONCILED' else 'ERROR'},
        {'name':'remote_evidence','critical':False,'status':'OK' if e.get('ok') is True else 'DEGRADED'},
    ]
    recovery=[]
    if checkpoint.get('status')=='RESTORED_EXACT_PAPER_ENGINE':
        recovery.append({'recovery_mode':'EXACT_PAPER','state_hash_equal':checkpoint.get('remote_state_hash')==checkpoint.get('local_state_hash'),
                         'session_continuity':bool((base12.base11.admission_status() or {}).get('session_id')),
                         'backfill_used':checkpoint.get('backfill_used'),'real_trading':False})
    learning={'challenger_only':True,'bounded_mutation':True,'historical_can_promote':False,
              'automatic_promotion':False,'mutates_active_champion':False,'real_trading':False}
    out=tasks3140.board(lease=lease,core=core,checkpoint=checkpoint,reconciliation=reconciliation,
        forward_current=current,forward_previous=previous,journal=journal,horizons=horizons,
        dependencies=deps,recoveries=recovery,replay={},learning=learning,
        task28_status=t28.get('status'),task29_status=t29.get('status'))
    out['tasks_21_30_status']=_task(b21,30).get('status');out['runtime']='v13';out['runtime_probe']=dict(_PROBE_RESULT)
    out['live_execution_allowed']=False;out['automatic_promotion']=False;out['automatic_release']=False
    out['setup_1_6_allowed']=False;out['real_trading']=False
    return out


def _run_runtime_probes_once():
    global _PROBE_RESULT
    time.sleep(8)
    try:_PROBE_RESULT=disaster_probes.run_controlled_probes()
    except Exception as exc:_PROBE_RESULT={'status':'FAIL','error':f'{type(exc).__name__}: {str(exc)[:700]}','real_trading':False}
    print('[paper-disaster-probes] '+json.dumps(_PROBE_RESULT,sort_keys=True,default=str),flush=True)


class ValidationV13Handler(base12.ValidationV12Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/tasks-21-30-v1':self._send(200,runtime_board_21_30());return
        if path=='/autonomous-simulator/tasks-31-40-v1':self._send(200,runtime_board_31_40());return
        if path=='/autonomous-simulator/tasks-21-40-v1':
            self._send(200,{'tasks_21_30':runtime_board_21_30(),'tasks_31_40':runtime_board_31_40(),
                            'live_execution_allowed':False,'automatic_promotion':False,'automatic_release':False,
                            'setup_1_6_allowed':False,'real_trading':False});return
        if path=='/autonomous-simulator/disaster-probes-v1':
            self._send(200,{**dict(_PROBE_RESULT),'live_execution_allowed':False,'real_trading':False});return
        super().do_GET()


def main():
    base12._install_runtime_guards()
    threading.Thread(target=base12._supervision_loop,name='paper-v12-supervision',daemon=True).start()
    threading.Thread(target=_run_runtime_probes_once,name='paper-disaster-probes',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV13Handler).serve_forever()


if __name__=='__main__':main()
