"""Operational dashboard v3: evidence-first paper/shadow state with legacy render compatibility."""
from __future__ import annotations
from radar_core import con
from radar_forward_engine import forward_health
from radar_operational_pipeline_v1 import operational_pipeline
from radar_paper_portfolio_v5 import paper_portfolio_v5_status
from radar_learning_engine_v3 import learn_v3
from radar_learning import active_model
from radar_scoring_v2 import lists_369_v2
from radar_benchmark import benchmark_agents

REAL_TRADING=False


def _learning_records():
    c=con()
    try:rows=c.execute('select asset,horizon,target_date,payload,outcome,evaluated_at from prediction_ledger where outcome is not null').fetchall()
    except Exception:c.close();return []
    c.close();import json;out=[]
    for asset,horizon,target,payload,outcome,evaluated_at in rows:
        try:p=json.loads(payload) if isinstance(payload,str) else (payload or {})
        except Exception:p={}
        try:o=json.loads(outcome) if isinstance(outcome,str) else (outcome or {})
        except Exception:o={}
        out.append({'symbol':asset,'horizon':horizon,'target_date':target,'evaluated_at':evaluated_at,'signals':p.get('features') or {},'regime':(p.get('uncertainty') or {}).get('regime') if isinstance(p.get('uncertainty'),dict) else None,'immutable':True,'matured':True,'backfilled':bool(o.get('backfilled',False)),'net_return':o.get('net_return'),'excess_return':o.get('excess_return'),'cost_aware':o.get('cost') is not None and bool(o.get('cost_model')),'benchmark_aware':o.get('benchmark_return') is not None and bool(o.get('benchmark_name'))})
    return out


def _counts():
    c=con();out={}
    for k,t in {'predictions':'predictions','outcomes':'prediction_outcomes','learning_cycles':'learning_cycles','model_evaluations':'model_evaluations'}.items():
        try:out[k]=c.execute('select count(*) from '+t).fetchone()[0]
        except Exception:out[k]=0
    c.close();return out


def dashboard_payload_v3():
    paper=paper_portfolio_v5_status();forward=forward_health();pipeline=operational_pipeline();learning=learn_v3(_learning_records())
    market=(pipeline.get('market_telemetry') or {});optimizer=pipeline.get('optimizer') or {};evidence_state='MATURE' if int(forward.get('matured') or 0)>0 else 'INSUFFICIENT_EVIDENCE'
    return {'model':active_model(),'lists_369':lists_369_v2(),'benchmarks':benchmark_agents(),'counts':_counts(),'paper':paper,'balance':{'cash':paper.get('cash'),'equity':(paper.get('equity') or {}).get('total'),'drawdown_pct':(paper.get('equity') or {}).get('drawdown_pct')},'positions':paper.get('positions') or [],'costs_paid':paper.get('costs_paid'),'forward_evidence':forward,'evidence_state':evidence_state,'learning':learning,'learning_state':'ACTIVE_FORWARD_ONLY' if learning.get('promotion_grade_records') else 'WAITING_FOR_MATURE_EVIDENCE','market':{'assets_expected':market.get('assets_expected'),'assets_observed':market.get('assets_observed'),'coverage_complete':market.get('coverage_complete'),'provider_health':market.get('provider_health')},'optimizer':optimizer,'optimizer_state':optimizer.get('status'),'cloud_operational':True,'performance_claim':'INSUFFICIENT_EVIDENCE' if evidence_state!='MATURE' else 'FORWARD_EVIDENCE_AVAILABLE_NOT_YET_REAL_TRADING','trading_real':False,'real_trading':False,'can_trade':False}
