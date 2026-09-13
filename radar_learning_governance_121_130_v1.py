"""PAPER-only learning governance tasks 121-130.

121 decision journal completeness; 122 feature snapshot authority; 123 causal attribution v2;
124 multi-horizon outcome evaluator; 125 Champion/Challenger forward tournament;
126 automatic demotion safety; 127 regime specialist evolution; 128 portfolio construction v2;
129 autonomous learning governor; 130 master PAPER control gate.

All automation is bounded to PAPER/shadow. No task may enable live trading, automatic promotion,
automatic release, or Setup 1.6. Counterfactual/historical evidence cannot mature forward gates.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime,timezone
import math,statistics

REAL_TRADING=False
REQUIRED_HORIZONS=('1d','1w','1m','3m')
MIN_N=20


def _f(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def _dt(v):
    try:
        d=datetime.fromisoformat(str(v).replace('Z','+00:00'))
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:return None

def _regime(r):return str(((r.get('uncertainty') or {}).get('regime') or r.get('regime') or 'UNKNOWN')).strip() or 'UNKNOWN'
def _matured(rows):return [r for r in rows or [] if r.get('matured') is True and r.get('natural') is True]
def _edge(r):
    x=_f(r.get('excess_return'))
    if x is None:x=_f(r.get('net_return'))
    return x

def _task(n,x):return {'task':n,'status':x.get('status'),'evidence':x,'real_trading':False}


def decision_journal_completeness(rows):
    required=('prediction_id','created_at','symbol','horizon','model_version','confidence','decision_state')
    inspected=[];complete=0
    for r in rows or []:
        missing=[k for k in required if r.get(k) in (None,'')]
        q=r.get('quality_checks') or {};prov=r.get('provenance') or {}
        if q.get('pit_valid') is not True:missing.append('pit_valid')
        if not isinstance(r.get('uncertainty'),dict):missing.append('uncertainty')
        if not prov:missing.append('provenance')
        ok=not missing;complete+=int(ok)
        if len(inspected)<30:inspected.append({'prediction_id':r.get('prediction_id'),'complete':ok,'missing':missing})
    n=len(rows or []);ratio=complete/n if n else 0.0
    return {'status':'PASS' if n>=MIN_N and ratio==1.0 else ('PARTIAL' if n else 'PENDING_SAMPLE'),
            'n':n,'complete_n':complete,'completeness_ratio':ratio,'required_fields':list(required),
            'examples':inspected,'decision_without_complete_journal_allowed':False,'real_trading':False}


def feature_snapshot_authority(feature_snapshots):
    xs=[]
    for s in feature_snapshots or []:
        ok=bool(s.get('prediction_id') and s.get('captured_at') and s.get('feature_fingerprint') and
                isinstance(s.get('features'),dict) and s.get('immutable') is True and s.get('lookahead') is not True and
                s.get('backfilled') is not True)
        xs.append({'prediction_id':s.get('prediction_id'),'valid':ok,'feature_count':len(s.get('features') or {})})
    valid=sum(x['valid'] for x in xs)
    return {'status':'PASS' if xs and valid==len(xs) else ('FAIL_CLOSED' if xs else 'PENDING_DATA'),
            'n':len(xs),'valid_n':valid,'snapshots':xs[:30],'full_feature_vector_required':True,
            'reconstruction_allowed':False,'backfill_allowed':False,'real_trading':False}


def causal_attribution_v2(rows,feature_snapshots):
    authority=feature_snapshot_authority(feature_snapshots)
    if authority['status']!='PASS':
        return {'status':'PENDING_DATA','reason':'FEATURE_SNAPSHOT_AUTHORITY_NOT_VERIFIED','causal_claim':False,'real_trading':False}
    byid={str(x.get('prediction_id')):x for x in feature_snapshots or []}
    buckets=defaultdict(list);matched=0
    for r in _matured(rows):
        snap=byid.get(str(r.get('prediction_id')));ret=_edge(r)
        if not snap or ret is None:continue
        matched+=1
        for k,v in (snap.get('features') or {}).items():
            fv=_f(v)
            if fv is not None:buckets[str(k)].append((fv,ret))
    out={}
    for k,pairs in buckets.items():
        if len(pairs)<MIN_N:continue
        xs=[a for a,_ in pairs];ys=[b for _,b in pairs];mx=statistics.mean(xs);my=statistics.mean(ys)
        den=sum((x-mx)**2 for x in xs);slope=(sum((x-mx)*(y-my) for x,y in pairs)/den) if den>0 else None
        out[k]={'n':len(pairs),'association_slope':slope}
    return {'status':'PARTIAL_ASSOCIATION' if out else 'PENDING_SAMPLE','matched_n':matched,'feature_associations':out,
            'causal_claim':False,'randomized_identification':False,'observational_attribution_only':True,
            'timing_cost_regime_noise_separation_required_for_causality':True,'real_trading':False}


def multi_horizon_outcome_evaluator(rows):
    out={}
    for h in REQUIRED_HORIZONS:
        xs=[r for r in _matured(rows) if str(r.get('horizon'))==h and _edge(r) is not None]
        vals=[_edge(r) for r in xs]
        out[h]={'n':len(vals),'mean_edge':statistics.mean(vals) if vals else None,
                'positive_rate':sum(x>0 for x in vals)/len(vals) if vals else None,
                'status':'PASS' if len(vals)>=MIN_N else 'PENDING_SAMPLE'}
    qualified=[h for h,v in out.items() if v['status']=='PASS']
    return {'status':'PASS' if len(qualified)==4 else ('PARTIAL' if qualified else 'PENDING_SAMPLE'),
            'horizons':out,'qualified_horizons':qualified,'horizon_borrowing_forbidden':True,
            'backfill_maturity_credit':False,'real_trading':False}


def forward_tournament(rows):
    groups=defaultdict(list)
    for r in _matured(rows):
        model=str(r.get('model_version') or '');e=_edge(r);d=_dt(r.get('created_at'))
        if model and e is not None and d:groups[model].append((d,e,_regime(r),str(r.get('horizon'))))
    models=[]
    for model,xs in groups.items():
        xs=sorted(xs,key=lambda x:x[0]);days=(xs[-1][0].date()-xs[0][0].date()).days+1 if xs else 0
        cells={(x[2],x[3]) for x in xs}
        models.append({'model_version':model,'n':len(xs),'forward_days':days,'mean_edge':statistics.mean(x[1] for x in xs),
                       'cells':sorted('|'.join(c) for c in cells),'eligible':len(xs)>=40 and days>=14})
    eligible=sorted([m for m in models if m['eligible']],key=lambda x:x['mean_edge'],reverse=True)
    shared=[]
    if len(eligible)>=2:shared=sorted(set(eligible[0]['cells']) & set(eligible[1]['cells']))
    return {'status':'SHADOW_TOURNAMENT_READY' if len(eligible)>=2 and shared else 'PENDING_SAMPLE','models':models,
            'leader':eligible[0] if eligible else None,'challenger':eligible[1] if len(eligible)>1 else None,'shared_cells':shared,
            'automatic_promotion':False,'automatic_replacement':False,'requires_new_prospective_forward_evidence':True,
            'scope':'SHADOW_PAPER_ONLY','real_trading':False}


def automatic_demotion_safety(rows,active_model=None):
    xs=[r for r in _matured(rows) if active_model in (None,r.get('model_version')) and _edge(r) is not None]
    xs=sorted(xs,key=lambda r:str(r.get('created_at') or ''))
    if len(xs)<40:return {'status':'PENDING_SAMPLE','n':len(xs),'demotion_action':'NONE','real_trading':False}
    cut=len(xs)//2;old=[_edge(r) for r in xs[:cut]];new=[_edge(r) for r in xs[cut:]]
    delta=statistics.mean(new)-statistics.mean(old);degraded=delta<-.002 or statistics.mean(new)<0
    return {'status':'ATTENTION' if degraded else 'PASS','n':len(xs),'older_mean':statistics.mean(old),'recent_mean':statistics.mean(new),
            'degraded':degraded,'demotion_action':'QUARANTINE_OR_REDUCE_PAPER_WEIGHT' if degraded else 'NONE',
            'can_reduce_paper_risk':True,'can_promote_replacement':False,'live_effect':False,'real_trading':False}


def regime_specialist_evolution(rows):
    by=defaultdict(lambda:defaultdict(list))
    for r in _matured(rows):
        e=_edge(r);model=str(r.get('model_version') or '');reg=_regime(r)
        if e is not None and model and reg!='UNKNOWN':by[reg][model].append(e)
    specialists={}
    for reg,models in by.items():
        elig=[(statistics.mean(v),m,len(v)) for m,v in models.items() if len(v)>=MIN_N]
        if elig:
            mean_edge,m,n=max(elig);specialists[reg]={'model_version':m,'n':n,'mean_edge':mean_edge}
    return {'status':'PASS' if len(specialists)>=2 else 'PENDING_SAMPLE','specialists':specialists,
            'specialization_requires_forward_evidence':True,'unknown_regime_cannot_train_specialist':True,
            'automatic_live_routing':False,'real_trading':False}


def portfolio_construction_v2(candidates,risk=None):
    risk=risk or {};max_positions=min(5,int(risk.get('max_positions') or 5));max_pos=min(.20,_f(risk.get('max_position')) or .20)
    total_budget=min(.70,_f(risk.get('risk_budget')) or .70);items=[]
    for c in candidates or []:
        if str(c.get('decision_state') or '').upper()!='BUY':continue
        conf=max(0.0,min(1.0,_f(c.get('confidence')) or 0.0));reg=_regime(c)
        score=conf*(.5 if reg=='UNKNOWN' else 1.0)
        if score>0:items.append((score,c))
    items=sorted(items,key=lambda x:x[0],reverse=True)[:max_positions];den=sum(x[0] for x in items)
    alloc=[]
    remaining=total_budget
    for score,c in items:
        w=min(max_pos,total_budget*score/den) if den>0 else 0.0;w=min(w,remaining);remaining-=w
        alloc.append({'symbol':c.get('symbol'),'horizon':c.get('horizon'),'paper_weight':w,'confidence':c.get('confidence'),'regime':_regime(c)})
    return {'status':'PASS' if alloc else 'PENDING_SAMPLE','allocations':alloc,'sum_weights':sum(x['paper_weight'] for x in alloc),
            'max_positions':max_positions,'max_position':max_pos,'risk_budget':total_budget,'orders_created':False,
            'correlation_liquidity_es_must_be_supplied_by_upstream_risk_gate':True,'live_execution_allowed':False,'real_trading':False}


def autonomous_learning_governor(inputs):
    inputs=inputs or {};critical=inputs.get('critical_integrity') is True;evidence=inputs.get('evidence_quality') is True
    drift=inputs.get('severe_drift') is True;unknown=inputs.get('unknown_regime') is True;degraded=inputs.get('champion_degraded') is True
    if not critical:mode='FREEZE_ALL_LEARNING'
    elif not evidence:mode='OBSERVE_ONLY'
    elif drift or unknown:mode='FREEZE_MUTATION_AND_INCREASE_ABSTENTION'
    elif degraded:mode='SHADOW_CHALLENGER_SEARCH'
    else:mode='BOUNDED_PAPER_LEARNING'
    return {'status':'PASS' if critical else 'FAIL_CLOSED','mode':mode,'bounded_mutation':mode=='BOUNDED_PAPER_LEARNING',
            'can_reduce_risk':True,'can_increase_live_risk':False,'automatic_live_promotion':False,
            'same_outcome_training_before_evaluation_forbidden':True,'real_trading':False}


def master_paper_control_gate(task_states,critical_runtime=None,valid_forward_hours=None):
    task_states=task_states or {};critical_runtime=critical_runtime or {}
    critical_tasks=(28,29,80,99,113,119,121,122,124,129)
    blockers=[]
    for n in critical_tasks:
        s=task_states.get(str(n),task_states.get(n))
        if s not in ('PASS','VERIFIED'):blockers.append(f'task_{n}:{s}')
    if critical_runtime.get('lease_held') is not True:blockers.append('lease_not_held')
    if critical_runtime.get('durable_sync')!='RECONCILED':blockers.append('durable_sync_not_reconciled')
    if critical_runtime.get('exact_restore') is not True:blockers.append('exact_restore_not_verified')
    h=_f(valid_forward_hours)
    if h is None or h<720:blockers.append('30d_valid_forward_maturity_not_verified')
    return {'status':'PASS' if not blockers else 'BLOCKED','blockers':blockers,'required_critical_tasks':list(critical_tasks),
            'audited_valid_forward_hours':h,'required_valid_forward_hours':720,'new_paper_risk_allowed':not blockers,
            'live_execution_allowed':False,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,
            'real_trading':False}


def board(rows,feature_snapshots=None,candidates=None,risk=None,governor_inputs=None,task_states=None,critical_runtime=None,valid_forward_hours=None):
    vals=[decision_journal_completeness(rows),feature_snapshot_authority(feature_snapshots),causal_attribution_v2(rows,feature_snapshots),
          multi_horizon_outcome_evaluator(rows),forward_tournament(rows),automatic_demotion_safety(rows),regime_specialist_evolution(rows),
          portfolio_construction_v2(candidates or [],risk),autonomous_learning_governor(governor_inputs),
          master_paper_control_gate(task_states or {},critical_runtime,valid_forward_hours)]
    return {'status':'TASKS_121_130_EVALUATED','tasks':{str(121+i):{'state':x.get('status'),'evidence':x} for i,x in enumerate(vals)},
            'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,
            'live_execution_allowed':False,'real_trading':False}
