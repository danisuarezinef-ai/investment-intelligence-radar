"""Forward-only PAPER intelligence tasks 51-60.

51 single forward evidence authority; 52 regime calibration; 53 horizon calibration;
54 dynamic calibration error; 55 confidence haircut; 56 regime transition detector;
57 unknown-regime mode; 58 multidimensional drift; 59 adaptive decay; 60 evidence half-life.
No live trading, promotion, release or Setup 1.6 authority exists here.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
import math, statistics

REAL_TRADING=False
MIN_N=20


def _f(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception:return None

def _dt(v):
    try:return datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(timezone.utc)
    except Exception:return None

def _matured(rows):return [r for r in rows or [] if r.get('matured') is True and r.get('natural') is True]
def _regime(r):return str(((r.get('uncertainty') or {}).get('regime') or 'UNKNOWN')).strip() or 'UNKNOWN'
def _correct(r):
    ret=_f(r.get('net_return')); a=str(r.get('decision_state') or '').upper()
    if ret is None:return None
    if a=='BUY':return 1.0 if ret>0 else 0.0
    if a=='SELL':return 1.0 if ret<0 else 0.0
    if a in {'WAIT','HOLD','ABSTAIN'}:return 1.0 if ret==0 else 0.0
    return None

def _cal(rows):
    vals=[]
    for r in rows:
        c=_f(r.get('confidence')); y=_correct(r)
        if c is not None and y is not None:vals.append((max(0,min(1,c)),y))
    if not vals:return {'n':0,'brier':None,'ece':None}
    brier=sum((c-y)**2 for c,y in vals)/len(vals)
    bins=defaultdict(list)
    for c,y in vals:bins[min(9,int(c*10))].append((c,y))
    ece=sum(len(v)/len(vals)*abs(sum(c for c,_ in v)/len(v)-sum(y for _,y in v)/len(v)) for v in bins.values())
    return {'n':len(vals),'brier':brier,'ece':ece}

def evidence_authority(rows):
    m=_matured(rows); pit=sum(bool((r.get('quality_checks') or {}).get('pit_valid')) for r in m)
    return {'status':'PASS' if m and pit==len(m) else 'FAIL','rows':len(rows or []),'matured_n':len(m),'pit_valid_n':pit,
            'single_authority':'decision_forward_ledger','backfill_allowed':False,'reconstructed':False,'real_trading':False}

def calibration_by_regime(rows):
    g=defaultdict(list)
    for r in _matured(rows):g[_regime(r)].append(r)
    detail={k:_cal(v) for k,v in g.items()}; qualified=sum(v['n']>=MIN_N for v in detail.values())
    return {'status':'PASS' if qualified>=1 else 'PENDING_SAMPLE','regimes':detail,'qualified_regimes':qualified,'real_trading':False}

def calibration_by_horizon(rows):
    g=defaultdict(list)
    for r in _matured(rows):g[str(r.get('horizon') or 'UNKNOWN')].append(r)
    detail={k:_cal(v) for k,v in g.items()}; matured_h=[k for k,v in detail.items() if v['n']>=MIN_N]
    return {'status':'PASS_1D_ONLY' if matured_h==['1d'] else ('PASS' if len(matured_h)>=2 else 'PENDING_SAMPLE'),
            'horizons':detail,'matured_horizons':matured_h,'backfill_allowed':False,'real_trading':False}

def dynamic_calibration_error(rows):
    m=sorted(_matured(rows),key=lambda r:str(r.get('evaluated_at') or ''))
    recent=_cal(m[-50:]); previous=_cal(m[-100:-50]) if len(m)>50 else {'n':0,'brier':None,'ece':None}
    delta=None if recent['ece'] is None or previous['ece'] is None else recent['ece']-previous['ece']
    return {'status':'PASS' if recent['n']>=MIN_N else 'PENDING_SAMPLE','recent':recent,'previous':previous,'ece_delta':delta,
            'drift_alert':bool(delta is not None and delta>0.05),'real_trading':False}

def confidence_haircut(rows):
    dyn=dynamic_calibration_error(rows); reg=calibration_by_regime(rows); penalties=[]
    if dyn.get('drift_alert'):penalties.append(.10)
    worst=max([v.get('ece') or 0 for v in reg.get('regimes',{}).values()] or [0])
    penalties.append(min(.25,worst))
    haircut=min(.35,sum(penalties));
    return {'status':'PASS' if _matured(rows) else 'PENDING_SAMPLE','haircut':haircut,'confidence_multiplier':1.0-haircut,
            'can_only_reduce_confidence':True,'can_increase_exposure':False,'real_trading':False}

def regime_transition_detector(rows):
    seq=[]
    for r in sorted(rows or [],key=lambda x:str(x.get('created_at') or '')):
        rg=_regime(r)
        if rg!='UNKNOWN' and (not seq or seq[-1]!=rg):seq.append(rg)
    return {'status':'PASS' if seq else 'PENDING_SAMPLE','transitions':max(0,len(seq)-1),'regime_sequence':seq[-10:],
            'transition_now':len(seq)>=2,'real_trading':False}

def unknown_regime_mode(rows):
    recent=list(rows or [])[-50:]; unknown=sum(_regime(r)=='UNKNOWN' for r in recent); ratio=unknown/len(recent) if recent else 1.0
    return {'status':'ABSTAIN_UNKNOWN_REGIME' if ratio>0.20 else 'PASS','recent_n':len(recent),'unknown_ratio':ratio,
            'new_risk_allowed':False if ratio>0.20 else True,'forced_trade':False,'real_trading':False}

def multidimensional_drift(rows):
    m=sorted(_matured(rows),key=lambda r:str(r.get('evaluated_at') or '')); a=m[-50:]; b=m[-100:-50]
    def stats(x):
        conf=[_f(r.get('confidence')) for r in x]; conf=[v for v in conf if v is not None]
        ret=[_f(r.get('net_return')) for r in x]; ret=[v for v in ret if v is not None]
        regs=defaultdict(int)
        for r in x:regs[_regime(r)]+=1
        return {'n':len(x),'confidence_mean':statistics.mean(conf) if conf else None,'return_mean':statistics.mean(ret) if ret else None,'regimes':dict(regs)}
    sa,sb=stats(a),stats(b); flags=[]
    if sa['confidence_mean'] is not None and sb['confidence_mean'] is not None and abs(sa['confidence_mean']-sb['confidence_mean'])>.08:flags.append('confidence')
    if sa['return_mean'] is not None and sb['return_mean'] is not None and abs(sa['return_mean']-sb['return_mean'])>.02:flags.append('return')
    if sa['regimes']!=sb['regimes'] and b:flags.append('regime_mix')
    return {'status':'ATTENTION' if flags else ('PASS' if len(a)>=MIN_N else 'PENDING_SAMPLE'),'recent':sa,'previous':sb,'drift_dimensions':flags,'real_trading':False}

def adaptive_decay(rows):
    drift=multidimensional_drift(rows); base_days=30; factor=.5 if drift['status']=='ATTENTION' else 1.0
    return {'status':'PASS' if _matured(rows) else 'PENDING_SAMPLE','base_half_life_days':base_days,'adaptive_half_life_days':base_days*factor,
            'drift_shortens_memory':factor<1.0,'cannot_accelerate_forward_maturity':True,'real_trading':False}

def evidence_half_life(rows,now=None):
    now=now or datetime.now(timezone.utc); decay=adaptive_decay(rows); hl=float(decay['adaptive_half_life_days']); weights=[]
    for r in _matured(rows):
        d=_dt(r.get('evaluated_at') or r.get('created_at'))
        if d:weights.append(2**(-max(0,(now-d).total_seconds()/86400)/hl))
    return {'status':'PASS' if weights else 'PENDING_SAMPLE','half_life_days':hl,'weighted_effective_n':sum(weights),
            'old_evidence_weight_lt_new':True,'backfill_creates_no_age_credit':True,'real_trading':False}

def board(rows):
    funcs=[evidence_authority,calibration_by_regime,calibration_by_horizon,dynamic_calibration_error,confidence_haircut,
           regime_transition_detector,unknown_regime_mode,multidimensional_drift,adaptive_decay,evidence_half_life]
    tasks={str(51+i):{'state':(e:=f(rows)).get('status'),'evidence':e} for i,f in enumerate(funcs)}
    return {'status':'TASKS_51_60_EVALUATED','tasks':tasks,'automatic_promotion':False,'automatic_release':False,
            'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
