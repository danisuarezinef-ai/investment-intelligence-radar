"""PAPER certification and closure tasks 131-160.

Fail-closed certification layer. This module cannot enable live execution, automatic
promotion/release, or Setup 1.6. Historical/counterfactual evidence cannot earn
forward-maturity credit.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
import hashlib, json, math, statistics

REAL_TRADING=False
REQUIRED_HORIZONS=('1d','1w','1m','3m')


def _f(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception:return None

def _dt(v):
    try:
        d=datetime.fromisoformat(str(v).replace('Z','+00:00'))
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:return None

def _hash(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def _task(n,status,**e):return {'task':n,'status':status,'evidence':{**e,'real_trading':False},'real_trading':False}

def deployment_verify(deployment):
    d=deployment or {}; ok=d.get('status')=='SUCCESS' and bool(d.get('commit_sha')) and d.get('commit_sha')==d.get('expected_sha')
    return _task(131,'PASS' if ok else 'PENDING',deployment=d,sha_match=ok)

def ci_integrity(ci):return _task(132,'PASS' if (ci or {}).get('status')=='PASS' else 'PENDING',ci=ci or {})
def runtime_integrity(runtime):
    r=runtime or {};ok=bool(r.get('main_sha') and r.get('deployed_sha')==r.get('main_sha') and r.get('entrypoint_sha')==r.get('main_sha'))
    return _task(133,'PASS' if ok else 'PENDING',runtime=r,sha_chain_match=ok)

def feature_coverage(rows):
    prospective=[r for r in rows or [] if r.get('prospective_capture') is True]
    valid=[r for r in prospective if isinstance(r.get('features'),dict) and bool(r.get('features')) and r.get('feature_fingerprint') and r.get('immutable') is True and r.get('backfilled') is not True]
    cov=len(valid)/len(prospective) if prospective else 0.0
    return _task(134,'PASS' if prospective and cov==1 else ('FAIL_CLOSED' if prospective else 'PENDING_DATA'),n=len(prospective),valid_n=len(valid),coverage=cov)

def referential_integrity(decisions,snapshots):
    by=defaultdict(list)
    for s in snapshots or []:by[str(s.get('prediction_id'))].append(s)
    bad=[]
    for r in decisions or []:
        pid=str(r.get('prediction_id') or '')
        matches=by.get(pid,[])
        if len(matches)!=1:bad.append({'prediction_id':pid,'snapshot_count':len(matches)})
    return _task(135,'PASS' if decisions and not bad else ('FAIL_CLOSED' if bad else 'PENDING_DATA'),decisions=len(decisions or []),violations=bad[:50])

def immutable_decision_package(packages):
    bad=[]
    for p in packages or []:
        body={k:p.get(k) for k in ('prediction_id','features','thesis','regime','model_version','provenance')}
        if not p.get('package_hash') or p.get('package_hash')!=_hash(body) or p.get('immutable') is not True:bad.append(p.get('prediction_id'))
    return _task(136,'PASS' if packages and not bad else ('FAIL_CLOSED' if bad else 'PENDING_DATA'),n=len(packages or []),violations=bad[:50])

def outcome_link_integrity(rows):
    bad=[]
    seen=set()
    for r in rows or []:
        if r.get('matured') is not True:continue
        pid=str(r.get('prediction_id') or '');oid=str((r.get('outcome') or {}).get('prediction_id') or pid)
        if not pid or oid!=pid or (pid,r.get('horizon')) in seen:bad.append(pid)
        seen.add((pid,r.get('horizon')))
    return _task(137,'PASS' if seen and not bad else ('FAIL_CLOSED' if bad else 'PENDING_DATA'),linked=len(seen),violations=bad[:50])

def temporal_causality(rows):
    bad=[];n=0
    for r in rows or []:
        known=_dt(r.get('known_at_boundary') or (r.get('provenance') or {}).get('known_at_boundary'));created=_dt(r.get('created_at'));evaluated=_dt(r.get('evaluated_at'))
        if created and known:
            n+=1
            if known>created or (evaluated and created>=evaluated):bad.append(r.get('prediction_id'))
    return _task(138,'PASS' if n and not bad else ('FAIL_CLOSED' if bad else 'PENDING_DATA'),checked=n,violations=bad[:50],rule='known_at<=decision_at<outcome_at')

def no_lookahead_monitor(rows):
    violations=[r.get('prediction_id') for r in rows or [] if (r.get('quality_checks') or {}).get('lookahead') is True or (r.get('provenance') or {}).get('lookahead') is True]
    return _task(139,'PASS' if rows and not violations else ('FAIL_CLOSED' if violations else 'PENDING_DATA'),violations=violations[:50],continuous_monitor=True)

def corruption_detector(records):
    ids={};bad=[]
    for r in records or []:
        rid=str(r.get('id') or r.get('prediction_id') or '');h=r.get('hash') or r.get('prediction_hash')
        if rid in ids and ids[rid]!=h:bad.append(rid)
        ids[rid]=h
        if r.get('mutated') is True or r.get('retroactive_change') is True:bad.append(rid)
    return _task(140,'PASS' if records and not bad else ('FAIL_CLOSED' if bad else 'PENDING_DATA'),records=len(records or []),violations=sorted(set(bad))[:50])

def market_reliability(m):
    m=m or {};req=('coverage','latency_ms_p95','stale_rate','gap_rate','duplicate_rate','timestamp_error_rate')
    complete=all(_f(m.get(k)) is not None for k in req)
    healthy=complete and m['coverage']>=.99 and m['stale_rate']<=.01 and m['gap_rate']<=.01 and m['duplicate_rate']<=.005 and m['timestamp_error_rate']==0
    return _task(141,'PASS' if healthy else ('ATTENTION' if complete else 'PENDING_DATA'),market=m)

def symbol_health(symbols):
    bad=[s for s,v in (symbols or {}).items() if not isinstance(v,dict) or v.get('healthy') is not True]
    return _task(142,'PASS' if symbols and not bad else ('ATTENTION' if symbols else 'PENDING_DATA'),blocked_symbols=bad,new_paper_risk_blocked_for_unhealthy=True)

def provider_failover(p):
    p=p or {};ok=bool(p.get('primary') and p.get('secondary') and p.get('pit_compatible') is True and p.get('fail_closed_on_divergence') is True and p.get('tested') is True)
    return _task(143,'PASS' if ok else 'PENDING_PROOF',provider=p)

def price_consensus(p):
    p=p or {};spread=_f(p.get('max_cross_provider_divergence'))
    ok=bool((p.get('providers') or 0)>=2 and spread is not None and spread<=.01)
    return _task(144,'PASS' if ok else 'PENDING_DATA',consensus=p,can_only_block_or_reduce_risk=True)

def spread_capture(obs):
    xs=[x for x in obs or [] if _f(x.get('bid')) is not None and _f(x.get('ask')) is not None and _dt(x.get('observed_at')) and x.get('source')]
    bad=[x for x in xs if float(x['ask'])<float(x['bid'])]
    return _task(145,'PASS' if xs and not bad else ('FAIL_CLOSED' if bad else 'PENDING_DATA'),n=len(xs),observed_not_imputed=True)

def liquidity_v2(obs):
    good=[x for x in obs or [] if all(x.get(k) is not None for k in ('spread','volume','observed_at','source')) and _f(x.get('volume')) and _f(x.get('volume'))>0]
    return _task(146,'PASS' if good and len(good)==len(obs or []) else 'PENDING_DATA',n=len(obs or []),valid_n=len(good),imputation_forbidden=True)

def market_hours(e):
    e=e or {};ok=all(e.get(k) is True for k in ('calendar_loaded','holidays_supported','early_close_supported','timezone_aware','closed_market_orders_blocked'))
    return _task(147,'PASS' if ok else 'PENDING_IMPLEMENTATION',engine=e)

def execution_v3(e):
    e=e or {};req=('partial_fills','rejects','cancellations','market_hours','spread','slippage','commissions','liquidity_limits','idempotency_key')
    ok=all(e.get(k) is True for k in req)
    return _task(148,'PASS' if ok else 'PENDING_IMPLEMENTATION',execution=e,paper_only=True)

def order_idempotency(events):
    seen={};dup=[]
    for x in events or []:
        key=x.get('idempotency_key');oid=x.get('order_id')
        if not key:dup.append('MISSING_KEY');continue
        if key in seen and seen[key]!=oid:dup.append(key)
        seen[key]=oid
    return _task(149,'PASS' if events and not dup else ('FAIL_CLOSED' if dup else 'PENDING_DATA'),violations=dup[:50])

def execution_accounting_atomicity(events):
    bad=[x.get('fill_id') for x in events or [] if x.get('fill_committed') is not True or x.get('accounting_committed') is not True or x.get('transaction_id') is None]
    return _task(150,'PASS' if events and not bad else ('FAIL_CLOSED' if bad else 'PENDING_DATA'),violations=bad[:50])

def accounting_proof(a):
    a=a or {};cash=_f(a.get('cash'));pos=_f(a.get('positions_value'));rp=_f(a.get('realized_pnl'));up=_f(a.get('unrealized_pnl'));eq=_f(a.get('equity'))
    vals=(cash,pos,rp,up,eq)
    err=None if any(v is None for v in vals) else (cash+pos+rp+up-eq)
    ok=err is not None and abs(err)<=1e-8 and a.get('persisted_reconciled') is True
    return _task(151,'PASS' if ok else ('FAIL_CLOSED' if err is not None else 'PENDING_DATA'),equation_error=err,accounting=a)

def position_lifecycle(records):
    by=defaultdict(set)
    for x in records or []:by[str(x.get('position_id'))].add(str(x.get('event')))
    req={'OPEN','MANAGE','CLOSE','PNL','EVALUATE'};bad=[k for k,v in by.items() if not req.issubset(v)]
    return _task(152,'PASS' if by and not bad else ('PARTIAL' if by else 'PENDING_DATA'),positions=len(by),incomplete=bad[:50])

def learning_chain(records):
    req=('decision_id','order_id','outcome_id','learning_event_id','next_policy_id');bad=[]
    for r in records or []:
        if any(not r.get(k) for k in req) or r.get('temporal_order_valid') is not True:bad.append(r.get('decision_id'))
    return _task(153,'PASS' if records and not bad else ('FAIL_CLOSED' if bad else 'PENDING_DATA'),chains=len(records or []),violations=bad[:50])

def prospective_arena(a):
    a=a or {};ok=bool(a.get('forward_only') is True and a.get('matched_cells') is True and (a.get('challengers') or 0)>=1 and (a.get('forward_n') or 0)>=40 and (a.get('forward_days') or 0)>=14)
    return _task(154,'PASS' if ok else 'PENDING_SAMPLE',arena=a,automatic_promotion=False)

def mutation_sandbox(m):
    m=m or {};ok=all(m.get(k) is True for k in ('isolated','shadow_only','no_champion_mutation','no_live_authority','state_namespace_separate'))
    return _task(155,'PASS' if ok else 'PENDING_IMPLEMENTATION',sandbox=m)

def learning_rollback(r):
    r=r or {};ok=bool(r.get('snapshot_before') and r.get('snapshot_after') and r.get('rollback_tested') is True and r.get('hash_restored') is True)
    return _task(156,'PASS' if ok else 'PENDING_PROOF',rollback=r)

def catastrophic_guard(g):
    g=g or {};ok=all(g.get(k) is True for k in ('freeze_on_drawdown','freeze_on_corruption','freeze_on_unknown_regime','freeze_on_runtime_failure','manual_unfreeze_required'))
    return _task(157,'PASS' if ok else 'PENDING_IMPLEMENTATION',guard=g)

def recovery_stress(s):
    required={'process_kill','supabase_outage','market_data_outage','timeout','redeploy','duplicate_instance','hung_process','restart_mid_persist'}
    got={str(x.get('scenario')) for x in s or [] if x.get('result') in ('EXACT_RECOVERY','FAIL_CLOSED')}
    return _task(158,'PASS' if required.issubset(got) else 'PENDING_PROOF',verified=sorted(got),missing=sorted(required-got))

def observatory(o):
    o=o or {};req=('runtime','market_data','portfolio','learning','agents','errors','forward_evidence','maturity','real_trading_banner')
    ok=all(o.get(k) is True for k in req)
    return _task(159,'PASS' if ok else 'PENDING_IMPLEMENTATION',observatory=o)

def certification_gate(task_states,valid_forward_hours=None):
    critical=(131,132,133,134,135,136,137,138,139,140,141,142,143,145,146,147,148,149,150,151,152,153,155,156,157,158,159)
    blockers=[]
    for n in critical:
        s=(task_states or {}).get(str(n),(task_states or {}).get(n))
        if s not in ('PASS','VERIFIED'):blockers.append(f'task_{n}:{s}')
    h=_f(valid_forward_hours)
    if h is None or h<720:blockers.append('30d_valid_forward_maturity_not_verified')
    return _task(160,'CERTIFIED_PAPER_AUTONOMOUS' if not blockers else 'BLOCKED',blockers=blockers,audited_valid_forward_hours=h,required_valid_forward_hours=720,
                 real_trading_required=False,live_execution_allowed=False,automatic_promotion=False,automatic_release=False,setup_1_6_allowed=False)

def board(**kw):
    vals=[
      deployment_verify(kw.get('deployment')),ci_integrity(kw.get('ci')),runtime_integrity(kw.get('runtime')),
      feature_coverage(kw.get('feature_rows')),referential_integrity(kw.get('decisions'),kw.get('snapshots')),
      immutable_decision_package(kw.get('packages')),outcome_link_integrity(kw.get('rows')),temporal_causality(kw.get('rows')),no_lookahead_monitor(kw.get('rows')),corruption_detector(kw.get('records')),
      market_reliability(kw.get('market')),symbol_health(kw.get('symbols')),provider_failover(kw.get('provider_failover')),price_consensus(kw.get('price_consensus')),
      spread_capture(kw.get('spread_observations')),liquidity_v2(kw.get('liquidity_observations')),market_hours(kw.get('market_hours')),execution_v3(kw.get('execution')),
      order_idempotency(kw.get('order_events')),execution_accounting_atomicity(kw.get('fill_events')),accounting_proof(kw.get('accounting')),position_lifecycle(kw.get('position_events')),
      learning_chain(kw.get('learning_records')),prospective_arena(kw.get('arena')),mutation_sandbox(kw.get('sandbox')),learning_rollback(kw.get('rollback')),
      catastrophic_guard(kw.get('catastrophic_guard')),recovery_stress(kw.get('recovery_scenarios')),observatory(kw.get('observatory'))]
    states={str(x['task']):x['status'] for x in vals}
    states.update({str(k):v for k,v in (kw.get('prior_states') or {}).items()})
    t160=certification_gate(states,kw.get('valid_forward_hours'));vals.append(t160)
    return {'status':'TASKS_131_160_EVALUATED','tasks':{str(x['task']):{'state':x['status'],'evidence':x['evidence']} for x in vals},
            'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
