"""Production PAPER runtime v12: resilient singleton lease + live tasks 21-30 evidence board.

V12 keeps every v11 safety invariant. A failed heartbeat first attempts an atomic reacquire
for the exact same owner+persisted session. If that fails, PAPER is disabled immediately
and v11 admission is revoked. Re-admission requires the full exact restore path again.
"""
from __future__ import annotations

import os
import threading
import time
from http.server import ThreadingHTTPServer

import cloud_service_v11 as base11
import cloud_service_v10 as base10
import cloud_service_v9 as base9
import radar_runtime_21_30_v1 as tasks2130

REAL_TRADING=False


def resilient_heartbeat_runtime_lease():
    with base10._LEASE_LOCK:
        owner=base10._LEASE_STATE.get('owner_id'); session=base10._LEASE_STATE.get('session_id')
    if not owner or not session:
        return base10.acquire_runtime_lease()
    out=base10.runtime_lease.heartbeat(str(owner),str(session),ttl_seconds=180)
    if out.get('held') is not True:
        reacquire=base10.runtime_lease.acquire(str(owner),str(session),ttl_seconds=180)
        if reacquire.get('held') is True:
            out={**reacquire,'reacquired':True,'status':'HELD','real_trading':False}
        else:
            out={**out,'reacquired':False,'reacquire_error':reacquire.get('error'),'real_trading':False}
            try: base9.autonomous_paper.simulator.set_enabled(False)
            except Exception: pass
    with base10._LEASE_LOCK:
        base10._LEASE_STATE['last']=out
        base10._LEASE_STATE['last_error']=out.get('error') or out.get('reacquire_error')
        base10._LEASE_STATE['started']=out.get('held') is True
    return out


# v10 heartbeat loop resolves this global at runtime, so patch before admission starts.
base10.heartbeat_runtime_lease=resilient_heartbeat_runtime_lease


def _lease_local():
    with base10._LEASE_LOCK:
        last=dict(base10._LEASE_STATE.get('last') or {})
        owner=base10._LEASE_STATE.get('owner_id');session=base10._LEASE_STATE.get('session_id')
    last.setdefault('owner_id',owner);last.setdefault('session_id',session)
    return last


def _restore_state():
    with base11._LOCK:return dict(base11._STATE.get('paper_restore') or {})


def _reconciliation_pair():
    # Only claim fields whose equality is directly proven by exact restore. Missing fields
    # remain explicit so task 28 cannot accidentally pass on invented data.
    r=_restore_state(); session=(base11.admission_status().get('session_id'))
    local={'state_hash':r.get('local_state_hash'),'session_id':session,'cycle':None,'cash':None,'equity':None,
           'positions_hash':None,'learning_hash':None,'observed_at':base11.admission_status().get('last_attempt_at'),
           'backfilled':False,'real_trading':False}
    remote={'state_hash':r.get('remote_state_hash'),'session_id':session,'cycle':None,'cash':None,'equity':None,
            'positions_hash':None,'learning_hash':None,'observed_at':base11.admission_status().get('last_attempt_at'),
            'backfilled':False,'real_trading':False}
    return local,remote


def runtime_board():
    sim=base9.autonomous_paper.simulator.simulator_status()
    milestones=base9.autonomous_paper.milestones()
    restore=_restore_state(); lease=_lease_local(); local,remote=_reconciliation_pair()
    b=tasks2130.board(simulator_status=sim,milestones=milestones,restore=restore,lease=lease,
                      reconciliation_local=local,reconciliation_remote=remote,disaster_results=[])
    b['admission']=base11.admission_status();b['runtime']='v12';b['real_trading']=False
    return b


def _supervision_loop():
    while True:
        try:
            with base11._LOCK: ready=base11._STATE.get('status')=='READY_EXACT_PAPER'
            if ready:
                lease=_lease_local()
                if lease.get('held') is not True:
                    base11._block('distributed PAPER lease liveness lost; exact re-admission required',lease=lease)
            else:
                base11.attempt_exact_admission()
        except Exception as exc:
            base11._block(f'v12 supervision: {type(exc).__name__}: {str(exc)[:700]}')
        time.sleep(15)


class ValidationV12Handler(base11.ValidationV11Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/tasks-21-30-v1':self._send(200,runtime_board());return
        if path=='/autonomous-simulator/lease-continuity-v2':
            self._send(200,{'lease':_lease_local(),'admission':base11.admission_status(),
                            'live_execution_allowed':False,'real_trading':False});return
        super().do_GET()


def main():
    threading.Thread(target=_supervision_loop,name='paper-v12-supervision',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV12Handler).serve_forever()


if __name__=='__main__':main()
