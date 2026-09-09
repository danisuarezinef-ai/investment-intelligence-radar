"""Production readiness scorecard with explicit verification classes."""
from __future__ import annotations
from radar_operational_pipeline_v1 import operational_pipeline
from radar_simulation_readiness import audit_simulation_ready
from radar_degradation_watch_v1 import degradation_snapshot
REAL_TRADING=False

def production_readiness():
 p=operational_pipeline();sim=audit_simulation_ready();deg=degradation_snapshot();w=p.get('wiring_status') or {};rows=[]
 def add(component,status,detail=None):rows.append({'component':component,'status':status,'detail':detail})
 add('market_data','LIVE' if (p.get('market_telemetry') or {}).get('assets_observed') else 'PARTIAL')
 add('fundamentals','LIVE' if int((p.get('fundamental_coverage') or {}).get('fundamentals_observed') or 0)>0 else 'PARTIAL')
 add('survivorship_control','LIVE' if w.get('survivorship_control') else 'NOT_VERIFIED')
 add('valuation','LIVE' if w.get('valuation_engine_v1') else 'NOT_VERIFIED')
 add('expected_return','PARTIAL' if w.get('expected_return') else 'NOT_VERIFIED',w.get('expected_return'))
 add('optimizer','PARTIAL' if w.get('portfolio_optimizer_v3') else 'NOT_VERIFIED',w.get('portfolio_optimizer_v3'))
 add('forward_evidence','PARTIAL' if len(p.get('forward_records') or [])<20 else 'LIVE')
 add('simulation_integrity','LIVE' if sim.get('simulation_ready') else 'BLOCKED',len(sim.get('blocking') or []))
 add('degradation_watch','LIVE',deg.get('status'))
 add('real_trading','BLOCKED','REAL_TRADING=false by design')
 return {'components':rows,'overall':'PAPER_SHADOW_OPERATIONAL' if not any(x['status']=='NOT_VERIFIED' for x in rows[:4]) else 'PARTIAL','simulation_ready':sim.get('simulation_ready'),'degradation':deg,'can_trade':False,'real_trading':False}
