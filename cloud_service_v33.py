"""PAPER runtime v33: v32 Block E + real secondary-provider proof."""
from __future__ import annotations
import json,os,threading,time
from http.server import ThreadingHTTPServer
import cloud_service_v32 as base32
import cloud_service_v30 as base30
import cloud_service_v29 as base29
import radar_block_e_external_fallback_v1 as fallback

REAL_TRADING=False
DEVELOPMENT_PAPER_MODE=True
_FALLBACK={'status':'NOT_RUN','real_trading':False}
_LOCK=threading.RLock()


def _run_fallback_once():
    global _FALLBACK
    try: out=fallback.external_fallback_probe()
    except Exception as exc: out={'status':'FAILED','error':str(exc)[:500],'real_trading':False}
    with _LOCK:_FALLBACK=out
    print('[block-e-fallback] '+json.dumps(out,sort_keys=True,default=str),flush=True)


def fallback_board():
    with _LOCK:return dict(_FALLBACK)

class ValidationV33Handler(base32.ValidationV32Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/block-e-fallback-v1':
            self._send(200,fallback_board());return
        super().do_GET()


def main():
    base30.apply_v30_mode()
    threading.Thread(target=base29.base27._run_block_d_once,name='block-d-validation-once',daemon=True).start()
    threading.Thread(target=base32._run_block_e_once,name='block-e-validation-once',daemon=True).start()
    threading.Thread(target=_run_fallback_once,name='block-e-fallback-once',daemon=True).start()
    base29.base27.base26.base25.base24.base23.base22.base21.base20._start_inherited_threads()
    threading.Thread(target=base29.base27.base26.base25.base24.base23._maturity_writer_loop,name='paper-maturity-writer',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV33Handler).serve_forever()

if __name__=='__main__':main()
