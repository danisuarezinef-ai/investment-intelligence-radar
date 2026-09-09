"""Automatic degradation detection for data, model and evidence health."""
from __future__ import annotations
from radar_operational_pipeline_v1 import operational_pipeline
REAL_TRADING=False

def degradation_snapshot():
 p=operational_pipeline();market=p.get('market_telemetry') or {};fund=p.get('fundamental_coverage') or {};forward=p.get('forward_records') or [];intel=p.get('decision_intelligence') or []
 alerts=[]
 expected=int(market.get('assets_expected') or 0);observed=int(market.get('assets_observed') or 0)
 if expected and observed/expected<.9:alerts.append({'type':'MARKET_COVERAGE','severity':'HIGH','detail':f'{observed}/{expected}'})
 if int(fund.get('fundamentals_observed') or 0)==0:alerts.append({'type':'FUNDAMENTAL_COVERAGE','severity':'MEDIUM','detail':'no observed fundamentals'})
 verified=sum(1 for x in intel if (x.get('expected_return') or {}).get('optimizer_eligible') is True)
 if verified==0:alerts.append({'type':'EXPECTED_RETURN_EVIDENCE','severity':'INFO','detail':'no verified forward expected-return signals yet'})
 matured=len(forward)
 if matured==0:alerts.append({'type':'FORWARD_EVIDENCE','severity':'INFO','detail':'no matured forward outcomes yet'})
 return {'status':'DEGRADED' if any(a['severity'] in ('HIGH','MEDIUM') for a in alerts) else 'OK_OR_EVIDENCE_PENDING','alerts':alerts,'market_coverage_ratio':(observed/expected if expected else None),'verified_expected_return_signals':verified,'matured_forward_records':matured,'can_trade':False,'real_trading':False}
