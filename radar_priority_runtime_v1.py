"""Read-only integration surface for the ten-priority forward phase."""
from __future__ import annotations
from typing import Any
from radar_evidence_scorecard_v1 import scorecard
from radar_champion_challenger_v1 import compete
from radar_live_readiness_v2 import evaluate
from radar_cloud_contract_v4 import audit_contract
from radar_investment_ui_v4 import investment_home
REAL_TRADING=False

def priority_snapshot(*, account:dict[str,Any], decision:dict[str,Any]|None, opportunities:list[dict[str,Any]],
                      forward_records:list[dict[str,Any]], models:list[dict[str,Any]], endpoint_status:dict[str,Any],
                      freshness:dict[str,Any], promotion_metrics:dict[str,Any])->dict[str,Any]:
    sc=scorecard(forward_records); competition=compete(models); cloud=audit_contract(endpoint_status,freshness)
    promotion=evaluate({**promotion_metrics,'performance_verified':sc['performance_verified']})
    ui=investment_home(account=account,decision=decision,opportunities=opportunities,scorecard=sc,cloud=cloud,promotion=promotion)
    return {'ui':ui,'scorecard':sc,'model_competition':competition,'cloud_contract':cloud,'promotion':promotion,
            'architecture_complete_claim':False,'strategy_performance_verified':sc['performance_verified'],
            'can_trade':False,'real_trading':False}
