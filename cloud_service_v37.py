"""Runtime v37 — Block I learned-policy PAPER Trial 002."""
from __future__ import annotations
import json,threading,time,os
from http.server import ThreadingHTTPServer
import cloud_service_v36 as base36
import radar_block_i_trial_v1 as I
REAL_TRADING=False
_BLOCK_I={'status':'NOT_RUN','real_trading':False}; _LOCK=threading.RLock()
def _run_i_once():
    global _BLOCK_I
    try:r=I.block_i_validation()
    except Exception as exc:r={'status':'FAIL','error':str(exc)[:500],'paper_trial_002':'NOT_VERIFIED','real_trading':False}
    with _LOCK:_BLOCK_I=r
    print('[block-i-validation] '+json.dumps(r,sort_keys=True,default=str),flush=True)
def board():
    with _LOCK:return dict(_BLOCK_I)
class Handler(base36.Handler):
    def do_GET(self):
        if self.path.split('?',1)[0]=='/autonomous-simulator/block-i-v1':self._send(200,board());return
        super().do_GET()
def main():
    # Preserve v36 startup exactly, adding Trial 002 proof.
    base36.base35.base34.base30.apply_v30_mode()
    threading.Thread(target=base36.base35.base34.base29.base27._run_block_d_once,name='block-d-validation-once',daemon=True).start()
    threading.Thread(target=base36.base35.base34.base33.base32._run_block_e_once,name='block-e-validation-once',daemon=True).start()
    threading.Thread(target=base36.base35.base34.base33._run_fallback_once,name='block-e-fallback-once',daemon=True).start()
    threading.Thread(target=base36.base35.base34._run_block_f_once,name='block-f-validation-once',daemon=True).start()
    threading.Thread(target=base36.base35._run_block_g_once,name='block-g-validation-once',daemon=True).start()
    threading.Thread(target=base36._run_h_once,name='block-h-validation-once',daemon=True).start()
    threading.Thread(target=_run_i_once,name='block-i-validation-once',daemon=True).start()
    base36.base35.base34.base29.base27.base26.base25.base24.base23.base22.base21.base20._start_inherited_threads()
    threading.Thread(target=base36.base35.base34.base29.base27.base26.base25.base24.base23._maturity_writer_loop,name='paper-maturity-writer',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
if __name__=='__main__':main()
