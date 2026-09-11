"""Pre-1.6 evidence runtime v3 for tasks 93-108.

All metrics are PAPER/SHADOW diagnostics. Missing prospective evidence is a blocker,
never a neutral score. No function can promote/demote a strategy or submit orders.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone

from radar_core import con

REAL_TRADING=False
SAMPLE_MIN_CLOSES=30
SAMPLE_MIN_DAYS=14
SAMPLE_MIN_SYMBOLS=5
CALIBRATION_BINS=((0,.2),(.2,.4),(.4,.6),(.6,.8),(.8,1.000001))
COST_LADDER_BPS=(0,5,10,25,50)


def _f(v,default=None):
    try:
        x=float(v);return x if math.isfinite(x) else default
    except (TypeError,ValueError):return default


def _dt(v):
    if not v:return None
    try:
        d=datetime.fromisoformat(str(v).replace('Z','+00:00'));return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:return None


def _prospective(rows):return [dict(x) for x in rows or [] if x.get('forward_eligible') is True and x.get('evidence_class')=='PROSPECTIVE_PAPER_CLOSE']


def sample_gate(rows,min_closes=SAMPLE_MIN_CLOSES,min_days=SAMPLE_MIN_DAYS,min_symbols=SAMPLE_MIN_SYMBOLS):
    rows=_prospective(rows);days={str(x.get('exit_ts') or '')[:10] for x in rows if x.get('exit_ts')};symbols={str(x.get('symbol')) for x in rows if x.get('symbol')}
    blockers=[]
    if len(rows)<min_closes:blockers.append('MIN_PROSPECTIVE_CLOSES_NOT_MET')
    if len(days)<min_days:blockers.append('MIN_PROSPECTIVE_DAYS_NOT_MET')
    if len(symbols)<min_symbols:blockers.append('MIN_SYMBOL_DIVERSITY_NOT_MET')
    return {'status':'MATURE' if not blockers else 'EVIDENCE_PENDING','closes':len(rows),'days':len(days),'symbols':len(symbols),
            'requirements':{'closes':min_closes,'days':min_days,'symbols':min_symbols},'blockers':blockers,'real_trading':False}


def sample_gates_by_competitor(rows):
    grouped=defaultdict(list)
    for row in rows or []:grouped[str(row.get('competitor_key') or 'unknown')].append(row)
    return {k:sample_gate(v) for k,v in grouped.items()}


def _confidence(row):
    value=_f(row.get('confidence'))
    if value is not None:return max(0.,min(1.,value))
    payload=row.get('payload') if isinstance(row.get('payload'),dict) else {}
    value=_f(payload.get('confidence'))
    return max(0.,min(1.,value)) if value is not None else None


def calibration_bins_and_drift(rows,min_total=30):
    records=[]
    for row in _prospective(rows):
        conf=_confidence(row);pnl=_f(row.get('realized_pnl'))
        if conf is not None and pnl is not None:records.append({'confidence':conf,'hit':1.0 if pnl>0 else 0.0,'exit_ts':row.get('exit_ts')})
    records.sort(key=lambda x:str(x.get('exit_ts') or ''))
    bins=[]
    for lo,hi in CALIBRATION_BINS:
        part=[x for x in records if lo<=x['confidence']<hi]
        bins.append({'low':lo,'high':min(1.,hi),'n':len(part),'mean_confidence':sum(x['confidence'] for x in part)/len(part) if part else None,
                     'hit_rate':sum(x['hit'] for x in part)/len(part) if part else None})
    brier=sum((x['confidence']-x['hit'])**2 for x in records)/len(records) if records else None
    drift=None
    if len(records)>=40:
        mid=len(records)//2;a=records[:mid];b=records[mid:]
        ba=sum((x['confidence']-x['hit'])**2 for x in a)/len(a);bb=sum((x['confidence']-x['hit'])**2 for x in b)/len(b);drift=bb-ba
    blockers=[]
    if len(records)<min_total:blockers.append('CALIBRATION_SAMPLE_SMALL')
    if drift is None:blockers.append('CALIBRATION_DRIFT_WINDOW_SMALL')
    return {'status':'MATURE' if not blockers else 'EVIDENCE_PENDING','n':len(records),'brier':brier,'brier_drift':drift,'bins':bins,'blockers':blockers,'real_trading':False}


def multi_benchmark_attribution(forward_records):
    rows=[x for x in forward_records or [] if x.get('matured') is True and x.get('backfilled') is not True]
    result={}
    for name,key in (('primary','benchmark_return'),('cash',None)):
        diffs=[];covered=0
        for row in rows:
            ret=_f(row.get('net_return',row.get('return_pct')))
            bench=0.0 if key is None else _f(row.get(key))
            if ret is None or bench is None:continue
            covered+=1;diffs.append(ret-bench)
        result[name]={'coverage':covered/len(rows) if rows else 0.0,'n':covered,'mean_excess_return':sum(diffs)/len(diffs) if diffs else None}
    blockers=[]
    if not rows:blockers.append('NO_MATURE_FORWARD_RECORDS')
    if result['primary']['coverage']<.95:blockers.append('PRIMARY_BENCHMARK_COVERAGE_LOW')
    return {'status':'AVAILABLE' if rows and not blockers else 'EVIDENCE_PENDING','benchmarks':result,'blockers':blockers,'real_trading':False}


def cost_slippage_ladder(rows):
    base=[]
    for row in _prospective(rows):
        r=_f(row.get('return_pct'))
        if r is not None:base.append(r)
    scenarios=[]
    for bps in COST_LADDER_BPS:
        penalty=bps/100.0;vals=[x-penalty for x in base]
        scenarios.append({'extra_cost_bps':bps,'n':len(vals),'mean_return_pct':sum(vals)/len(vals) if vals else None,'positive_rate':sum(x>0 for x in vals)/len(vals) if vals else None})
    return {'status':'AVAILABLE' if base else 'EVIDENCE_PENDING','observations':len(base),'scenarios':scenarios,
            'blockers':[] if base else ['NO_PROSPECTIVE_RETURN_OBSERVATIONS'],'real_trading':False}


def capital_efficiency(rows):
    rows=_prospective(rows);capital=[];pnl=[];costs=[]
    for row in rows:
        c=_f(row.get('entry_capital'));p=_f(row.get('realized_pnl'));k=_f(row.get('costs'),0.)
        if c is not None and c>0 and p is not None:capital.append(c);pnl.append(p);costs.append(k or 0.)
    deployed=sum(capital);profit=sum(pnl);cost=sum(costs)
    return {'status':'AVAILABLE' if capital else 'EVIDENCE_PENDING','closed_positions':len(capital),'capital_deployed':deployed or None,
            'realized_pnl':profit if capital else None,'realized_return_on_deployed_pct':profit/deployed*100 if deployed else None,
            'cost_drag_pct':cost/deployed*100 if deployed else None,'blockers':[] if capital else ['CAPITAL_EFFICIENCY_SAMPLE_EMPTY'],'real_trading':False}


def pit_trade_context_candidates(capture_started_at):
    """Freeze only context that existed at/before trade time; never recalculate with future data."""
    boundary=_dt(capture_started_at)
    if boundary is None:return []
    c=con();out=[]
    try:
        sources=[]
        try:
            sources.extend([('agent:'+str(r[2]),r[0],r[1],str(r[2]),r[3],r[4]) for r in c.execute('select id,ts,agent_id,symbol,side from paper_agent_trades where ts>=? order by id',(boundary.isoformat(),)).fetchall()])
        except Exception:pass
        try:
            sources.extend([('champion',r[0],r[1],'champion',r[2],r[3]) for r in c.execute('select id,ts,symbol,side from champion_paper_trades where ts>=? order by id',(boundary.isoformat(),)).fetchall()])
        except Exception:pass
        for source,trade_id,trade_ts,competitor,symbol,side in sources:
            regime=None
            try:regime=c.execute('select ts,regime,confidence,features from market_regimes where ts<=? order by ts desc,id desc limit 1',(trade_ts,)).fetchone()
            except Exception:regime=None
            if regime:
                try:features=json.loads(regime[3] or '{}')
                except Exception:features={}
                status='PIT_CAPTURED';regime_ts,regime_name,confidence=regime[0],regime[1],_f(regime[2])
            else:
                status='PIT_REGIME_NOT_CAPTURED';regime_ts=regime_name=confidence=None;features={}
            out.append({'source_key':source,'trade_id':int(trade_id),'trade_ts':trade_ts,'competitor_key':competitor,'symbol':symbol,'side':side,
                        'regime_ts':regime_ts,'regime':regime_name,'regime_confidence':confidence,'regime_features':features,'status':status,'real_trading':False})
    finally:c.close()
    return out


def regime_horizon_matrix(rows,contexts,min_cell_n=5):
    contexts=contexts or []
    index={}
    for x in contexts:
        if x.get('status')=='PIT_CAPTURED' and str(x.get('side')).upper()=='BUY':index[(str(x.get('competitor_key')),str(x.get('symbol')))] = x
    cells=defaultdict(list);missing_context=0;missing_horizon=0
    for row in _prospective(rows):
        ctx=index.get((str(row.get('competitor_key')),str(row.get('symbol'))));payload=row.get('payload') if isinstance(row.get('payload'),dict) else {}
        horizon=row.get('horizon') or payload.get('horizon')
        ret=_f(row.get('return_pct'))
        if not ctx:missing_context+=1;continue
        if not horizon:missing_horizon+=1;continue
        if ret is not None:cells[(str(ctx.get('regime')),str(horizon))].append(ret)
    matrix=[]
    for (regime,horizon),vals in sorted(cells.items()):
        matrix.append({'regime':regime,'horizon':horizon,'n':len(vals),'mean_return_pct':sum(vals)/len(vals),'mature':len(vals)>=min_cell_n})
    blockers=[]
    if missing_context:blockers.append('PIT_REGIME_CONTEXT_INCOMPLETE')
    if missing_horizon:blockers.append('HORIZON_CONTEXT_INCOMPLETE')
    if not any(x['mature'] for x in matrix):blockers.append('NO_MATURE_REGIME_HORIZON_CELL')
    return {'status':'AVAILABLE' if matrix else 'EVIDENCE_PENDING','matrix':matrix,'missing_context':missing_context,'missing_horizon':missing_horizon,'blockers':blockers,'real_trading':False}


def stress_readiness(forward_records):
    exposures=[x for x in forward_records or [] if x.get('stress_scenario') or x.get('perturbation') or x.get('stress')]
    return {'status':'AVAILABLE' if exposures else 'EVIDENCE_PENDING','observed_exposures':len(exposures),
            'blockers':[] if exposures else ['OBSERVED_STRESS_EXPOSURES_MISSING'],'synthetic_stress_claim':False,'real_trading':False}


def anti_overfitting_v2(validation,forward_records):
    hist=(validation or {}).get('historical_lab') or {};rows=[x for x in forward_records or [] if x.get('matured') is True and x.get('backfilled') is not True]
    components={}
    for name,keys in {'walk_forward':('mean_gain','walk_forward_gain'),'vault':('vault_gain',),'final_test':('test_gain','final_test_gain')}.items():
        value=None
        for key in keys:
            if _f(hist.get(key)) is not None:value=_f(hist.get(key));break
        components[name]=value
    live=[_f(x.get('excess_return')) for x in rows];live=[x for x in live if x is not None];components['live_forward']=sum(live)/len(live) if live else None
    available=[v for v in components.values() if v is not None]
    blockers=[f'{k.upper()}_EVIDENCE_MISSING' for k,v in components.items() if v is None]
    score=None
    if len(available)>=3:
        spread=max(available)-min(available);sign_consistency=sum((v>=0)==(available[0]>=0) for v in available)/len(available)
        score=max(0.,min(100.,100.-min(60.,abs(spread)*1000)+20.*(sign_consistency-1.)))
    return {'status':'AVAILABLE' if score is not None else 'EVIDENCE_PENDING','score':score,'components':components,'blockers':blockers,
            'selection_uses_final_test':False,'selection_uses_live_forward':False,'real_trading':False}


def champion_challenger_transfer(scorecards,champion_key='champion'):
    champ=next((x for x in scorecards or [] if str(x.get('competitor_key'))==str(champion_key)),None);rows=[]
    if not champ:return {'status':'EVIDENCE_PENDING','comparisons':[],'blockers':['CHAMPION_SCORECARD_MISSING'],'real_trading':False}
    for x in scorecards or []:
        if x is champ:continue
        bm=x.get('competitor_benchmark') or {};gate=x.get('promotion_v2') or {};excess=_f(bm.get('excess_return_pct'));readiness=_f(gate.get('readiness'))
        if excess is None or readiness is None:score=None
        else:score=max(0.,min(100.,50.+excess*4.+(readiness-50.)*.25))
        rows.append({'competitor_key':x.get('competitor_key'),'transfer_score':score,'excess_return_pct':excess,'promotion_readiness':readiness})
    return {'status':'AVAILABLE' if any(x['transfer_score'] is not None for x in rows) else 'EVIDENCE_PENDING','comparisons':rows,
            'automatic_replacement':False,'real_trading':False}


def sequential_degradation_watch(daily_rows,champion_key='champion',cooldown_days=7):
    rows=[x for x in daily_rows or [] if str(x.get('competitor_key'))==str(champion_key)];rows.sort(key=lambda x:str(x.get('day') or ''))
    recent=rows[-7:];flags=[]
    for row in recent:
        ev=row.get('evaluation') if isinstance(row.get('evaluation'),dict) else {};v=_f(row.get('v_score'));dq=_f(row.get('data_quality_score'))
        flags.append(bool((v is not None and v<150) or (dq is not None and dq<60) or ev.get('integration_status')=='DEGRADED_BASE_CAPTURE'))
    consecutive=0
    for f in reversed(flags):
        if f:consecutive+=1
        else:break
    degraded=consecutive>=3
    return {'status':'DEGRADED_WATCH' if degraded else ('AVAILABLE' if rows else 'EVIDENCE_PENDING'),'observed_days':len(rows),'consecutive_degraded_days':consecutive,
            'cooldown_days':cooldown_days,'cooldown_active':degraded,'automatic_demotion':False,'real_trading':False}


def provenance_completeness(rows):
    required=('competitor_key','decision_fingerprint','entry_ts','exit_ts','symbol','realized_pnl','return_pct','evidence_class','forward_eligible')
    prospective=_prospective(rows);total=len(prospective)*len(required);present=sum(1 for row in prospective for k in required if row.get(k) is not None)
    score=100.*present/total if total else None;blockers=[]
    if not prospective:blockers.append('NO_PROSPECTIVE_DECISIONS')
    if score is not None and score<100:blockers.append('PROVENANCE_FIELDS_INCOMPLETE')
    return {'status':'COMPLETE' if score==100 else 'EVIDENCE_PENDING','score':score,'records':len(prospective),'required_fields':list(required),'blockers':blockers,'real_trading':False}


def freshness_sla(*,capture_started_at,daily_rows,decisions,contexts,now=None):
    now=now or datetime.now(timezone.utc);latest_daily=max((_dt(x.get('observed_at')) for x in daily_rows or [] if _dt(x.get('observed_at'))),default=None)
    latest_close=max((_dt(x.get('exit_ts')) for x in _prospective(decisions) if _dt(x.get('exit_ts'))),default=None)
    latest_context=max((_dt(x.get('trade_ts')) for x in contexts or [] if _dt(x.get('trade_ts'))),default=None)
    surfaces={'evaluation_daily':(latest_daily,6*3600),'prospective_close':(latest_close,7*86400),'pit_context':(latest_context,7*86400)};rows=[];blocking=[]
    for name,(ts,limit) in surfaces.items():
        age=None if ts is None else max(0.,(now-ts).total_seconds());state='MISSING' if ts is None else ('FRESH' if age<=limit else 'STALE')
        item={'surface':name,'timestamp':ts.isoformat() if ts else None,'age_seconds':age,'sla_seconds':limit,'state':state};rows.append(item)
        if name=='evaluation_daily' and state!='FRESH':blocking.append(name)
    return {'status':'FRESH' if not blocking else 'DEGRADED','surfaces':rows,'blocking':blocking,'capture_started_at':capture_started_at,'real_trading':False}


def canonical_hash(payload):return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str).encode()).hexdigest()


def readiness_16(*,sample_gates,calibration,benchmarks,costs,regime_matrix,stress,anti_overfit,provenance,freshness,observed_runtime_days):
    checks={
        'runtime_30d':observed_runtime_days>=30,
        'all_samples_mature':bool(sample_gates) and all(x.get('status')=='MATURE' for x in sample_gates.values()),
        'calibration_mature':calibration.get('status')=='MATURE',
        'benchmark_coverage':benchmarks.get('status')=='AVAILABLE',
        'cost_sensitivity_available':costs.get('status')=='AVAILABLE',
        'regime_horizon_mature':not regime_matrix.get('blockers'),
        'stress_observed':stress.get('status')=='AVAILABLE',
        'anti_overfit_available':anti_overfit.get('score') is not None,
        'provenance_complete':provenance.get('status')=='COMPLETE',
        'freshness_ok':freshness.get('status')=='FRESH',
    }
    severity={'runtime_30d':'CRITICAL','all_samples_mature':'CRITICAL','calibration_mature':'HIGH','benchmark_coverage':'HIGH','cost_sensitivity_available':'HIGH',
              'regime_horizon_mature':'HIGH','stress_observed':'HIGH','anti_overfit_available':'HIGH','provenance_complete':'CRITICAL','freshness_ok':'CRITICAL'}
    blockers=[{'check':k,'severity':severity[k]} for k,v in checks.items() if not v];score=round(100*sum(checks.values())/len(checks),1)
    return {'status':'READY_FOR_1_6_REVIEW' if not blockers else 'BLOCKED_PRE160','score_pct':score,'checks':checks,'blockers':blockers,
            'setup_allowed':False,'automatic_release':False,'can_trade':False,'real_trading':False}


def build_evidence_snapshot(*,base_runtime,durable_eval,evidence_authority,forward_records,validation):
    decisions=(durable_eval or {}).get('decisions') or [];contexts=(evidence_authority or {}).get('contexts') or []
    local_contexts=pit_trade_context_candidates((durable_eval or {}).get('capture_started_at'));all_contexts=contexts or local_contexts
    gates=sample_gates_by_competitor(decisions);cal=calibration_bins_and_drift(decisions);bench=multi_benchmark_attribution(forward_records);costs=cost_slippage_ladder(decisions)
    efficiency=capital_efficiency(decisions);matrix=regime_horizon_matrix(decisions,all_contexts);stress=stress_readiness(forward_records);anti=anti_overfitting_v2(validation,forward_records)
    transfer=champion_challenger_transfer((base_runtime or {}).get('scorecards') or [],(base_runtime or {}).get('champion_key') or 'champion')
    degradation=sequential_degradation_watch((durable_eval or {}).get('daily') or [],(base_runtime or {}).get('champion_key') or 'champion')
    provenance=provenance_completeness(decisions);fresh=freshness_sla(capture_started_at=(durable_eval or {}).get('capture_started_at'),daily_rows=(durable_eval or {}).get('daily') or [],decisions=decisions,contexts=all_contexts)
    days=int(((base_runtime or {}).get('evidence_maturity') or {}).get('observed_runtime_days') or 0)
    ready=readiness_16(sample_gates=gates,calibration=cal,benchmarks=bench,costs=costs,regime_matrix=matrix,stress=stress,anti_overfit=anti,provenance=provenance,freshness=fresh,observed_runtime_days=days)
    snapshot={'status':'PRE160_EVIDENCE_V3','observed_at':datetime.now(timezone.utc).isoformat(),'capture_started_at':(durable_eval or {}).get('capture_started_at'),
              'sample_gates':gates,'calibration':cal,'multi_benchmark':bench,'cost_slippage':costs,'capital_efficiency':efficiency,
              'regime_horizon':matrix,'stress_readiness':stress,'anti_overfitting_v2':anti,'champion_challenger_transfer':transfer,
              'champion_degradation_sequential':degradation,'provenance':provenance,'freshness':fresh,'readiness_1_6':ready,
              'contexts_to_freeze':local_contexts,'automatic_promotion':False,'automatic_demotion':False,'setup_allowed':False,'can_trade':False,'real_trading':False}
    snapshot['snapshot_hash']=canonical_hash({k:v for k,v in snapshot.items() if k!='snapshot_hash'});return snapshot
