"""Safe legacy cleanup registry.

No runtime deletion is performed here. Components are marked removable only when a
replacement exists and the current validation suite is green.
"""
from __future__ import annotations
REAL_TRADING=False

LEGACY={
 'dashboard_v2':{'replacement':'radar_dashboard_v3','state':'ADAPTER_ONLY','delete_now':False},
 'forward_ledger_v1':{'replacement':'radar_forward_engine/prediction_ledger','state':'SUPERSEDED','delete_now':False},
 'paper_portfolio_v4':{'replacement':'radar_paper_portfolio_v5','state':'SUPERSEDED','delete_now':False},
 'degradation_watch_v1':{'replacement':'radar_degradation_watch_v2','state':'SUPERSEDED_AFTER_VALIDATION','delete_now':False},
 'old_desktop_update_visibility':{'replacement':'radar_desktop_v3 hot-update adapter','state':'COMPATIBILITY_LAYER','delete_now':False},
}

def legacy_cleanup_plan(ci_green=False):
    rows=[]
    for name,meta in LEGACY.items():
        x={'component':name,**meta}
        x['eligible_for_removal_review']=bool(ci_green and meta['state'].startswith('SUPERSEDED'))
        rows.append(x)
    return {'status':'REVIEW_ONLY','components':rows,'automatic_delete':False,'real_trading':False}
