"""Tasks 171-190: restart-safe maturity, PIT replay, market reliability and PAPER execution reality.
Pure evaluation layer. Missing evidence never becomes PASS. REAL_TRADING is permanently false.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json, math
REAL_TRADING=False

def _task(n,status,**e):
    return {'task':n,'status':status,'evidence':{**e,'real_trading':False},'real_trading':False}

def _iso(v):
    try:return datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(timezone.utc)
    except Exception:return None

def _canon(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str)
def sha(v):return hashlib.sha256(_canon(v).encode('utf-8')).hexdigest()

def maturity_integrity(summary, intervals=None):
    summary=summary or {};intervals=list(intervals or [])
    # Server-side exclusion constraints are the primary no-overlap authority; local list is additional proof.
    ordered=sorted(intervals,key=lambda x:str(x.get('started_at') or x.get('start') or ''))
    overlap=False;future=False;bad_duration=False;prev=None
    now=datetime.now(timezone.utc)
    for x in ordered:
        a=_iso(x.get('started_at') or x.get('start'));b=_iso(x.get('ended_at') or x.get('end'))
        if not a or not b or b<a: bad_duration=True;continue
        if (b-a).total_seconds()>900.001:bad_duration=True
        if b>now:future=True
        if prev and a<prev:overlap=True
        prev=max(prev,b) if prev else b
    return {'overlap':overlap,'future':future,'bad_duration':bad_duration,
            'valid_forward_hours':float(summary.get('valid_forward_hours') or 0.0),
            'qualifying_intervals':int(summary.get('qualifying_intervals') or 0),
            'server_overlap_guard':summary.get('overlap_guard') is True,
            'server_no_backfill':summary.get('no_backfill') is True,
            'real_trading':False}

def feature_authority(snapshots):
    valid=[];invalid=[]
    for s in snapshots or []:
        f=s.get('features');capt=_iso(s.get('captured_at'));cut=_iso(s.get('data_cutoff'))
        ok=bool(s.get('prediction_id') and isinstance(f,dict) and f and s.get('feature_fingerprint') and
                s.get('immutable') is True and s.get('prospective_capture') is True and
                s.get('backfilled') is not True and s.get('retroactive_fill') is not True and
                s.get('lookahead') is not True and capt and cut and cut<=capt)
        expected=sha(f) if isinstance(f,dict) and f else None
        # Existing historical fingerprints may use a different canonicaliser; exact recomputation is only asserted when explicitly labelled sha256.
        if s.get('fingerprint_algorithm')=='sha256-canonical-json' and expected!=s.get('feature_fingerprint'):ok=False
        (valid if ok else invalid).append(s)
    return {'valid':valid,'invalid':invalid,'valid_count':len(valid),'invalid_count':len(invalid),'real_trading':False}

def decision_chain(rows,snapshots):
    sm={str(s.get('prediction_id')):s for s in snapshots or [] if s.get('prediction_id')}
    linked=0;ambiguous=0;lookahead=0
    for r in rows or []:
        pid=str(r.get('prediction_id') or r.get('local_prediction_id') or '')
        s=sm.get(pid)
        if not s:continue
        linked+=1
        c=_iso(s.get('captured_at'));cut=_iso(s.get('data_cutoff'));created=_iso(r.get('created_at'));ev=_iso(r.get('evaluated_at'))
        if c and created and c>created:lookahead+=1
        if cut and created and cut>created:lookahead+=1
        if ev and created and ev<created:lookahead+=1
    ids=[str(r.get('prediction_id') or r.get('local_prediction_id') or '') for r in rows or []]
    ambiguous=len(ids)-len(set(ids)) if ids else 0
    return {'linked':linked,'rows':len(rows or []),'ambiguous_ids':ambiguous,'temporal_violations':lookahead,'real_trading':False}

def pit_replay(snapshot,decision):
    if not snapshot or not decision:return {'status':'PENDING_DATA','real_trading':False}
    captured=_iso(snapshot.get('captured_at'));cut=_iso(snapshot.get('data_cutoff'));dt=_iso(decision.get('created_at'))
    fields=bool(snapshot.get('features') and snapshot.get('feature_fingerprint') and snapshot.get('prediction_id'))
    temporal=bool(captured and cut and dt and cut<=dt and captured<=dt)
    return {'status':'PASS' if fields and temporal and snapshot.get('immutable') is True and snapshot.get('backfilled') is not True else 'FAIL_CLOSED',
            'replay_input_hash':sha({'features':snapshot.get('features'),'data_cutoff':snapshot.get('data_cutoff'),'prediction_id':snapshot.get('prediction_id')}) if fields else None,
            'no_future_data':temporal,'side_effects':False,'real_trading':False}

def market_reliability(market):
    m=market or {};rows=int(m.get('rows') or 0);sources=int(m.get('sources') or 0);symbols=int(m.get('symbols') or 0)
    stale_rate=m.get('stale_rate');gap_rate=m.get('gap_rate');dup_rate=m.get('duplicate_rate')
    complete=all(v is not None for v in (stale_rate,gap_rate,dup_rate))
    healthy=bool(rows>0 and symbols>0 and complete and float(stale_rate)<=0.05 and float(gap_rate)<=0.05 and float(dup_rate)<=0.01)
    return {'rows':rows,'sources':sources,'symbols':symbols,'metrics_complete':complete,'healthy':healthy,
            'broken_provider_paths':int(m.get('broken_provider_paths') or 0),'http_404_count':int(m.get('http_404_count') or 0),'real_trading':False}

def execution_model(order,quote,*,commission_bps=1.0,impact_bps=2.0,liquidity_fraction=0.01):
    """Deterministic PAPER-only fill model. Requires observed bid/ask and volume; otherwise rejects."""
    if not order or not quote:return {'status':'REJECTED','reason':'missing_order_or_quote','fills':[],'real_trading':False}
    side=str(order.get('side') or '').upper();qty=float(order.get('requested_qty') or 0)
    try:bid=float(quote.get('bid'));ask=float(quote.get('ask'));vol=float(quote.get('volume'))
    except Exception:return {'status':'REJECTED','reason':'missing_observed_liquidity','fills':[],'real_trading':False}
    if side not in {'BUY','SELL'} or qty<=0 or bid<=0 or ask<bid or vol<=0:return {'status':'REJECTED','reason':'invalid_execution_inputs','fills':[],'real_trading':False}
    if quote.get('market_open') is False:return {'status':'REJECTED','reason':'market_closed','fills':[],'real_trading':False}
    max_fill=max(0.0,vol*max(0.0,float(liquidity_fraction)))
    fill_qty=min(qty,max_fill)
    if fill_qty<=0:return {'status':'REJECTED','reason':'insufficient_liquidity','fills':[],'real_trading':False}
    mid=(bid+ask)/2;spread=max(0.0,ask-bid);base=ask if side=='BUY' else bid
    participation=min(1.0,fill_qty/max(vol,1e-12));impact=mid*(float(impact_bps)/10000.0)*(1+participation)
    px=base+impact if side=='BUY' else max(1e-12,base-impact)
    commission=fill_qty*px*(float(commission_bps)/10000.0)
    spread_cost=fill_qty*spread/2.0;slippage_cost=fill_qty*abs(px-base)
    status='FILLED' if math.isclose(fill_qty,qty,rel_tol=1e-12,abs_tol=1e-12) else 'PARTIAL'
    return {'status':status,'fills':[{'fill_seq':1,'qty':fill_qty,'price':px,'fee':commission,'spread_cost':spread_cost,'slippage_cost':slippage_cost}],
            'remaining_qty':max(0.0,qty-fill_qty),'observed_quote_required':True,'real_trading':False}

def board(*,maturity=None,intervals=None,restart=None,feature_snapshots=None,decision_rows=None,market=None,quotes=None,execution=None,accounting=None):
    maturity=maturity or {};restart=restart or {};feature_snapshots=list(feature_snapshots or []);decision_rows=list(decision_rows or [])
    quotes=list(quotes or []);execution=execution or {};accounting=accounting or {}
    mi=maturity_integrity(maturity,intervals);fa=feature_authority(feature_snapshots);chain=decision_chain(decision_rows,feature_snapshots);mr=market_reliability(market)
    t=[]
    # 171-176: durable time authority
    t.append(_task(171,'PASS' if mi['server_overlap_guard'] and not mi['overlap'] else 'PENDING_PROOF',no_double_count=not mi['overlap'],authority=mi))
    t.append(_task(172,'PASS' if mi['server_no_backfill'] and restart.get('downtime_credit') is False else 'PENDING_PROOF',downtime_credit=restart.get('downtime_credit'),authority=mi))
    restart_ok=bool(restart.get('preserves_prior_valid_hours') is True and restart.get('state_hash_equal') is True and restart.get('session_equal') is True)
    t.append(_task(173,'PASS' if restart_ok else 'PENDING_PROOF',restart=restart))
    for n,h in ((174,72),(175,168),(176,720)):
        t.append(_task(n,'PASS' if mi['valid_forward_hours']>=h else 'PENDING_TIME',required_hours=h,audited_valid_forward_hours=mi['valid_forward_hours']))
    # 177-180: immutable decision-time evidence
    t.append(_task(177,'PASS' if fa['valid_count']>=20 and fa['invalid_count']==0 else ('FAIL_CLOSED' if fa['invalid_count'] else 'PENDING_SAMPLE'),valid_snapshots=fa['valid_count'],invalid_claims=fa['invalid_count']))
    fp_complete=fa['valid_count']>0 and all(s.get('feature_fingerprint') for s in fa['valid'])
    t.append(_task(178,'PASS' if fp_complete and fa['invalid_count']==0 else 'PENDING_DATA',fingerprinted=fp_complete,valid_snapshots=fa['valid_count']))
    chain_ok=chain['linked']>=20 and chain['ambiguous_ids']==0 and chain['temporal_violations']==0
    t.append(_task(179,'PASS' if chain_ok else 'PENDING_DATA',chain=chain))
    sample_dec=decision_rows[0] if decision_rows else None;sample_snap=None
    if sample_dec:
        pid=str(sample_dec.get('prediction_id') or sample_dec.get('local_prediction_id') or '')
        sample_snap=next((s for s in feature_snapshots if str(s.get('prediction_id') or '')==pid),None)
    replay=pit_replay(sample_snap,sample_dec)
    t.append(_task(180,replay.get('status','PENDING_DATA'),replay=replay))
    # 181-184: market authority. Historical + one live source is not multi-provider consensus.
    t.append(_task(181,'PASS' if mr['healthy'] and mr['broken_provider_paths']==0 and mr['http_404_count']==0 else 'PENDING_DATA',market=mr))
    t.append(_task(182,'PASS' if mr['healthy'] and mr['sources']>=2 and (market or {}).get('contemporaneous_multi_source') is True else 'PENDING_DATA',sources=mr['sources'],contemporaneous_multi_source=(market or {}).get('contemporaneous_multi_source') is True))
    t.append(_task(183,'PASS' if mr['healthy'] else 'PENDING_DATA',stale_rate=(market or {}).get('stale_rate'),gap_rate=(market or {}).get('gap_rate'),duplicate_rate=(market or {}).get('duplicate_rate')))
    observed=[q for q in quotes if q.get('bid') is not None and q.get('ask') is not None and q.get('volume') is not None and q.get('source')]
    t.append(_task(184,'PASS' if len(observed)>=20 else 'PENDING_DATA',observed_quotes=len(observed),imputation_allowed=False))
    # 185-190: execution reality
    model_features=execution.get('model_features') or {}
    required=('observed_spread','observed_volume','market_hours','partial_fills','rejects','slippage','commissions','liquidity_limits')
    model_ok=all(model_features.get(k) is True for k in required)
    t.append(_task(185,'PASS' if model_ok else 'PENDING_IMPLEMENTATION',features=model_features,paper_only=True))
    calibrated=bool(execution.get('slippage_observations',0)>=30 and execution.get('slippage_calibrated') is True)
    t.append(_task(186,'PASS' if calibrated else 'PENDING_SAMPLE',slippage_observations=execution.get('slippage_observations',0),calibrated=calibrated))
    t.append(_task(187,'PASS' if execution.get('partial_fill_tested') is True and execution.get('partial_fill_persisted') is True else 'PENDING_PROOF',partial_fill_tested=execution.get('partial_fill_tested'),partial_fill_persisted=execution.get('partial_fill_persisted')))
    failure_modes=('reject','timeout','market_closed','insufficient_liquidity','stale_quote')
    fm=execution.get('failure_modes') or {}
    t.append(_task(188,'PASS' if all(fm.get(x) is True for x in failure_modes) else 'PENDING_PROOF',failure_modes={x:fm.get(x) for x in failure_modes}))
    atomic=bool(accounting.get('atomic_fill_accounting') is True and accounting.get('unaccounted_fills')==0 and accounting.get('equation_error')==0)
    t.append(_task(189,'PASS' if atomic else 'FAIL_CLOSED' if accounting.get('unaccounted_fills',0)>0 else 'PENDING_PROOF',accounting=accounting))
    critical={x['task']:x['status'] for x in t if x['task'] in (181,183,184,185,189)}
    reality_ok=all(v=='PASS' for v in critical.values())
    t.append(_task(190,'PASS' if reality_ok else 'BLOCKED',critical=critical,learning_from_unrealistic_execution_allowed=False))
    return {'status':'TASKS_171_190_EVALUATED','tasks':t,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
