"""Runtime v34 — Block F end-to-end PAPER pipeline validation.

Extends v33. It runs deterministic + live Block F validation at startup and exposes
one read-only diagnostic endpoint. No broker transport; REAL_TRADING=false.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import ThreadingHTTPServer

import cloud_service_v33 as base33
import cloud_service_v30 as base30
import cloud_service_v29 as base29
import radar_block_f_pipeline_v1 as block_f

REAL_TRADING=False
DEVELOPMENT_PAPER_MODE=True
_BLOCK_F={'status':'NOT_RUN','real_trading':False}
_LOCK=threading.RLock()


def _run_block_f_once():
    global _BLOCK_F
    deterministic=block_f.block_f_validation()
    try:
        live=block_f.live_block_f_probe('MSFT')
    except Exception as exc:
        live={'status':'FAILED','error':str(exc)[:500],'end_to_end_paper_pipeline':'NOT_VERIFIED','real_trading':False}
    ok=deterministic.get('status')=='PASS' and live.get('status')=='PASS'
    result={'status':'PASS' if ok else 'PARTIAL','deterministic':deterministic,'live':live,
            'five_brains':'VERIFIED' if deterministic.get('checks',{}).get('five_distinct_brains') else 'NOT_VERIFIED',
            'opportunity_radar_3_6_9':'VERIFIED' if deterministic.get('checks',{}).get('radar_3_6_9') else 'NOT_VERIFIED',
            'ensemble_regime':'VERIFIED' if deterministic.get('checks',{}).get('explicit_no_invertir') else 'NOT_VERIFIED',
            'decision_to_paper_execution':'VERIFIED' if ok else 'NOT_VERIFIED',
            'end_to_end_paper_pipeline':'VERIFIED' if ok else 'NOT_VERIFIED',
            'broker_connected':False,'live_execution_allowed':False,'real_money_orders_allowed':False,'real_trading':False}
    with _LOCK:_BLOCK_F=result
    print('[block-f-validation] '+json.dumps(result,sort_keys=True,default=str),flush=True)


def block_f_board():
    with _LOCK:return dict(_BLOCK_F)


class ValidationV34Handler(base33.ValidationV33Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/block-f-v1':
            self._send(200,block_f_board());return
        super().do_GET()


def main():
    base30.apply_v30_mode()
    threading.Thread(target=base29.base27._run_block_d_once,name='block-d-validation-once',daemon=True).start()
    threading.Thread(target=base33.base32._run_block_e_once,name='block-e-validation-once',daemon=True).start()
    threading.Thread(target=base33._run_fallback_once,name='block-e-fallback-once',daemon=True).start()
    threading.Thread(target=_run_block_f_once,name='block-f-validation-once',daemon=True).start()
    base29.base27.base26.base25.base24.base23.base22.base21.base20._start_inherited_threads()
    threading.Thread(target=base29.base27.base26.base25.base24.base23._maturity_writer_loop,name='paper-maturity-writer',daemon=True).start()
    port=int(__import__('os').environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV34Handler).serve_forever()

if __name__=='__main__':main()
