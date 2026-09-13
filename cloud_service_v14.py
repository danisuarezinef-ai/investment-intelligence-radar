"""Production PAPER runtime v14: v13 recovery/ops + forward learning diagnostics 41-50.

Tasks 41-50 are observational PAPER diagnostics. They cannot authorize real trading,
automatic model promotion, automatic release, or Setup 1.6.
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import ThreadingHTTPServer

import cloud_service_v13 as base13
import cloud_service_v7 as deployment_v7
import radar_learning_evidence_41_50_v1 as evidence4150
import radar_autonomous_learning_41_60_v1 as learning4160

REAL_TRADING=False


def runtime_board_41_50():
    ev=evidence4150.normalized_rows(limit=400)
    if ev.get('ok') is not True:
        tasks={str(n):{'state':'BLOCKED_EVIDENCE','evidence':{'status':'BLOCKED_EVIDENCE','reason':ev.get('error') or ev.get('status'),'real_trading':False}} for n in range(41,51)}
        return {'status':'BLOCKED_EVIDENCE','tasks':tasks,'evidence_status':ev.get('status'),
                'operational_dependency':'INDEPENDENT_DIAGNOSTIC','automatic_promotion':False,'automatic_release':False,
                'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
    rows=list(ev.get('normalized_rows') or [])
    # Tasks 41-50 do not require the 31-40 operational board to compute their forward diagnostics.
    # Later promotion/release gates still require prior operational evidence separately.
    full=learning4160.build_priorities_41_60(rows=rows,prior_16_40={'tasks':{},'diversity':{},'real_trading':False},persist=False)
    tasks={str(n):dict((full.get('tasks') or {}).get(str(n)) or {'state':'PENDING_SAMPLE','evidence':{'real_trading':False}}) for n in range(41,51)}
    counts={}
    for item in tasks.values():counts[item.get('state')]=counts.get(item.get('state'),0)+1
    matured=sum(1 for r in rows if r.get('matured') is True and r.get('natural') is True)
    actions=sum(1 for r in rows if r.get('matured') is True and r.get('natural') is True and r.get('decision_state') in {'BUY','SELL'})
    return {'status':'TASKS_41_50_EVALUATED','tasks':tasks,'state_counts':counts,
            'forward_rows':len(rows),'natural_matured_rows':matured,'natural_matured_actions':actions,
            'horizon_stats':ev.get('stats') or [],'evidence_edge_ms':ev.get('edge_ms'),
            'operational_dependency':'INDEPENDENT_DIAGNOSTIC_PRIOR_GATES_REQUIRED_LATER',
            'source_max_evaluated_at':full.get('source_max_evaluated_at'),
            'automatic_promotion':False,'automatic_demotion':False,'automatic_release':False,
            'setup_1_6_allowed':False,'live_execution_allowed':False,'simulation_only':True,'real_trading':False}


def _log_41_50_once():
    time.sleep(20)
    try:
        out=runtime_board_41_50()
        compact={
            'status':out.get('status'),'forward_rows':out.get('forward_rows'),
            'natural_matured_rows':out.get('natural_matured_rows'),'natural_matured_actions':out.get('natural_matured_actions'),
            'states':{k:(v or {}).get('state') for k,v in (out.get('tasks') or {}).items()},
            'automatic_promotion':False,'live_execution_allowed':False,'real_trading':False,
        }
    except Exception as exc:
        compact={'status':'FAIL_CLOSED','error':f'{type(exc).__name__}: {str(exc)[:500]}',
                 'automatic_promotion':False,'live_execution_allowed':False,'real_trading':False}
    print('[paper-learning-41-50] '+json.dumps(compact,sort_keys=True,default=str),flush=True)


class ValidationV14Handler(base13.ValidationV13Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/pre160-deployment-v7':
            self._send(200,deployment_v7.deployment_identity());return
        if path=='/autonomous-simulator/tasks-41-50-v1':self._send(200,runtime_board_41_50());return
        if path=='/autonomous-simulator/tasks-21-50-v1':
            self._send(200,{'tasks_21_30':base13.runtime_board_21_30(),
                            'tasks_31_40':base13.runtime_board_31_40(),
                            'tasks_41_50':runtime_board_41_50(),
                            'automatic_promotion':False,'automatic_release':False,
                            'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False});return
        super().do_GET()


def main():
    base13.base12._install_runtime_guards()
    threading.Thread(target=base13.base12._supervision_loop,name='paper-v12-supervision',daemon=True).start()
    threading.Thread(target=base13._run_runtime_probes_once,name='paper-disaster-probes',daemon=True).start()
    threading.Thread(target=_log_41_50_once,name='paper-learning-41-50',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV14Handler).serve_forever()


if __name__=='__main__':main()
