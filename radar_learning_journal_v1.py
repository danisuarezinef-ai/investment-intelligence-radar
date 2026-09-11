"""Falsifiable PAPER learning journal primitives.

Lessons are hypotheses with evidence requirements, not permanent truths. A lesson can
be confirmed, weakened or invalidated as new regime/forward evidence arrives.
"""
from __future__ import annotations

import hashlib
import json

REAL_TRADING=False


def _canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),default=str)

def lesson_id(subject,claim,created_at=''):
    return hashlib.sha256(f'{subject}|{claim}|{created_at}'.encode()).hexdigest()[:24]


def lesson_candidate(*,subject,claim,evidence=None,regime=None,horizon=None,created_at=None,min_future_tests=5):
    evidence=evidence or {}
    return {'lesson_id':lesson_id(subject,claim,created_at or ''),'subject':str(subject),'claim':str(claim),
            'status':'HYPOTHESIS','created_at':created_at,'regime':regime,'horizon':horizon,
            'supporting_evidence':evidence,'required_future_tests':max(1,int(min_future_tests)),
            'future_tests':0,'future_support':0,'future_refute':0,'confidence':'LOW',
            'falsifiable':True,'can_trade':False,'real_trading':False}


def update_lesson(lesson,test_outcomes):
    out=dict(lesson or {});tests=[x for x in (test_outcomes or []) if x in (True,False)]
    support=sum(1 for x in tests if x);refute=len(tests)-support;required=max(1,int(out.get('required_future_tests') or 5))
    ratio=support/len(tests) if tests else None
    if len(tests)<required:status='TESTING';confidence='LOW'
    elif ratio>=.70:status='SUPPORTED';confidence='MEDIUM' if len(tests)<required*3 else 'HIGH'
    elif ratio<=.40:status='INVALIDATED';confidence='HIGH' if len(tests)>=required*2 else 'MEDIUM'
    else:status='WEAKENED';confidence='LOW'
    out.update({'status':status,'future_tests':len(tests),'future_support':support,'future_refute':refute,
                'support_ratio':ratio,'confidence':confidence,'can_trade':False,'real_trading':False})
    return out


def false_learning_check(lesson,regime_results):
    """Flag apparent lessons that collapse outside the originating regime."""
    lesson=lesson or {};results=regime_results or {};valid={k:v for k,v in results.items() if isinstance(v,(int,float))}
    if len(valid)<2:return {'status':'INSUFFICIENT_REGIME_EVIDENCE','false_learning_risk':None,'real_trading':False}
    origin=str(lesson.get('regime') or '');origin_value=valid.get(origin);others=[v for k,v in valid.items() if k!=origin]
    if origin_value is None or not others:return {'status':'INSUFFICIENT_REGIME_EVIDENCE','false_learning_risk':None,'real_trading':False}
    mean_other=sum(others)/len(others);gap=float(origin_value)-float(mean_other)
    risk='HIGH' if origin_value>0 and mean_other<0 else ('MEDIUM' if gap>5 else 'LOW')
    return {'status':'AVAILABLE','false_learning_risk':risk,'origin_value':origin_value,'other_regime_mean':mean_other,
            'gap':gap,'real_trading':False}


def loss_autopsy(decision,context=None):
    d=decision or {};ctx=context or {};pnl=float(d.get('realized_pnl') or 0);ret=d.get('return_pct')
    factors=[]
    if pnl<0:factors.append('REALIZED_LOSS')
    if float(d.get('costs') or 0)>abs(pnl)*.25 and pnl!=0:factors.append('COST_DRAG_MATERIAL')
    if ctx.get('concentration_high'):factors.append('CONCENTRATION')
    if ctx.get('regime_mismatch'):factors.append('REGIME_MISMATCH')
    if ctx.get('confidence_overstated'):factors.append('OVERCONFIDENCE')
    if ctx.get('data_quality_degraded'):factors.append('DATA_QUALITY')
    return {'symbol':d.get('symbol'),'entry_ts':d.get('entry_ts'),'exit_ts':d.get('exit_ts'),
            'realized_pnl':pnl,'return_pct':ret,'entry_reason':d.get('entry_reason'),'exit_reason':d.get('exit_reason'),
            'factors':factors,'ex_ante_reasonable':ctx.get('ex_ante_reasonable'),'lesson_status':'CANDIDATE_ONLY',
            'automatic_strategy_change':False,'can_trade':False,'real_trading':False}
