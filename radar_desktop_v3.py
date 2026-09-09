"""Radar de Inversión desktop v3 adapter.

Patches only PAPER-simulator startup/cycle behavior before loading the canonical
v2 UI. History warmup runs in the background so the GUI does not freeze.
"""
import threading
import radar_core
from radar_simulator_engine_v3 import run_simulator_cycle

_ORIGINAL_START=radar_core.paper_start


def _start_nonblocking(amount=1000.0):
    radar_core.init_db(); amount=max(100.0,float(amount))
    c=radar_core.con()
    c.execute('delete from paper_positions');c.execute('delete from paper_trades');c.execute('delete from portfolio_values')
    c.execute('insert or replace into paper_account(id,cash,initial_cash,enabled,last_rebalance) values(1,?,?,1,null)',(amount,amount))
    c.commit();c.close()
    def warm_and_cycle():
        try:
            if not radar_core.history_ready():radar_core.collect_history()
            run_simulator_cycle(force=True)
        except Exception as e:
            try:radar_core.log('paper_simulator','ERROR',str(e))
            except Exception:pass
    threading.Thread(target=warm_and_cycle,daemon=True).start()
    return radar_core.paper_status()


def _step_v3(force=False):
    return run_simulator_cycle(force=force).get('after') or radar_core.paper_status()

radar_core.paper_start=_start_nonblocking
radar_core.paper_step=_step_v3

# Importing the canonical UI after patching binds its from-import callbacks to v3.
from radar_desktop_v2 import *  # noqa: F401,F403,E402
