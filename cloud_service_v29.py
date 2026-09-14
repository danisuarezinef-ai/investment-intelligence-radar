"""PAPER runtime v29: persistence stability isolation for DEVELOPMENT_PAPER.

Purpose: prove lease/checkpoint/exact restore/reconciliation without concurrent noncritical
writers masking the root cause. All paused workers remain fail-closed and PAPER only.
REAL_TRADING is permanently false.
"""
from __future__ import annotations
import os,time,threading,json
from http.server import ThreadingHTTPServer
import cloud_service_v27 as base27
import cloud_service_v4 as v4

REAL_TRADING=False
DEVELOPMENT_PAPER_MODE=True
_STABILITY_APPLIED=False


def _idle(label):
    def worker(*args,**kwargs):
        print(f'[persistence-stability] paused={label} reason=isolate-durable-transport real_trading=false',flush=True)
        while True: time.sleep(3600)
    return worker


def apply_persistence_stability_mode():
    global _STABILITY_APPLIED
    if _STABILITY_APPLIED:return
    _STABILITY_APPLIED=True
    base27.apply_development_load_shed()
    b3=v4.base3
    core=b3.base_v2.base
    # Pause noncritical/high-volume writers while preserving v12 exact supervision,
    # distributed lease heartbeat, checkpoint persistence/reconciliation and HTTP health.
    core.supabase_sync_loop=_idle('supabase-sync')
    core.learning_sync_loop=_idle('learning-sync')
    b3._resilient_learning_loop=_idle('learning-engine')
    b3._forward_outcome_sync_loop=_idle('forward-outcome-sync')
    b3.autonomous_simulator_loop=_idle('autonomous-simulator')
    b3.soak_loop=_idle('autonomy-soak')
    b3._authority_sync_loop=_idle('persistent-authority')
    v4.closed_loop_runtime_loop=_idle('closed-loop-paper')


def stability_board():
    return {
      'status':'ENABLED' if _STABILITY_APPLIED else 'NOT_APPLIED',
      'mode':'DEVELOPMENT_PAPER_PERSISTENCE_STABILITY',
      'purpose':'prove_durable_persistence_without_writer_contention',
      'preserved':['paper-v12-supervision','paper-runtime-lease-heartbeat','paper-engine-checkpoint','durable-reconciliation','http-health','block-d-validation'],
      'temporarily_paused':['supabase-sync','learning-sync','learning-engine','forward-outcome-sync','autonomous-simulator','autonomy-soak','persistent-authority','closed-loop-paper'],
      'evidence_policy':'PAUSED_COMPONENTS_ARE_NOT_VERIFIED_AND_CANNOT_EARN_FORWARD_MATURITY',
      'broker_connected':False,'live_execution_allowed':False,'real_money_orders_allowed':False,'real_trading':False,
    }

class ValidationV29Handler(base27.ValidationV27Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/persistence-stability-v1':
            self._send(200,stability_board());return
        super().do_GET()


def main():
    apply_persistence_stability_mode()
    threading.Thread(target=base27._run_block_d_once,name='block-d-validation-once',daemon=True).start()
    base27.base26.base25.base24.base23.base22.base21.base20._start_inherited_threads()
    # Maturity writer remains active but fail-closed; it cannot earn maturity unless all
    # original qualifying conditions are satisfied.
    threading.Thread(target=base27.base26.base25.base24.base23._maturity_writer_loop,
                     name='paper-maturity-writer',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV29Handler).serve_forever()

if __name__=='__main__':main()
