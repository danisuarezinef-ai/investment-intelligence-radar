"""Part II validation governance for forward/shadow evidence.

This module evaluates evidence quality and validation integrity. It never enables
real trading, never backfills forward evidence, and never invents missing metrics.
"""
from __future__ import annotations
from datetime import datetime
from radar_promotion_attribution_v1 import promotion_gate, degradation_check

REAL_TRADING=False


def _dt(x):
    if not x:return None
    try:return datetime.fromisoformat(str(x).replace('Z','+00:00'))
    except Exception:return None


def walk_forward_audit(folds,min_folds=4):
    """Audit chronological fold separation and basic OOS integrity."""
    checked=[];violations=[]
    for i,f in enumerate(folds or [],1):
        train_start=_dt(f.get('train_start'));train_end=_dt(f.get('train_end'))
        val_start=_dt(f.get('validation_start'));val_end=_dt(f.get('validation_end'))
        n_train=f.get('observations_train');n_val=f.get('observations_validation')
        temporal=bool(train_start and train_end and val_start and val_end and train_start<=train_end<val_start<=val_end)
        counts=bool(isinstance(n_train,int) and n_train>0 and isinstance(n_val,int) and n_val>0)
        holdout=f.get('holdout') is True
        lookahead=f.get('lookahead') is False
        ok=temporal and counts and holdout and lookahead
        row={'fold':i,'temporal_separation':temporal,'positive_counts':counts,'holdout':holdout,'lookahead_false':lookahead,'ok':ok}
        checked.append(row)
        if not ok:violations.append(i)
    sufficient=len(checked)>=int(min_folds)
    return {'folds':len(checked),'minimum_folds':int(min_folds),'sufficient_folds':sufficient,
            'violations':violations,'pass':sufficient and not violations,'checks':checked,
            'real_trading':False}


def shadow_evidence_summary(records,started_at=None):
    """Summarize immutable matured forward records without backfill assumptions."""
    rows=list(records or []);valid=[];invalid=[]
    boundary=_dt(started_at)
    for idx,r in enumerate(rows):
        created=_dt(r.get('created_at'));evaluated=_dt(r.get('evaluated_at'))
        immutable=r.get('immutable') is True
        no_backfill=(boundary is None or (created is not None and created>=boundary))
        matured=r.get('matured') is True and evaluated is not None
        has_outcome=r.get('return_pct') is not None or r.get('return') is not None
        if immutable and no_backfill and matured and has_outcome:
            valid.append(r)
        else:
            invalid.append({'index':idx,'immutable':immutable,'no_backfill':no_backfill,'matured':matured,'has_outcome':has_outcome})
    returns=[];hits=[]
    for r in valid:
        raw=r.get('return_pct') if r.get('return_pct') is not None else r.get('return')
        try:
            v=float(raw)
            if r.get('return_pct') is None:v*=100.0
            returns.append(v);hits.append(1.0 if v>0 else 0.0)
        except Exception:pass
    return {'records':len(rows),'valid_matured':len(valid),'invalid_records':invalid,
            'mean_return_pct':sum(returns)/len(returns) if returns else None,
            'hit_rate':sum(hits)/len(hits) if hits else None,
            'boundary_verified':boundary is not None,
            'real_trading':False}


def validation_gate(evidence,folds,degradation_reference=None,degradation_current=None,policy=None):
    """Combine promotion policy, OOS audit and degradation state into review readiness."""
    promo=promotion_gate(evidence or {},policy=policy)
    wf=walk_forward_audit(folds)
    deg=None
    if degradation_reference is not None or degradation_current is not None:
        deg=degradation_check(degradation_reference or {},degradation_current or {})
    degradation_clear=(deg is None or deg.get('degraded') is False)
    evidence_complete=(deg is None or deg.get('evidence_complete') is True)
    ready=bool(promo['ready_for_live_review'] and wf['pass'] and degradation_clear and evidence_complete)
    blockers=[]
    if not promo['ready_for_live_review']:blockers.extend('promotion:'+x for x in promo['failed'])
    if not wf['pass']:blockers.append('walk_forward_integrity')
    if deg is not None and deg.get('degraded') is True:blockers.append('performance_degradation')
    if deg is not None and deg.get('evidence_complete') is not True:blockers.append('degradation_evidence_incomplete')
    return {'ready_for_live_review':ready,'blockers':blockers,'promotion':promo,'walk_forward':wf,
            'degradation':deg,'can_trade':False,'auto_promote':False,'real_trading':False}


def degradation_action(degradation,current_multiplier=1.0):
    """Recommend conservative exposure scaling; never applies it automatically."""
    try:current=max(0.0,min(1.0,float(current_multiplier)))
    except Exception:current=0.0
    if not isinstance(degradation,dict) or degradation.get('evidence_complete') is not True:
        target=min(current,0.50);reason='incomplete_degradation_evidence'
    elif degradation.get('degraded') is True:
        target=min(current,0.50);reason='verified_degradation'
    else:
        target=current;reason='no_verified_degradation'
    return {'current_multiplier':current,'recommended_multiplier':target,'reason':reason,
            'automatic_application':False,'real_trading':False}
