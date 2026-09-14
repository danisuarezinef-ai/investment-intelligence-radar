"""PAPER runtime v30: v29 durability proof + generic radar-sync only.

Used for task 35. All other high-volume writers remain paused. REAL_TRADING=false.
"""
from __future__ import annotations
import os,time,threading
from http.server import ThreadingHTTPServer
import cloud_service_v29 as base29
import cloud_service_v4 as v4

REAL_TRADING=False
DEVELOPMENT_PAPER_MODE=True
_REACTIVATED=False


def apply_v30_mode():
    global _REACTIVATED
    if _REACTIVATED:return
    core=v4.base3.base_v2.base
    original_supabase_sync=core.supabase_sync_loop
    base29.apply_persistence_stability_mode()
    core.supabase_sync_loop=original_supabase_sync
    _REACTIVATED=True


def staged_board():
    b=base29.stability_board()
    b=dict(b)
    b.update({'runtime':'v30','generic_radar_sync':'REACTIVATED_FOR_STAGED_TEST','learning_sync':'PAUSED','real_trading':False})
    return b

class ValidationV30Handler(base29.ValidationV29Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/persistence-staged-v30':
            self._send(200,staged_board());return
        super().do_GET()


def main():
    apply_v30_mode()
    threading.Thread(target=base29.base27._run_block_d_once,name='block-d-validation-once',daemon=True).start()
    base29.base27.base26.base25.base24.base23.base22.base21.base20._start_inherited_threads()
    threading.Thread(target=base29.base27.base26.base25.base24.base23._maturity_writer_loop,name='paper-maturity-writer',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV30Handler).serve_forever()

if __name__=='__main__':main()
