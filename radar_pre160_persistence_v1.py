"""Durable Supabase sync client for pre-1.6 PAPER strategy evaluation."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime,timezone

from radar_agents import agents_status
from radar_champion_portfolio import champion_status
from radar_simulator_league_v1 import RISK_PROFILES,league_status
from radar_simulator_vscore_v1 import competitor_observations
from radar_strategy_evaluation_v1 import competitor_evaluation
from radar_operational_pipeline_v1 import operational_pipeline
from radar_validation_runtime_v3 import validation_runtime_v3
from radar_pre160_runtime_v2 import enrich_scorecards

REAL_TRADING=False
DEFAULT_URL='https://wvmiludqzdepqmjhfwos.supabase.co/functions/v1/radar-pre160-evaluation'
URL=os.environ.get('SUPABASE_PRE160_EVALUATION_URL',DEFAULT_URL).strip()
TOKEN=os.environ.get('RADAR_SYNC_TOKEN','').strip()
NODE_ID=os.environ.get('RADAR_NODE_ID','cloud-primary').strip() or 'cloud-primary'


def _fingerprint(key,row):
    fields={k:row.get(k) for k in ('symbol','entry_ts','exit_ts','qty','entry_price','exit_price','entry_capital')}
    raw=json.dumps({'competitor':key,'fields':fields},sort_keys=True,separators=(',',':'),default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _post(payload,timeout=40):
    if not (URL and TOKEN):return {'ok':False,'status':'AUTHORITY_DISABLED','real_trading':False}
    data=json.dumps(payload,ensure_ascii=False,default=str).encode()
    req=urllib.request.Request(URL,data=data,method='POST',headers={'Content-Type':'application/json','X-Radar-Token':TOKEN,'User-Agent':'RadarPre160Evaluation/2.0'})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body=exc.read().decode('utf-8','replace');raise RuntimeError(f'pre160 evaluation HTTP {exc.code}: {body[:1200]}') from exc


def _base_evaluations():
    statuses={'champion':champion_status()};statuses.update({x['agent_id']:x for x in agents_status() if x.get('configured')})
    observed=datetime.now(timezone.utc).isoformat();out=[]
    for key,profile in RISK_PROFILES.items():
        status=statuses.get(key)
        if not status:continue
        quality=competitor_observations(key,status,profile['target_invested_pct'])
        ev=competitor_evaluation(key,status,profile['target_invested_pct'])
        closed=[]
        for row in (ev.get('decision_outcomes') or {}).get('closed') or []:
            item=dict(row);item['decision_fingerprint']=_fingerprint(key,item);closed.append(item)
        out.append({'competitor_key':key,'observed_at':observed,'v_score':quality.get('v_score'),'v_confidence':quality.get('v_confidence'),
                    'v_components':quality.get('v_components'),'score_semantics':quality.get('score_semantics'),
                    'decision_metrics':ev.get('decision_metrics'),'drawdown_profile':ev.get('drawdown_profile'),
                    'risk_attribution':ev.get('risk_attribution'),'closed_decisions':closed,
                    'risk_label':profile.get('risk_label'),'target_invested_pct':profile.get('target_invested_pct'),
                    'stability_score':None,'transfer_score':None,'anti_overfitting_score':None,'data_quality_score':None,
                    'promotion_readiness':None,'can_trade':False,'real_trading':False})
    return out


def current_evaluations():
    """Build enriched scorecards. Fail-soft integration never blocks the base capture."""
    base=_base_evaluations()
    try:
        # Status call creates the server-side capture boundary before any old close is persisted.
        durable=pre160_evaluation_status(365)
        league=league_status(90)
        operational=operational_pipeline()
        validation=validation_runtime_v3()
        validation=dict(validation);validation['market_telemetry']=operational.get('market_telemetry') or {}
        integrated=enrich_scorecards(base,league,operational.get('forward_records') or [],validation,durable=durable)
        return integrated.get('scorecards') or base
    except Exception as exc:
        for row in base:
            row['integration_status']='DEGRADED_BASE_CAPTURE'
            row['integration_error']=str(exc)[:500]
        return base


def push_pre160_evaluation():
    payload={'action':'persist_pre160_evaluation','node_id':NODE_ID,'evaluations':current_evaluations(),'real_trading':False}
    out=_post(payload);out['real_trading']=False;return out


def pre160_evaluation_status(days=30):
    out=_post({'action':'pre160_evaluation_status','node_id':NODE_ID,'days':max(1,min(365,int(days or 30))),'real_trading':False});out['real_trading']=False;return out


def persist_learning_lesson(lesson):
    out=_post({'action':'persist_learning_lesson','node_id':NODE_ID,'lesson':lesson,'real_trading':False});out['real_trading']=False;return out
