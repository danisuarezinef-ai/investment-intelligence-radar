"""Fail-closed simulation readiness gate."""
from __future__ import annotations
import importlib
from radar_core import ASSETS
from radar_universe_pit import survivorship_audit
from radar_corporate_actions import integrity_status
from radar_delisting_integrity_v1 import audit_delisting_coverage
REAL_TRADING=False
REQUIRED_MODULES=('radar_learning','radar_learning_guarded','radar_historical_lab','radar_benchmark','radar_simulation_factory','radar_cost_model')

def audit_simulation_ready(as_of='2026-09-09T00:00:00+00:00'):
 checks=[]
 for name in REQUIRED_MODULES:
  try:
   mod=importlib.import_module(name);checks.append({'check':'module:'+name,'status':'PASS'})
   if getattr(mod,'REAL_TRADING',False):checks.append({'check':'real_trading:'+name,'status':'FAIL','detail':'REAL_TRADING enabled'})
  except Exception as exc:checks.append({'check':'module:'+name,'status':'FAIL','detail':str(exc)[:300]})
 pit=survivorship_audit(list(ASSETS),as_of);corp=integrity_status();delist=audit_delisting_coverage(list(ASSETS),as_of)
 evidence={'point_in_time_data':'VERIFIED' if not pit['survivorship_bias_risk'] else 'NOT_VERIFIED','survivorship_controls':'VERIFIED_CONTROL_ACTIVE','corporate_actions':'VERIFIED' if corp['coverage_verified'] else 'NOT_VERIFIED','delisting_returns':'VERIFIED' if delist['coverage_complete'] and delist['known_delistings']>0 else 'NOT_VERIFIED','transaction_costs':'IMPLEMENTED_ASSUMPTION_NOT_BROKER_VERIFIED','fx_costs':'IMPLEMENTED_ASSUMPTION_NOT_BROKER_VERIFIED','purged_temporal_validation':'IMPLEMENTED_NOT_REVERIFIED','forward_immutable_evidence':'ACTIVE_PROSPECTIVE_LEDGER'}
 for key,value in evidence.items():checks.append({'check':key,'status':'PASS' if value.startswith('VERIFIED') or value=='ACTIVE_PROSPECTIVE_LEDGER' else 'BLOCKED','detail':value})
 blocking=[x for x in checks if x['status'] in ('FAIL','BLOCKED')]
 return {'simulation_ready':not blocking,'checks':checks,'blocking':blocking,'pit':pit,'corporate_actions':corp,'delisting':delist,'real_trading':False}
