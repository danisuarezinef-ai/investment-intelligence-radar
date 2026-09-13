"""Production PAPER runtime v13: v12 recovery + operational evidence gates 31-40.

V13 is observational/governance hardening on top of v12. It cannot authorize live trading,
automatic promotion/release, or Setup 1.6. Tasks 28 and 29 remain mandatory blockers for 40.
"""
from __future__ import annotations

import os
import threading
import time
from http.server import ThreadingHTTPServer

import cloud_service_v12 as base12
import radar_runtime_31_40_v1 as tasks3140
import radar_remote_evidence_21_30_v1 as remote_evidence

REAL_TRADING=False
_FORWARD_LOCK=threading.RLock()
_FORWARD_PREVIOUS=None


def _task(board,n):
    for row in (board or {}).get('tasks') or []:
        if row.get('task')==n:return row
    return {}


def _forward_snapshot(evidence):
    horizons=(evidence or {}).get('horizons') or {}
    return {'records':sum(int((v or {}).get('n',0) or 0) for v in horizons.values()),
            'matured':sum(int((v or {}).get('matured',0) or 0) for v in horizons.values()),
            'capture_started_at':(evidence or {}).get('capture_started_at'),
            'backfill_used':False,'reconstructed':False,'real_trading':False}


def runtime_board_31_40():
    global _FORWARD_PREVIOUS
    b21=base12.runtime_board();e=remote_evidence.summary()
    t28=_task(b21,28);t29=_task(b21,29)
    reconciliation=(base12._DURABLE_SYNC or {}).get('reconciliation') or t28
    lease=base12._lease_local();core=dict(base12._CORE_RESTORE_STATUS);checkpoint=base12._restore_state()
    current=_forward_snapshot(e if e.get('ok') else {})
    with _FORWARD_LOCK:
        previous=dict(_FORWARD_PREVIOUS or current);_FORWARD_PREVIOUS=dict(current)
    journal=(e.get('journal') or {}) if e.get('ok') else {}
    if e.get('ok'):
        # Backward-compatible summary fields from the durable evidence edge.
        for k in ('decision_rows','context_rows','pit_rows','nonretro_rows','paper_rows','prospective_decision_rows','prospective_context_rows'):
            if k in e and k not in journal:journal[k]=e.get(k)
    horizons=(e.get('horizons') or {}) if e.get('ok') else {}
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
    out['tasks_21_30_status']=_task(b21,30).get('status');out['runtime']='v13'
    out['live_execution_allowed']=False;out['automatic_promotion']=False;out['automatic_release']=False
    out['setup_1_6_allowed']=False;out['real_trading']=False
    return out


class ValidationV13Handler(base12.ValidationV12Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/tasks-31-40-v1':self._send(200,runtime_board_31_40());return
        if path=='/autonomous-simulator/tasks-21-40-v1':
            self._send(200,{'tasks_21_30':base12.runtime_board(),'tasks_31_40':runtime_board_31_40(),
                            'live_execution_allowed':False,'automatic_promotion':False,'automatic_release':False,
                            'setup_1_6_allowed':False,'real_trading':False});return
        super().do_GET()


def main():
    base12._install_runtime_guards()
    threading.Thread(target=base12._supervision_loop,name='paper-v12-supervision',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV13Handler).serve_forever()


if __name__=='__main__':main()
