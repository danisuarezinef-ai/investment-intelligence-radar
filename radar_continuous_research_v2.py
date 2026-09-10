"""Continuous autonomous research loop for the Radar brain."""
from __future__ import annotations
import time
from radar_core import collect_history
from radar_simulation_v2 import _series_by_day
from radar_experiment_brain_v1 import generate_experiments
from radar_experiment_memory_v2 import diversity_filter,remember,memory_snapshot
from radar_simulation_research_v5 import research_protocol
REAL_TRADING=False


def run_research_batch(generation=1,max_experiments=6,min_history_days=90):
    days=_series_by_day()
    if len(days)<int(min_history_days):
        collect_history();days=_series_by_day()
    if len(days)<int(min_history_days):return {'status':'HOLD','reason':'INSUFFICIENT_HISTORY','history_days':len(days),'real_trading':False}
    candidates=diversity_filter(generate_experiments(generation))[:int(max_experiments)];results=[]
    for e in candidates:
        cfg=e['configuration'];protocol=research_protocol(cfg,days);base=protocol['base'];wf=protocol['walk_forward'];stress=protocol['stress'];gate=protocol['gate'];score=protocol['research_score']
        row={'experiment_id':e['experiment_id'],'configuration':cfg,'completed':base.get('completed',False),'return_pct':base.get('return_pct'),'alpha_pct':0.0,'max_drawdown_pct':base.get('max_drawdown_pct'),'costs':base.get('costs'),'sharpe':base.get('sharpe'),'sortino':base.get('sortino'),'walk_forward':wf,'stress':stress,'gate':gate,'research_score':score,'ranking_dimensions':protocol.get('ranking_dimensions'),'evidence_class':'SIMULATED_RESEARCH_OOS_ONLY','real_trading':False}
        remember(cfg,status='PASS' if gate['status']=='PASS_RESEARCH' else 'REJECTED',reason=','.join(gate['blockers']) if gate['blockers'] else None,generation=generation,research_score=score,stage='SHADOW_REVIEW' if gate['status']=='PASS_RESEARCH' else 'GRAVEYARD');results.append(row)
    winners=sorted([r for r in results if r['gate']['status']=='PASS_RESEARCH'],key=lambda r:float(r.get('research_score') or -1e9),reverse=True)
    return {'status':'COMPLETED','generation':int(generation),'history_days':len(days),'tested':len(results),'shadow_candidates':[{'experiment_id':r['experiment_id'],'research_score':r['research_score'],'configuration':r['configuration']} for r in winners[:3]],'results':results,'memory':memory_snapshot(10),'research_protocol':'STRICT_OOS_CHRONOLOGICAL_V5','funnel':'SIMULATED→SHADOW_REVIEW_OR_GRAVEYARD; PAPER_REQUIRES_FORWARD_GATE','evidence_class':'SIMULATED_RESEARCH_OOS_ONLY','automatic_live_promotion':False,'real_trading':False}


def continuous_research_loop(interval_seconds=21600):
    generation=1
    while True:
        try:
            r=run_research_batch(generation);print(f'[research-brain] generation={generation} status={r.get("status")} tested={r.get("tested",0)} candidates={len(r.get("shadow_candidates",[]))}',flush=True)
            if r.get('status')=='COMPLETED':generation+=1
        except Exception as exc:print('[research-brain] ERROR '+repr(exc),flush=True)
        time.sleep(max(1800,int(interval_seconds)))
