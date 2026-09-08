"""Fail-soft runtime bridge for Simulation/Memory/Learning/Champion."""
from __future__ import annotations
import traceback
from radar_orchestrator_v2 import fast_cycle,deep_learning_cycle,system_v2_health
from radar_learning import detect_regime
from radar_causal_runtime_v2 import refresh_causal_if_due
REAL_TRADING=False

def safe_fast_cycle():
    causal=None
    try:causal=refresh_causal_if_due()
    except Exception as exc:causal={'refreshed':False,'error':str(exc),'real_trading':False}
    try:
        out=fast_cycle();out['causal_graph']=causal;out['ok']=True;out['real_trading']=False;return out
    except Exception as exc:return {'ok':False,'error':str(exc),'trace':traceback.format_exc(limit=4),'causal_graph':causal,'real_trading':False}

def safe_deep_cycle(regime=None):
    causal=None
    try:causal=refresh_causal_if_due(force=True)
    except Exception as exc:causal={'refreshed':False,'error':str(exc),'real_trading':False}
    try:
        regime_info=None
        if not regime or str(regime).lower() in ('unknown','auto'):
            regime_info=detect_regime(store=True);regime=(regime_info or {}).get('regime') or 'unknown'
        out=deep_learning_cycle(regime=regime);out['causal_graph']=causal;out['ok']=True;out['regime']=regime;out['regime_detection']=regime_info;out['real_trading']=False;return out
    except Exception as exc:return {'ok':False,'error':str(exc),'trace':traceback.format_exc(limit=4),'causal_graph':causal,'real_trading':False}

def runtime_snapshot():
    try:
        out=system_v2_health();out['ok']=True;out['real_trading']=False;return out
    except Exception as exc:return {'ok':False,'error':str(exc),'real_trading':False}
