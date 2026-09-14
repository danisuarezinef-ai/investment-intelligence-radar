"""Runtime v35 — Block G autonomous PAPER learning validation."""
from __future__ import annotations
import json, threading, time
from http.server import ThreadingHTTPServer
import cloud_service_v34 as base34
import radar_block_g_learning_v1 as block_g

REAL_TRADING=False
DEVELOPMENT_PAPER_MODE=True
_BLOCK_G={'status':'NOT_RUN','real_trading':False}
_LOCK=threading.RLock()

def _run_block_g_once():
    global _BLOCK_G
    try: result=block_g.block_g_validation()
    except Exception as exc: result={'status':'FAIL','error':str(exc)[:500],'autonomous_learning_loop':'NOT_VERIFIED','real_trading':False}
    with _LOCK: _BLOCK_G=result
    print('[block-g-validation] '+json.dumps(result,sort_keys=True,default=str),flush=True)

def block_g_board():
    with _LOCK:return dict(_BLOCK_G)

class ValidationV35Handler(base34.ValidationV34Handler):
    def do_GET(self):
        if self.path.split('?',1)[0]=='/autonomous-simulator/block-g-v1':
            self._send(200,block_g_board());return
        super().do_GET()

def main():
    base34.base30.apply_v30_mode()
    threading.Thread(target=base34.base29.base27._run_block_d_once,name='block-d-validation-once',daemon=True).start()
    threading.Thread(target=base34.base33.base32._run_block_e_once,name='block-e-validation-once',daemon=True).start()
    threading.Thread(target=base34.base33._run_fallback_once,name='block-e-fallback-once',daemon=True).start()
    threading.Thread(target=base34._run_block_f_once,name='block-f-validation-once',daemon=True).start()
    threading.Thread(target=_run_block_g_once,name='block-g-validation-once',daemon=True).start()
    base34.base29.base27.base26.base25.base24.base23.base22.base21.base20._start_inherited_threads()
    threading.Thread(target=base34.base29.base27.base26.base25.base24.base23._maturity_writer_loop,name='paper-maturity-writer',daemon=True).start()
    port=int(__import__('os').environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV35Handler).serve_forever()

if __name__=='__main__':main()
