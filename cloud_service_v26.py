"""PAPER runtime v26: v25 plus Block D economic accounting validation."""
from __future__ import annotations
import os,time,threading
from http.server import ThreadingHTTPServer
import cloud_service_v25 as base25
from radar_block_d_validation_v1 import block_d_validation

REAL_TRADING=False


def block_d_board():
    out=block_d_validation()
    out.update({
        'runtime':'v26',
        'block':'D',
        'paper_accounting_ready':out.get('status')=='PASS',
        'broker_connected':False,
        'live_execution_allowed':False,
        'real_money_orders_allowed':False,
        'real_trading':False,
    })
    return out


class ValidationV26Handler(base25.ValidationV25Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/block-d-v1':
            out=block_d_board()
            self._send(200 if out.get('status')=='PASS' else 503,out)
            return
        super().do_GET()


def main():
    base25.base24.base23.base22.base21.base20._start_inherited_threads()
    threading.Thread(target=base25.base24.base23._maturity_writer_loop,
                     name='paper-maturity-writer',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV26Handler).serve_forever()


if __name__=='__main__':main()
