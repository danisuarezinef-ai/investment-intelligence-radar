"""Radar de Inversión desktop v3 adapter.

Patches PAPER-simulator startup/cycle behavior, starts the persistent autonomous
simulator independently of the Simulation Lab window, and hardens Windows update
UX. REAL_TRADING remains disabled.
"""
import json
import threading
import urllib.request
import tkinter as tk

import radar_core
from radar_simulator_engine_v3 import run_simulator_cycle
from radar_autonomous_simulator_v1 import autonomous_simulator_loop, simulator_status
from radar_ui_state import update_available

_ORIGINAL_START=radar_core.paper_start
_UPDATE_MANIFEST='https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/updates/update_manifest.json'
_UPDATE_CHECK_INTERVAL_MS=5*60*1000
_ORIGINAL_BUTTON_INIT=tk.Button.__init__
_ORIGINAL_BUTTON_FORGET=tk.Button.pack_forget
_ORIGINAL_MAINLOOP=tk.Tk.mainloop
_ORIGINAL_STRINGVAR_SET=tk.StringVar.set
_SIMULATOR_THREAD_STARTED=False


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
        except Exception as exc:
            try:radar_core.log('paper_simulator','ERROR',str(exc))
            except Exception:pass
    threading.Thread(target=warm_and_cycle,daemon=True).start()
    return radar_core.paper_status()


def _step_v3(force=False):
    return run_simulator_cycle(force=force).get('after') or radar_core.paper_status()


def _is_update_button(widget):
    try:
        text=str(widget.cget('text'))
        return (text in ('ACTUALIZACIÓN','BUSCAR ACTUALIZACIÓN','COMPROBANDO…') or
                text.startswith('ACTUALIZAR A v') or text.startswith('ACTUALIZADO · v') or
                text.startswith('ERROR · REINTENTAR'))
    except Exception:return False


def _walk(widget):
    yield widget
    for child in widget.winfo_children():yield from _walk(child)


def _find_update_button(root):
    for widget in _walk(root):
        if isinstance(widget,tk.Button) and _is_update_button(widget):return widget
    return None


def _local_version():
    try:
        import radar_desktop_v2 as ui
        return str(getattr(ui,'APP_VERSION','0.0.0'))
    except Exception:return '0.0.0'


def _check_update(root,manual=False):
    btn=_find_update_button(root)
    if manual and btn:
        try:btn.configure(text='COMPROBANDO…',bg='#2563eb');btn.pack(side='right',anchor='n')
        except Exception:pass
    def work():
        try:
            req=urllib.request.Request(_UPDATE_MANIFEST,headers={'User-Agent':'InvestmentIntelligenceRadarDesktop/1.6','Cache-Control':'no-cache'})
            manifest=json.loads(urllib.request.urlopen(req,timeout=12).read().decode('utf-8-sig'))
            remote=str(manifest.get('version') or '').strip();local=_local_version();available=update_available(local,remote)
            def apply():
                button=_find_update_button(root)
                if not button:return
                button.configure(text=(f'ACTUALIZAR A v{remote}' if available else f'ACTUALIZADO · v{local}'),bg=('#16a34a' if available else '#2563eb'))
                button.pack(side='right',anchor='n')
            root.after(0,apply)
        except Exception as exc:
            def fail():
                button=_find_update_button(root)
                if button:
                    button.configure(text='ERROR · REINTENTAR',bg='#dc2626')
                    button.pack(side='right',anchor='n')
                try:radar_core.log('update_check','ERROR',str(exc))
                except Exception:pass
            root.after(0,fail)
    threading.Thread(target=work,daemon=True).start()


def _manual_update(button):
    text=str(button.cget('text'))
    if text.startswith('ACTUALIZAR A v'):
        launch=getattr(button,'_radar_launch_updater',None)
        if callable(launch):return launch()
    _check_update(button.winfo_toplevel(),manual=True)


def _button_init(self,*args,**kwargs):
    launch=kwargs.get('command')
    _ORIGINAL_BUTTON_INIT(self,*args,**kwargs)
    if _is_update_button(self):
        self._radar_launch_updater=launch
        self.configure(text='BUSCAR ACTUALIZACIÓN',command=lambda b=self:_manual_update(b))
        self.after_idle(lambda:self.pack(side='right',anchor='n') if self.winfo_exists() else None)


def _button_forget(self,*args,**kwargs):
    if _is_update_button(self):
        try:self.pack(side='right',anchor='n')
        except Exception:pass
        return None
    return _ORIGINAL_BUTTON_FORGET(self,*args,**kwargs)


def _simulator_aware_stringvar_set(self,value):
    # The canonical UI writes ACTIVA/PAUSADA into the simulator status variable.
    # Enrich that existing label without coupling the background worker to the UI.
    if value in ('ACTIVA','PAUSADA','Sin iniciar'):
        try:
            s=simulator_status()
            if s.get('active'):
                value='ACTIVA · gen {} · {} exp · {} ciclos'.format(
                    s.get('generation',1),s.get('completed_experiments',0),s.get('completed_cycles',0))
            elif value=='ACTIVA':value='PAUSADA'
        except Exception:pass
    return _ORIGINAL_STRINGVAR_SET(self,value)


def _hot_mainloop(self,*args,**kwargs):
    global _SIMULATOR_THREAD_STARTED
    if not _SIMULATOR_THREAD_STARTED:
        _SIMULATOR_THREAD_STARTED=True
        threading.Thread(target=autonomous_simulator_loop,name='desktop-autonomous-simulator',daemon=True).start()
    def periodic():
        _check_update(self)
        if self.winfo_exists():self.after(_UPDATE_CHECK_INTERVAL_MS,periodic)
    self.after(1000,periodic)
    return _ORIGINAL_MAINLOOP(self,*args,**kwargs)


radar_core.paper_start=_start_nonblocking
radar_core.paper_step=_step_v3
tk.Button.__init__=_button_init
tk.Button.pack_forget=_button_forget
tk.StringVar.set=_simulator_aware_stringvar_set
tk.Tk.mainloop=_hot_mainloop

from radar_desktop_v2 import *  # noqa: F401,F403,E402
