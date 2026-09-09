"""Read-only integration surface for the ten-priority forward phase."""
from __future__ import annotations
from typing import Any
from radar_evidence_scorecard_v1 import scorecard
from radar_champion_challenger_v1 import compete,derive_forward_model_metrics
from radar_live_readiness_v2 import evaluate
from radar_cloud_contract_v4 import audit_contract
from radar_investment_ui_v4 import investment_home
REAL_TRADING=False

def priority_snapshot(*, account:dict[str,Any], decision:dict[str,Any]|None, opportunities:list[dict[str,Any]],
                      forward_records:list[dict[str,Any]], models:list[dict[str,Any]], endpoint_status:dict[str,Any],
                      freshness:dict[str,Any], promotion_metrics:dict[str,Any])->dict[str,Any]:
    sc=scorecard(forward_records)
    observed_models=models or derive_forward_model_metrics(forward_records)
    competition=compete(observed_models)
    cloud=audit_contract(endpoint_status,freshness)
    merged_metrics={**promotion_metrics,
                    'days':promotion_metrics.get('days',sc.get('forward_days')),
                    'decisions':promotion_metrics.get('decisions',sc.get('matured_decisions')),
                    'benchmark_coverage':promotion_metrics.get('benchmark_coverage',sc.get('benchmark_coverage')),
                    'cost_coverage':promotion_metrics.get('cost_coverage',sc.get('cost_coverage')),
                    'performance_verified':sc['performance_verified'],
                    'backfill_used':sc.get('backfill_used'),
                    'model_competition_ready':competition.get('status')=='READY'}
    promotion=evaluate(merged_metrics)
    ui=investment_home(account=account,decision=decision,opportunities=opportunities,scorecard=sc,cloud=cloud,
                       promotion=promotion,competition=competition)
    return {'ui':ui,'scorecard':sc,'model_metrics':observed_models,'model_competition':competition,
            'cloud_contract':cloud,'promotion':promotion,'architecture_complete_claim':False,
            'strategy_performance_verified':sc['performance_verified'],'execution_mode':'PAPER_OR_SHADOW_ONLY',
            'can_trade':False,'real_trading':False}
