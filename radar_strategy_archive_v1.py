"""Policy objects for Hall of Fame, Graveyard and Champion lineage persistence."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json

REAL_TRADING=False


def _id(payload):return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()[:24]


def hall_candidate(strategy,reason,*,category='PAPER_STRATEGY',min_evidence=70,min_v=260):
    s=strategy or {};v=float(s.get('v_score') or 0);e=float((s.get('v_components') or {}).get('evidence') or 0)
    eligible=v>=float(min_v) and e>=float(min_evidence)
    payload={'lineage':s.get('lineage_id') or s.get('competitor_key'),'reason':reason,'score':v,'category':category,
             'metadata':{'v_score':v,'evidence':e,'risk_label':s.get('risk_label'),'drawdown_pct':s.get('max_drawdown_pct')},
             'eligible':eligible,'real_trading':False}
    payload['archive_id']=_id(payload);return payload


def graveyard_candidate(strategy,reason,*,failed_regime=None,failed_horizon=None):
    s=strategy or {};payload={'lineage':s.get('lineage_id') or s.get('competitor_key'),'reason':reason,'score':s.get('v_score'),
        'failed_regime':failed_regime,'failed_horizon':failed_horizon,'metadata':{'v_score':s.get('v_score'),'drawdown_pct':s.get('max_drawdown_pct'),'v_components':s.get('v_components') or {}},
        'automatic_delete':False,'real_trading':False};payload['archive_id']=_id(payload);return payload


def champion_lineage_event(from_strategy,to_strategy,reason,governance):
    now=datetime.now(timezone.utc).isoformat();payload={'event_time':now,'from_key':(from_strategy or {}).get('competitor_key'),
        'to_key':(to_strategy or {}).get('competitor_key'),'reason':reason,'from_snapshot':from_strategy or {},'to_snapshot':to_strategy or {},
        'governance':governance or {},'scope':'SIMULATION_LEAGUE_ONLY','automatic_model_promotion':False,'can_trade':False,'real_trading':False}
    payload['event_hash']=_id(payload);return payload
