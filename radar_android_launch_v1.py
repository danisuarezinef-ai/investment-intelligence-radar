"""Android launch contracts for Radar PAPER mobile app.
UI is observer/controller only; cloud durable PAPER state is authoritative.
"""
from __future__ import annotations
REAL_TRADING=False
SAFE_PREFS=("window","metric","selected_tab","expanded_panels","notifications")
def sanitize_preferences(x):
    x=x if isinstance(x,dict) else {}
    return {k:x[k] for k in SAFE_PREFS if k in x}
def resume_mode(network,cloud_ok,exact_restore,reconciled,lease_ok):
    if not network:return {"mode":"OFFLINE_READ_ONLY","paper_mutation":False}
    if not cloud_ok:return {"mode":"CLOUD_UNAVAILABLE_READ_ONLY","paper_mutation":False}
    if not (exact_restore and reconciled and lease_ok):return {"mode":"RECOVERY_BLOCKED","paper_mutation":False}
    return {"mode":"CLOUD_OBSERVER","paper_mutation":False}
def install_contract():
    return {"single_install":True,"manual_setup":False,"python_required":False,"terminal_required":False,
            "real_trading":False,"state_authority":"cloud"}
