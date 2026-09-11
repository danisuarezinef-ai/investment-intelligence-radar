"""Pre-1.6 evidence hardening v4 for tasks 111-128.

This layer adds operational continuity, uncertainty, paired comparisons and
point-in-time decision envelopes. It is diagnostics/governance only: no order
submission, automatic promotion/demotion, Setup release or real-money authority.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

from radar_core import con
from radar_multi_benchmark_v1 import compare_benchmarks, benchmark_gate
import radar_pre160_runtime_v3 as v3

REAL_TRADING=False
HORIZON_DAYS={'1d':1,'1w':7,'1m':30,'3m':90}


def _f(value,default=None):
    try:
        x=float(value);return x if math.isfinite(x) else default
    except (TypeError,ValueError):return default


def _dt(value):
    if not value:return None
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'));return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:return None


def _canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str)


def _hash(payload):return hashlib.sha256(_canonical(payload).encode('utf-8')).hexdigest()


def checkpoint_continuity(checkpoints, expected_interval_seconds=300, gap_factor=4):
    rows=sorted([dict(x) for x in checkpoints or []],key=lambda x:int(x.get('id') or 0))
    chain_ok=True;prev=None;gaps=[];last_ts=None
    for row in rows:
        if (row.get('prev_hash') or None)!=(prev or None):chain_ok=False
        payload=row.get('payload') if isinstance(row.get('payload'),dict) else None
        if payload is not None and row.get('record_hash') and _hash(payload)!=str(row.get('record_hash')):chain_ok=False
        ts=_dt(row.get('observed_at'))
        if last_ts and ts:
            sec=(ts-last_ts).total_seconds()
            if sec>expected_interval_seconds*gap_factor:gaps.append({'from':last_ts.isoformat(),'to':ts.isoformat(),'gap_seconds':sec})
        if ts:last_ts=ts
        prev=str(row.get('record_hash') or '') or prev
    blockers=[]
    if not rows:blockers.append('CHECKPOINT_HISTORY_EMPTY')
    elif len(rows)<2:blockers.append('CHECKPOINT_CONTINUITY_NEEDS_SECOND_POINT')
    if not chain_ok:blockers.append('CHECKPOINT_HASH_CHAIN_FAILED')
    if gaps:blockers.append('CHECKPOINT_CADENCE_GAPS')
    return {'status':'VERIFIED' if rows and len(rows)>=2 and not blockers else 'EVIDENCE_PENDING' if chain_ok else 'FAILED',
            'checkpoints':len(rows),'chain_integrity':chain_ok,'gaps':gaps,'expected_interval_seconds':expected_interval_seconds,
            'gap_threshold_seconds':expected_interval_seconds*gap_factor,'blockers':blockers,'real_trading':False}


def _latest_market_before(c,symbol,trade_ts):
    try:
        r=c.execute('select ts,source,price from market_snapshots where symbol=? and ts<=? order by ts desc,id desc limit 1',(symbol,trade_ts)).fetchone()
    except Exception:r=None
    if not r:return {'status':'SOURCE_NOT_CAPTURED','ts':None,'source':None,'price':None}
    return {'status':'PIT_SOURCE_CAPTURED','ts':r[0],'source':r[1],'price':_f(r[2])}


def _latest_regime_before(c,trade_ts):
    try:r=c.execute('select ts,regime,confidence,features from market_regimes where ts<=? order by ts desc,id desc limit 1',(trade_ts,)).fetchone()
    except Exception:r=None
    if not r:return {'status':'PIT_REGIME_NOT_CAPTURED','ts':None,'regime':None,'confidence':None,'features':{}}
    try:features=json.loads(r[3] or '{}')
    except Exception:features={}
    return {'status':'PIT_CAPTURED','ts':r[0],'regime':r[1],'confidence':_f(r[2]),'features':features}


def _latest_model_before(c,trade_ts):
    try:r=c.execute('select version,created_at from model_versions where created_at<=? order by created_at desc limit 1',(trade_ts,)).fetchone()
    except Exception:r=None
    return {'decision_model_version':r[0],'model_created_at':r[1]} if r else {'decision_model_version':None,'model_created_at':None}


def decision_envelope_candidates(capture_started_at):
    """Build future-trade envelopes using only information timestamped <= trade time.

    Strategy *identity* is known from the ledger owner. Strategy code version is not
    guessed when it was not captured at decision time; this remains a provenance blocker.
    """
    boundary=_dt(capture_started_at)
    if boundary is None:return []
    c=con();items=[]
    try:
        try:
            rows=c.execute('select id,ts,agent_id,symbol,side,gross_value,fees,spread_cost,fx_cost,reason from paper_agent_trades where ts>=? order by id',(boundary.isoformat(),)).fetchall()
            for r in rows:
                items.append({'source_key':'agent:'+str(r[2]),'trade_id':int(r[0]),'trade_ts':r[1],'competitor_key':str(r[2]),'symbol':str(r[3]),'side':str(r[4]),
                              'costs':{'gross_value':_f(r[5]),'fees':_f(r[6]),'spread_cost':_f(r[7]),'fx_cost':_f(r[8]),'total':sum(x or 0 for x in (_f(r[6]),_f(r[7]),_f(r[8])))},
                              'reason':str(r[9] or '')})
        except Exception:pass
        try:
            rows=c.execute('select id,ts,symbol,side,gross,costs,reason from champion_paper_trades where ts>=? order by id',(boundary.isoformat(),)).fetchall()
            for r in rows:
                items.append({'source_key':'champion','trade_id':int(r[0]),'trade_ts':r[1],'competitor_key':'champion','symbol':str(r[2]),'side':str(r[3]),
                              'costs':{'gross_value':_f(r[4]),'total':_f(r[5]),'fees':None,'spread_cost':None,'fx_cost':None},'reason':str(r[6] or '')})
        except Exception:pass
        out=[]
        for item in sorted(items,key=lambda x:(str(x['trade_ts']),x['source_key'],x['trade_id'])):
            regime=_latest_regime_before(c,item['trade_ts']);provider=_latest_market_before(c,item['symbol'],item['trade_ts']);model=_latest_model_before(c,item['trade_ts'])
            identity='champion_paper' if item['competitor_key']=='champion' else 'paper_agent:'+item['competitor_key']
            fp_body={'source_key':item['source_key'],'trade_id':item['trade_id'],'trade_ts':item['trade_ts'],'competitor_key':item['competitor_key'],
                     'symbol':item['symbol'],'side':item['side']}
            fingerprint=_hash(fp_body)
            benchmark={'name':'RADAR_EQUAL_WEIGHT_OBSERVED_UNIVERSE','reference_ts':item['trade_ts'],'entry_value':None,
                       'status':'REFERENCE_IDENTITY_FROZEN_VALUE_NOT_CAPTURED'}
            provenance={'strategy_identity':identity,'strategy_version':None,'strategy_version_status':'NOT_CAPTURED_AT_DECISION',
                        **model,'provider_status':provider['status'],'regime_status':regime['status'],'lookahead':False,'backfilled':False}
            envelope={'source_key':item['source_key'],'trade_id':item['trade_id'],'trade_ts':item['trade_ts'],'competitor_key':item['competitor_key'],
                      'strategy_identity':identity,'strategy_version':None,'decision_fingerprint':fingerprint,'symbol':item['symbol'],'side':item['side'],
                      'regime_ts':regime['ts'],'regime':regime['regime'],'regime_confidence':regime['confidence'],'regime_features':regime['features'],
                      'benchmark_snapshot':benchmark,'cost_snapshot':item['costs'],'provider_snapshot':provider,'provenance':provenance,
                      'reason':item['reason'],'real_trading':False}
            envelope['envelope_hash']=_hash({k:v for k,v in envelope.items() if k!='envelope_hash'})
            out.append(envelope)
        return out
    finally:c.close()


def horizon_maturity_queue(forward_records,now=None):
    now=now or datetime.now(timezone.utc);pending=[];overdue=[];unknown=[]
    for raw in forward_records or []:
        r=dict(raw)
        if r.get('backfilled') is True:continue
        if r.get('matured') is True:continue
        created=_dt(r.get('created_at') or r.get('prediction_ts') or r.get('ts'));h=str(r.get('horizon') or '')
        days=HORIZON_DAYS.get(h)
        if not created or days is None:unknown.append({'symbol':r.get('symbol'),'horizon':h or None,'reason':'MISSING_CREATED_AT_OR_HORIZON'});continue
        due=created+timedelta(days=days);item={'symbol':r.get('symbol'),'horizon':h,'created_at':created.isoformat(),'due_at':due.isoformat(),'overdue':now>due}
        (overdue if item['overdue'] else pending).append(item)
    return {'status':'AVAILABLE' if pending or overdue or unknown else 'EVIDENCE_PENDING','pending':len(pending),'overdue':len(overdue),'unknown':len(unknown),
            'next_due_at':min((x['due_at'] for x in pending),default=None),'overdue_examples':overdue[:20],'unknown_examples':unknown[:20],
            'blockers':(['OVERDUE_FORWARD_OUTCOMES'] if overdue else [])+(['MATURITY_METADATA_INCOMPLETE'] if unknown else []),'real_trading':False}


def _wilson(successes,n,z=1.96):
    if n<=0:return (None,None)
    p=successes/n;den=1+z*z/n;center=(p+z*z/(2*n))/den;margin=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/den
    return max(0.,center-margin),min(1.,center+margin)


def calibration_uncertainty(decisions,min_n=30):
    rows=[]
    for r in v3._prospective(decisions):
        conf=v3._confidence(r);pnl=_f(r.get('realized_pnl'))
        if conf is not None and pnl is not None:rows.append((conf,1 if pnl>0 else 0))
    bins=[]
    for lo,hi in v3.CALIBRATION_BINS:
        part=[x for x in rows if lo<=x[0]<hi];wins=sum(x[1] for x in part);low,high=_wilson(wins,len(part))
        bins.append({'low':lo,'high':min(1.,hi),'n':len(part),'mean_confidence':sum(x[0] for x in part)/len(part) if part else None,
                     'hit_rate':wins/len(part) if part else None,'hit_rate_ci95':[low,high] if low is not None else None})
    total_wins=sum(x[1] for x in rows);low,high=_wilson(total_wins,len(rows));blockers=[]
    if len(rows)<min_n:blockers.append('CALIBRATION_EFFECTIVE_SAMPLE_SMALL')
    populated=sum(1 for x in bins if x['n']>=5)
    if populated<3:blockers.append('CALIBRATION_BIN_COVERAGE_LOW')
    return {'status':'MATURE' if not blockers else 'EVIDENCE_PENDING','n':len(rows),'populated_bins_n5':populated,
            'overall_hit_rate':total_wins/len(rows) if rows else None,'overall_hit_rate_ci95':[low,high] if low is not None else None,
            'bins':bins,'blockers':blockers,'real_trading':False}


def multi_benchmark_robustness(forward_records):
    summary=compare_benchmarks(forward_records);gate=benchmark_gate(summary)
    rows=summary.get('benchmarks') or [];covered=[r for r in rows if float(r.get('coverage') or 0)>=.95]
    blockers=[]
    if len(covered)<2:blockers.append('FEWER_THAN_TWO_HIGH_COVERAGE_BENCHMARKS')
    if not gate.get('passed'):blockers.append('NONNEGATIVE_EXCESS_NOT_ESTABLISHED')
    return {'status':'AVAILABLE' if rows else 'EVIDENCE_PENDING','summary':summary,'gate':gate,'high_coverage_benchmarks':[x.get('benchmark') for x in covered],
            'blockers':blockers,'performance_verified':False,'real_trading':False}


def turnover_cost_budget(decisions,cost_drag_warn_pct=1.0):
    rows=v3._prospective(decisions);capital=sum(max(0.,_f(x.get('entry_capital'),0.) or 0.) for x in rows);cost=sum(max(0.,_f(x.get('costs'),0.) or 0.) for x in rows)
    ratio=100*cost/capital if capital>0 else None;status='EVIDENCE_PENDING' if ratio is None else ('WATCH' if ratio>cost_drag_warn_pct else 'OK')
    return {'status':status,'closed_decisions':len(rows),'capital_deployed':capital or None,'costs':cost if rows else None,'cost_drag_pct':ratio,
            'warning_threshold_pct':cost_drag_warn_pct,'threshold_note':'Governance default, not empirically proven optimal.','automatic_action':False,'real_trading':False}


def concentration_exposure_watch(scorecards):
    rows=[]
    for s in scorecards or []:
        r=s.get('risk_attribution') or {};top=_f(r.get('top_position_share'));hhi=_f(r.get('hhi'));inv=_f(r.get('invested_pct'))
        watch=bool((top is not None and top>.45) or (hhi is not None and hhi>.40) or (inv is not None and inv>95))
        rows.append({'competitor_key':s.get('competitor_key'),'top_position_share':top,'hhi':hhi,'invested_pct':inv,'watch':watch})
    return {'status':'AVAILABLE' if rows else 'EVIDENCE_PENDING','competitors':rows,'watch_count':sum(x['watch'] for x in rows),
            'synthetic_stress_performance_claim':False,'automatic_action':False,'real_trading':False}


def regime_coverage_balance(decisions,envelopes,min_per_regime=5):
    by_fp={str(x.get('decision_fingerprint')):x for x in envelopes or [] if x.get('decision_fingerprint')}
    counts=Counter();missing=0
    for d in v3._prospective(decisions):
        env=by_fp.get(str(d.get('decision_fingerprint') or ''))
        if not env or not env.get('regime'):missing+=1;continue
        counts[str(env['regime'])]+=1
    mature={k:n for k,n in counts.items() if n>=min_per_regime};blockers=[]
    if missing:blockers.append('PROSPECTIVE_REGIME_CONTEXT_MISSING')
    if len(mature)<2:blockers.append('REGIME_DIVERSITY_NOT_MATURE')
    total=sum(counts.values());shares={k:n/total for k,n in counts.items()} if total else {}
    return {'status':'MATURE' if not blockers else 'EVIDENCE_PENDING','counts':dict(counts),'shares':shares,'mature_regimes':mature,'missing':missing,'blockers':blockers,'real_trading':False}


def paired_champion_challenger(decisions,min_pairs=5):
    prospective=v3._prospective(decisions);champ=[x for x in prospective if str(x.get('competitor_key'))=='champion'];chall=[x for x in prospective if str(x.get('competitor_key'))!='champion']
    cindex=defaultdict(list)
    for x in champ:
        key=(str(x.get('symbol')),str(x.get('exit_ts') or '')[:10],str((x.get('payload') or {}).get('horizon') or x.get('horizon') or ''))
        cindex[key].append(x)
    pairs=[]
    for x in chall:
        key=(str(x.get('symbol')),str(x.get('exit_ts') or '')[:10],str((x.get('payload') or {}).get('horizon') or x.get('horizon') or ''))
        if not cindex.get(key):continue
        c=cindex[key][0];cr=_f(c.get('return_pct'));xr=_f(x.get('return_pct'))
        if cr is None or xr is None:continue
        pairs.append({'challenger':x.get('competitor_key'),'symbol':x.get('symbol'),'day':key[1],'horizon':key[2] or None,'champion_return_pct':cr,'challenger_return_pct':xr,'delta_pct':xr-cr})
    grouped=defaultdict(list)
    for p in pairs:grouped[str(p['challenger'])].append(p['delta_pct'])
    comparisons=[]
    for key,vals in grouped.items():
        comparisons.append({'challenger':key,'pairs':len(vals),'mean_delta_pct':sum(vals)/len(vals),'win_rate':sum(v>0 for v in vals)/len(vals),'mature':len(vals)>=min_pairs})
    return {'status':'AVAILABLE' if pairs else 'EVIDENCE_PENDING','pairs':len(pairs),'comparisons':comparisons,
            'blockers':[] if any(x['mature'] for x in comparisons) else ['PAIRED_COMPARISON_SAMPLE_SMALL'],'real_trading':False}


def sequential_superiority(paired,min_pairs=5,min_win_rate=.60):
    rows=[]
    for x in (paired or {}).get('comparisons') or []:
        ready=bool(int(x.get('pairs') or 0)>=min_pairs and _f(x.get('mean_delta_pct'),-999)>0 and _f(x.get('win_rate'),0)>=min_win_rate)
        rows.append({**x,'superiority_watch_ready':ready})
    return {'status':'WATCH_READY' if any(x['superiority_watch_ready'] for x in rows) else 'EVIDENCE_PENDING','comparisons':rows,
            'requirements':{'min_pairs':min_pairs,'min_win_rate':min_win_rate,'mean_delta_positive':True},
            'automatic_promotion':False,'real_trading':False}


def persistent_degradation_state(v3_degradation,now=None,cooldown_days=7):
    now=now or datetime.now(timezone.utc);d=v3_degradation or {};consecutive=int(d.get('consecutive_degraded_days') or 0);active=bool(d.get('cooldown_active'))
    until=(now+timedelta(days=cooldown_days)).date().isoformat() if active else None
    return {'status':'COOLDOWN' if active else ('AVAILABLE' if d.get('status')!='EVIDENCE_PENDING' else 'EVIDENCE_PENDING'),
            'consecutive_degraded_days':consecutive,'cooldown_until':until,'cooldown_days':cooldown_days,
            'automatic_demotion':False,'real_trading':False}


def readiness_countdown(capture_started_at,sample_gates,readiness,now=None):
    now=now or datetime.now(timezone.utc);start=_dt(capture_started_at);calendar_due=start+timedelta(days=30) if start else None
    mature=bool(sample_gates) and all(x.get('status')=='MATURE' for x in sample_gates.values())
    remaining_calendar=max(0,(calendar_due.date()-now.date()).days) if calendar_due else None
    return {'status':'READY_NOW' if (readiness or {}).get('status')=='READY_FOR_1_6_REVIEW' else 'CONDITIONAL_WAIT',
            'capture_started_at':start.isoformat() if start else None,'calendar_30d_due_at':calendar_due.isoformat() if calendar_due else None,
            'calendar_days_remaining':remaining_calendar,'sample_gates_mature':mature,
            'earliest_possible_review_at':calendar_due.isoformat() if calendar_due and mature else None,
            'note':'Conditional lower bound only; evidence rate, market events and unresolved blockers can move readiness later. No release date is promised.',
            'setup_allowed':False,'real_trading':False}


def build_hardening_snapshot(*,evidence_v3,durable_eval,evidence_authority,forward_records,base_runtime):
    decisions=(durable_eval or {}).get('decisions') or [];envelopes_remote=(evidence_authority or {}).get('envelopes') or []
    local=decision_envelope_candidates((durable_eval or {}).get('capture_started_at'));envelopes=envelopes_remote or local
    continuity=checkpoint_continuity((evidence_authority or {}).get('checkpoints') or [])
    maturity=horizon_maturity_queue(forward_records);cal=calibration_uncertainty(decisions);bench=multi_benchmark_robustness(forward_records)
    turnover=turnover_cost_budget(decisions);concentration=concentration_exposure_watch((base_runtime or {}).get('scorecards') or [])
    regimes=regime_coverage_balance(decisions,envelopes);paired=paired_champion_challenger(decisions);superiority=sequential_superiority(paired)
    degradation=persistent_degradation_state((evidence_v3 or {}).get('champion_degradation_sequential') or {})
    countdown=readiness_countdown((durable_eval or {}).get('capture_started_at'),(evidence_v3 or {}).get('sample_gates') or {},(evidence_v3 or {}).get('readiness_1_6') or {})
    strategy_versions_missing=sum(1 for x in envelopes if not x.get('strategy_version'))
    provenance={'status':'COMPLETE' if envelopes and strategy_versions_missing==0 else 'EVIDENCE_PENDING','envelopes':len(envelopes),
                'strategy_versions_missing':strategy_versions_missing,'blockers':(['STRATEGY_VERSION_NOT_CAPTURED_AT_DECISION'] if strategy_versions_missing else [])+(['DECISION_ENVELOPES_EMPTY'] if not envelopes else []),'real_trading':False}
    snapshot={'status':'PRE160_EVIDENCE_V4','observed_at':datetime.now(timezone.utc).isoformat(),'checkpoint_continuity':continuity,'horizon_maturity':maturity,
              'calibration_uncertainty':cal,'multi_benchmark_robustness':bench,'turnover_cost_budget':turnover,'concentration_exposure':concentration,
              'regime_coverage':regimes,'paired_champion_challenger':paired,'sequential_superiority':superiority,'persistent_degradation':degradation,
              'readiness_countdown':countdown,'decision_envelope_provenance':provenance,'envelopes_to_freeze':local,
              'guard_state':degradation,'setup_allowed':False,'automatic_release':False,'automatic_promotion':False,'automatic_demotion':False,'can_trade':False,'real_trading':False}
    snapshot['snapshot_hash']=_hash({k:v for k,v in snapshot.items() if k!='snapshot_hash'});return snapshot
