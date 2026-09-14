"""PAPER runtime v32: v30 persistence stage + Block E market-data validation.

Runs deterministic and external provider probes once at startup. It does not enable any
broker transport or real-money execution. REAL_TRADING=false.
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import ThreadingHTTPServer

import cloud_service_v30 as base30
import cloud_service_v29 as base29
import radar_block_e_market_data_v2 as block_e

REAL_TRADING=False
DEVELOPMENT_PAPER_MODE=True
_BLOCK_E={'status':'NOT_RUN','real_trading':False}
_LOCK=threading.RLock()


def _run_block_e_once():
    global _BLOCK_E
    deterministic=block_e.deterministic_block_e_validation()
    try:
        live=block_e.live_block_e_probe()
    except Exception as exc:
        live={'status':'FAILED','error':str(exc)[:500],'market_data_test_set':'NOT_READY','real_trading':False}
    result={
        'status':'PASS' if deterministic.get('status')=='PASS' and live.get('status')=='PASS' else 'PARTIAL',
        'deterministic':deterministic,
        'live':live,
        'market_data_test_set':'READY' if deterministic.get('status')=='PASS' and live.get('status')=='PASS' else 'PARTIAL',
        'broker_connected':False,'live_execution_allowed':False,'real_money_orders_allowed':False,'real_trading':False,
    }
    with _LOCK:_BLOCK_E=result
    print('[block-e-validation] '+json.dumps(result,sort_keys=True,default=str),flush=True)


def block_e_board():
    with _LOCK:return dict(_BLOCK_E)


class ValidationV32Handler(base30.ValidationV30Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/block-e-v1':
            self._send(200,block_e_board());return
        super().do_GET()


def main():
    base30.apply_v30_mode()
    threading.Thread(target=base29.base27._run_block_d_once,name='block-d-validation-once',daemon=True).start()
    threading.Thread(target=_run_block_e_once,name='block-e-validation-once',daemon=True).start()
    base29.base27.base26.base25.base24.base23.base22.base21.base20._start_inherited_threads()
    threading.Thread(target=base29.base27.base26.base25.base24.base23._maturity_writer_loop,name='paper-maturity-writer',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV32Handler).serve_forever()

if __name__=='__main__':main()
