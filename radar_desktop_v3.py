"""Radar de Inversión desktop v3 adapter.

Patches PAPER-simulator startup/cycle behavior and hardens the Windows update UX
before loading the canonical v2 UI. The update control is always visible and the
app re-checks the stable channel while it stays open; no restart is required just
to discover an update.
"""
import json
import threading
import time
import urllib.request
import tkinter as tk

import radar_core
from radar_simulator_engine_v3 import run_simulator_cycle
from radar_ui_state import update_available

_ORIGINAL_START=radar_core.paper_start
_UPDATE_MANIFEST='https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/updates/update_manifest.json'
_UPDATE_CHECK_INTERVAL_MS=5*60*1000
_ORIGINAL_BUTTON_INIT=tk.Button.__init__
_ORIGINAL_BUTTON_FORGET=tk.Button.pack_forget
_ORIGINAL_MAINLOOP=tk.Tk.mainloop


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


def _is_update_button(widget):
    try:return str(widget.cget('text')) in ('ACTUALIZACIÓN','BUSCAR ACTUALIZACIÓN') or str(widget.cget('text')).startswith('ACTUALIZAR A v')
    except Exception:return False


def _button_init(self,*args,**kwargs):
    _ORIGINAL_BUTTON_INIT(self,*args,**kwargs)
    if _is_update_button(self):
        self.configure(text='BUSCAR ACTUALIZACIÓN')
        self.after_idle(lambda:self.pack(side='right',anchor='n') if self.winfo_exists() else None)


def _button_forget(self,*args,**kwargs):
    if _is_update_button(self):
        try:self.pack(side='right',anchor='n')
        except Exception:pass
        return None
    return _ORIGINAL_BUTTON_FORGET(self,*args,**kwargs)


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _find_update_button(root):
    for widget in _walk(root):
        if isinstance(widget,tk.Button) and _is_update_button(widget):return widget
    return None


def _check_update(root):
    def work():
        try:
            req=urllib.request.Request(_UPDATE_MANIFEST,headers={'User-Agent':'InvestmentIntelligenceRadarDesktop/1.5','Cache-Control':'no-cache'})
            manifest=json.loads(urllib.request.urlopen(req,timeout=12).read().decode('utf-8-sig'))
            remote=str(manifest.get('version') or '').strip()
            def apply():
                btn=_find_update_button(root)
                if not btn:return
                try:
                    import radar_desktop_v2 as ui
                    local=str(getattr(ui,'APP_VERSION','0.0.0'))
                    btn.configure(text=(f'ACTUALIZAR A v{remote}' if update_available(local,remote) else 'BUSCAR ACTUALIZACIÓN'),bg=('#16a34a' if update_available(local,remote) else '#2563eb'))
                    btn.pack(side='right',anchor='n')
                except Exception:
                    btn.configure(text='BUSCAR ACTUALIZACIÓN');btn.pack(side='right',anchor='n')
            root.after(0,apply)
        except Exception:
            def fail():
                btn=_find_update_button(root)
                if btn:
                    btn.configure(text='BUSCAR ACTUALIZACIÓN');btn.pack(side='right',anchor='n')
            root.after(0,fail)
    threading.Thread(target=work,daemon=True).start()


def _hot_mainloop(self,*args,**kwargs):
    def periodic():
        _check_update(self)
        if self.winfo_exists():self.after(_UPDATE_CHECK_INTERVAL_MS,periodic)
    self.after(1000,periodic)
    return _ORIGINAL_MAINLOOP(self,*args,**kwargs)


radar_core.paper_start=_start_nonblocking
radar_core.paper_step=_step_v3
tk.Button.__init__=_button_init
tk.Button.pack_forget=_button_forget
tk.Tk.mainloop=_hot_mainloop

# Importing the canonical UI after patching binds its callbacks to the hardened adapter.
from radar_desktop_v2 import *  # noqa: F401,F403,E402
