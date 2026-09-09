"""Explicit reconciliation ledger for superseded legacy PRs.

This module documents what was preserved from PRs #7, #10 and #20 and what was
superseded by current architecture. It performs no code mutation at runtime.
"""
from __future__ import annotations
REAL_TRADING=False

RECONCILIATION={
  7:{'title':'Forward Evidence v1','status':'SUPERSEDED_AFTER_RECONCILIATION','preserved':['radar_universe_pit.py','immutable forward-evidence semantics'],'superseded':['radar_forward_ledger.py -> radar_forward_engine.py/prediction_ledger']},
  10:{'title':'Simulation Ready v1','status':'SUPERSEDED_AFTER_RECONCILIATION','preserved':['radar_corporate_actions.py','radar_cost_model.py','radar_simulation_factory.py','radar_simulation_readiness.py'],'superseded':['legacy simulation promotion semantics']},
  20:{'title':'Decision v3 causal','status':'SUPERSEDED_AFTER_RECONCILIATION','preserved':['radar_causal_scoring_v2.py','radar_causal_runtime_v2.py','event deduplication and bounded causal adjustment'],'superseded':['any causal path that could bypass current abstention/risk/promotion gates']},
}

def reconciliation_status():
    return {'prs':RECONCILIATION,'mechanical_merge_required':False,'real_trading':False}
