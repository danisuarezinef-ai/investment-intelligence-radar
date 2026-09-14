"""PAPER runtime v25: v24 plus explicit development simulator mode.

Development restrictions may be relaxed for PAPER-only testing, while real-money and
broker execution remain impossible by policy.
"""
from __future__ import annotations
import os
import time
from http.server import ThreadingHTTPServer
import cloud_service_v24 as base24
import radar_development_paper_mode_v1 as development_mode

REAL_TRADING = False


def development_board():
    out = development_mode.assert_safety()
    out.update({
        "runtime": "v25",
        "purpose": "first_end_to_end_simulator_trial",
        "maturity_72h_blocks_development": False,
        "maturity_7d_blocks_development": False,
        "maturity_30d_blocks_development": False,
        "production_gates_preserved_separately": True,
        "real_trading": False,
    })
    return out


class ValidationV25Handler(base24.ValidationV24Handler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/autonomous-simulator/development-mode-v1":
            self._send(200, development_board())
            return
        super().do_GET()


def main():
    base24.base23.base22.base21.base20._start_inherited_threads()
    import threading
    threading.Thread(target=base24.base23._maturity_writer_loop,
                     name="paper-maturity-writer", daemon=True).start()
    port = int(os.environ.get("PORT") or 0)
    if port <= 0:
        while True:
            time.sleep(60)
    ThreadingHTTPServer(("0.0.0.0", port), ValidationV25Handler).serve_forever()


if __name__ == "__main__":
    main()
