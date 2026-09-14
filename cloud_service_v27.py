"""PAPER runtime v27: v26 + development-only load shedding.

Pauses legacy pre160/deep audit workers that are not required for the first simulator
trial. Critical PAPER continuity remains active: exact admission, distributed lease,
checkpoint restore/persist, durable reconciliation, generic/learning sync, authority,
forward outcomes, autonomous simulator, closed-loop and core PAPER worker.

REAL_TRADING remains permanently false in this development runtime.
"""
from __future__ import annotations
import os,time,threading,json
from http.server import ThreadingHTTPServer
import cloud_service_v26 as base26
import cloud_service_v4 as v4
import cloud_service_v7 as v7
import cloud_service_v8 as v8
import cloud_service_v9 as v9
from radar_block_d_validation_v1 import block_d_validation

REAL_TRADING=False
DEVELOPMENT_PAPER_MODE=True
_LOAD_SHED_APPLIED=False
_BLOCK_D_RESULT={'status':'NOT_RUN','real_trading':False}


def _idle_worker(label):
    def worker(*args,**kwargs):
        print(f'[development-load-shed] paused={label} real_trading=false',flush=True)
        while True: time.sleep(3600)
    return worker


def apply_development_load_shed():
    global _LOAD_SHED_APPLIED
    if _LOAD_SHED_APPLIED:return
    _LOAD_SHED_APPLIED=True
    # v4 workers are included in start_v3_runtime's worker tuple at call time.
    v4.pre160_evidence_loop=_idle_worker('pre160-evidence-v3')
    v4.pre160_hardening_loop=_idle_worker('pre160-hardening-v5')
    # v7-v9 spawn additional audit/observability workers during start_runtime.
    v7._ensure_prewarm=lambda: print('[development-load-shed] paused=pre160-v7-deep-prewarm real_trading=false',flush=True)
    v7._ensure_queue_probe=lambda: print('[development-load-shed] paused=pre160-queue-durability real_trading=false',flush=True)
    v8._ensure_controlled_probes=lambda: print('[development-load-shed] paused=pre160-v8-controlled-probes real_trading=false',flush=True)
    v9._ensure_worker=lambda: print('[development-load-shed] paused=pre160-v9-brain-evidence real_trading=false',flush=True)


def development_load_board():
    return {
        'status':'ENABLED' if _LOAD_SHED_APPLIED else 'NOT_APPLIED',
        'mode':'DEVELOPMENT_PAPER',
        'paused_workers':['pre160-evidence-v3','pre160-hardening-v5','pre160-v7-deep-prewarm',
                          'pre160-queue-durability','pre160-v8-controlled-probes','pre160-v9-brain-evidence'],
        'critical_workers_preserved':['paper-v12-supervision','paper-runtime-lease-heartbeat','supabase-sync',
            'learning-sync','learning-engine','forward-outcome-sync','autonomous-simulator','autonomy-soak',
            'persistent-authority','closed-loop-paper','radar-core-worker-v11'],
        'production_audits_deferred':True,
        'broker_connected':False,'live_execution_allowed':False,'real_money_orders_allowed':False,
        'real_trading':False,
    }


def _run_block_d_once():
    global _BLOCK_D_RESULT
    try:
        _BLOCK_D_RESULT=block_d_validation()
    except Exception as exc:
        _BLOCK_D_RESULT={'status':'FAIL','error':f'{type(exc).__name__}: {str(exc)[:700]}','real_trading':False}
    print('[block-d-validation] '+json.dumps(_BLOCK_D_RESULT,sort_keys=True,default=str)[:5000],flush=True)


class ValidationV27Handler(base26.ValidationV26Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/development-load-v1':
            self._send(200,development_load_board());return
        if path=='/autonomous-simulator/block-d-v1':
            out=dict(_BLOCK_D_RESULT)
            out.update({'runtime':'v27','paper_accounting_ready':out.get('status')=='PASS',
                        'broker_connected':False,'live_execution_allowed':False,
                        'real_money_orders_allowed':False,'real_trading':False})
            self._send(200 if out.get('status')=='PASS' else 503,out);return
        super().do_GET()


def main():
    apply_development_load_shed()
    threading.Thread(target=_run_block_d_once,name='block-d-validation-once',daemon=True).start()
    base26.base25.base24.base23.base22.base21.base20._start_inherited_threads()
    threading.Thread(target=base26.base25.base24.base23._maturity_writer_loop,
                     name='paper-maturity-writer',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV27Handler).serve_forever()


if __name__=='__main__':main()
