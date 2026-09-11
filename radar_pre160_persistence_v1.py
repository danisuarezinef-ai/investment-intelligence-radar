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
from radar_learning_journal_v1 import loss_autopsy,lesson_candidate
from radar_strategy_archive_v1 import hall_candidate,graveyard_candidate

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
            row['integration_status']='DEGRADED_BASE_CAPTURE';row['integration_error']=str(exc)[:500]
        return base


def persist_learning_lesson(lesson):
    out=_post({'action':'persist_learning_lesson','node_id':NODE_ID,'lesson':lesson,'real_trading':False});out['real_trading']=False;return out


def persist_archive_candidate(candidate):
    out=_post({'action':'persist_archive_candidate','node_id':NODE_ID,'candidate':candidate,'real_trading':False});out['real_trading']=False;return out


def _prospective_loss_lessons(durable):
    results=[]
    for row in (durable or {}).get('decisions') or []:
        try:pnl=float(row.get('realized_pnl'))
        except (TypeError,ValueError):continue
        if row.get('forward_eligible') is not True or pnl>=0:continue
        key=str(row.get('competitor_key') or 'unknown');fp=str(row.get('decision_fingerprint') or '')
        autopsy=loss_autopsy(row,context={})
        factors=autopsy.get('factors') or ['UNCLASSIFIED_PROSPECTIVE_LOSS']
        claim='Future decisions with the same observed loss factors may underperform and must be retested: '+','.join(factors)
        lesson=lesson_candidate(subject=f'{key}:{row.get("symbol")}:prospective_loss',claim=claim,
                                evidence={'competitor_key':key,'decision_fingerprint':fp,'autopsy':autopsy,
                                          'evidence_class':row.get('evidence_class')},
                                created_at=row.get('exit_ts'),min_future_tests=5)
        results.append(persist_learning_lesson(lesson))
    return results


def _archive_candidates(evaluations):
    persisted=[]
    for row in evaluations or []:
        key=str(row.get('competitor_key') or '')
        if not key:continue
        hall=hall_candidate(row,'PRE160_QUALITY_EVIDENCE_CANDIDATE')
        if hall.get('eligible') is True:
            hall=dict(hall);hall.update({'competitor_key':key,'archive_kind':'HALL_CANDIDATE','applied':False})
            persisted.append(persist_archive_candidate(hall))
        components=row.get('v_components') or {};evidence=float(components.get('evidence') or 0);v=float(row.get('v_score') or 0)
        if evidence>=70 and v<=140:
            grave=graveyard_candidate(row,'SUSTAINED_LOW_V_WITH_MATURE_EVIDENCE')
            grave=dict(grave);grave.update({'competitor_key':key,'archive_kind':'GRAVEYARD_CANDIDATE','eligible':True,'applied':False})
            persisted.append(persist_archive_candidate(grave))
    return persisted


def push_pre160_evaluation():
    evaluations=current_evaluations()
    payload={'action':'persist_pre160_evaluation','node_id':NODE_ID,'evaluations':evaluations,'real_trading':False}
    out=_post(payload);out['real_trading']=False
    try:
        durable=pre160_evaluation_status(365)
        lessons=_prospective_loss_lessons(durable)
        archives=_archive_candidates(evaluations)
        out['prospective_loss_lessons_persisted']=sum(x.get('ok') is True for x in lessons)
        out['archive_candidates_persisted']=sum(x.get('ok') is True for x in archives)
    except Exception as exc:
        out['learning_archive_status']='DEGRADED_RETRY';out['learning_archive_error']=str(exc)[:500]
    return out


def pre160_evaluation_status(days=30):
    out=_post({'action':'pre160_evaluation_status','node_id':NODE_ID,'days':max(1,min(365,int(days or 30))),'real_trading':False});out['real_trading']=False;return out
