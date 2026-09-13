"""PAPER-only validation and autonomous readiness tasks 91-100.

91 multi-regime validation; 92 multi-horizon validation; 93 cross-regime generalization;
94 cross-horizon generalization; 95 stability vs performance; 96 forward consistency;
97 evidence quality v2; 98 autonomous learning health; 99 autonomous PAPER readiness v2;
100 30-day PAPER proof package.

No task may create maturity credit from wall-clock/backfill/counterfactual evidence or enable live trading.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
import math, statistics
REAL_TRADING=False
MIN_N=20
REQUIRED_HORIZONS=('1d','1w','1m','3m')

def _f(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def _dt(v):
    if not v:return None
    try:
        s=str(v).replace('Z','+00:00');d=datetime.fromisoformat(s)
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:return None

def _regime(r):return str(((r.get('uncertainty') or {}).get('regime') or 'UNKNOWN')).strip() or 'UNKNOWN'
def _matured(rows):return [r for r in rows or [] if r.get('matured') is True and r.get('natural') is True]
def _edge(r):
    x=_f(r.get('excess_return'))
    if x is None:x=_f(r.get('net_return'))
    return x

def _summary(xs):
    xs=[x for x in xs if x is not None]
    if not xs:return {'n':0,'mean':None,'positive_rate':None,'stdev':None}
    return {'n':len(xs),'mean':statistics.mean(xs),'positive_rate':sum(x>0 for x in xs)/len(xs),'stdev':statistics.stdev(xs) if len(xs)>1 else 0.0}

def multi_regime_validation(rows):
    groups=defaultdict(list)
    for r in _matured(rows):
        e=_edge(r)
        if e is not None:groups[_regime(r)].append(e)
    out={k:_summary(v) for k,v in groups.items()};qualified=[k for k,v in out.items() if k!='UNKNOWN' and v['n']>=MIN_N]
    return {'status':'PASS' if len(qualified)>=2 else 'PENDING_SAMPLE','regimes':out,'qualified_regimes':qualified,
            'minimum_n_per_regime':MIN_N,'unknown_not_counted_as_regime_proof':True,'real_trading':False}

def multi_horizon_validation(rows):
    groups=defaultdict(list)
    for r in _matured(rows):
        e=_edge(r)
        if e is not None:groups[str(r.get('horizon') or 'UNKNOWN')].append(e)
    out={h:_summary(groups.get(h,[])) for h in REQUIRED_HORIZONS};qualified=[h for h,v in out.items() if v['n']>=MIN_N]
    status='PASS' if len(qualified)==len(REQUIRED_HORIZONS) else ('PARTIAL_1D_ONLY' if qualified==['1d'] else 'PENDING_SAMPLE')
    return {'status':status,'horizons':out,'qualified_horizons':qualified,'required_horizons':list(REQUIRED_HORIZONS),
            'no_horizon_inference':True,'real_trading':False}

def cross_regime_generalization(rows):
    v=multi_regime_validation(rows);qs=[v['regimes'][k] for k in v['qualified_regimes']]
    means=[x['mean'] for x in qs if x['mean'] is not None]
    if len(means)<2:return {'status':'PENDING_SAMPLE','score_0_100':None,'qualified_regimes':len(means),'real_trading':False}
    positive=sum(x>0 for x in means)/len(means);disp=statistics.pstdev(means) if len(means)>1 else 0.0
    score=max(0.0,min(100.0,100*(0.7*positive+0.3/(1+50*disp))))
    return {'status':'PASS','score_0_100':round(score,2),'qualified_regimes':len(means),'all_regime_means_positive':all(x>0 for x in means),
            'dispersion':disp,'real_trading':False}

def cross_horizon_generalization(rows):
    v=multi_horizon_validation(rows);means=[v['horizons'][h]['mean'] for h in v['qualified_horizons'] if v['horizons'][h]['mean'] is not None]
    if len(means)<2:return {'status':'PENDING_SAMPLE','score_0_100':None,'qualified_horizons':len(means),'real_trading':False}
    positive=sum(x>0 for x in means)/len(means);disp=statistics.pstdev(means)
    score=max(0.0,min(100.0,100*(0.7*positive+0.3/(1+50*disp))))
    return {'status':'PASS','score_0_100':round(score,2),'qualified_horizons':len(means),'dispersion':disp,
            'all_horizon_means_positive':all(x>0 for x in means),'real_trading':False}

def stability_vs_performance(rows):
    xs=[_edge(r) for r in _matured(rows)];xs=[x for x in xs if x is not None]
    if len(xs)<30:return {'status':'PENDING_SAMPLE','n':len(xs),'score_0_100':None,'real_trading':False}
    mean=statistics.mean(xs);sd=statistics.stdev(xs);down=statistics.mean([abs(x) for x in xs if x<0]) if any(x<0 for x in xs) else 0.0
    stability=1/(1+25*sd+25*down);performance=max(0.0,min(1.0,.5+10*mean));score=100*(.6*stability+.4*performance)
    return {'status':'PASS','n':len(xs),'mean_edge':mean,'stdev':sd,'mean_downside':down,'score_0_100':round(score,2),
            'penalizes_unstable_performance':True,'real_trading':False}

def forward_consistency(rows):
    obs=[]
    for r in _matured(rows):
        d=_dt(r.get('evaluated_at') or r.get('created_at'));e=_edge(r)
        if d and e is not None:obs.append((d,e))
    obs.sort(key=lambda x:x[0]);windows=[]
    for i in range(0,len(obs),20):
        chunk=obs[i:i+20]
        if len(chunk)==20:windows.append({'start':chunk[0][0].isoformat(),'end':chunk[-1][0].isoformat(),'n':20,'mean':statistics.mean(x[1] for x in chunk)})
    if len(windows)<3:return {'status':'PENDING_SAMPLE','windows':windows,'consistent_positive_fraction':None,'real_trading':False}
    frac=sum(w['mean']>0 for w in windows)/len(windows);disp=statistics.pstdev(w['mean'] for w in windows)
    return {'status':'PASS','windows':windows,'consistent_positive_fraction':frac,'window_mean_dispersion':disp,
            'chronological_natural_forward_only':True,'real_trading':False}

def evidence_quality_v2(rows):
    rows=list(rows or []);m=_matured(rows)
    if not rows:return {'status':'PENDING_SAMPLE','score_0_100':0.0,'n_total':0,'n_matured_natural':0,'real_trading':False}
    pit=sum(bool((r.get('quality_checks') or {}).get('pit_valid')) for r in rows)/len(rows)
    natural=len(m)/max(1,sum(bool(r.get('matured')) for r in rows))
    cost=sum(_f(r.get('cost')) is not None for r in m)/max(1,len(m));bench=sum(_f(r.get('benchmark_return')) is not None for r in m)/max(1,len(m))
    regimes=len({ _regime(r) for r in m if _regime(r)!='UNKNOWN'});horizons=len({str(r.get('horizon')) for r in m})
    coverage=min(1.0,.5*(regimes/4)+.5*(horizons/4));score=100*(.30*pit+.25*natural+.15*cost+.15*bench+.15*coverage)
    return {'status':'PASS' if len(m)>=30 and pit==1.0 and natural==1.0 else 'PARTIAL','score_0_100':round(score,2),
            'n_total':len(rows),'n_matured_natural':len(m),'pit_fraction':pit,'natural_maturity_fraction':natural,
            'cost_coverage':cost,'benchmark_coverage':bench,'non_unknown_regimes':regimes,'horizons_seen':horizons,
            'backfill_cannot_improve_score':True,'real_trading':False}

def autonomous_learning_health(rows):
    a=cross_regime_generalization(rows);b=cross_horizon_generalization(rows);c=stability_vs_performance(rows);d=forward_consistency(rows);q=evidence_quality_v2(rows)
    components={'regime_generalization':a.get('score_0_100'),'horizon_generalization':b.get('score_0_100'),'stability':c.get('score_0_100'),'evidence_quality':q.get('score_0_100')}
    vals=[x for x in components.values() if x is not None];score=statistics.mean(vals) if vals else None
    status='PASS' if len(vals)==4 and d.get('status')=='PASS' and score is not None and score>=60 else 'PENDING_EVIDENCE'
    return {'status':status,'score_0_100':round(score,2) if score is not None else None,'components':components,
            'forward_consistency_status':d.get('status'),'automatic_promotion':False,'real_trading':False}

def autonomous_paper_readiness_v2(rows,audited_valid_forward_hours=None,critical_runtime_ok=None,exact_restore_ok=None):
    r91=multi_regime_validation(rows);r92=multi_horizon_validation(rows);r95=stability_vs_performance(rows);r96=forward_consistency(rows);r97=evidence_quality_v2(rows);r98=autonomous_learning_health(rows)
    blockers=[]
    if r91['status']!='PASS':blockers.append('multi_regime_validation')
    if r92['status']!='PASS':blockers.append('multi_horizon_validation')
    if r95['status']!='PASS':blockers.append('stability_not_verified')
    if r96['status']!='PASS':blockers.append('forward_consistency_not_verified')
    if r97['status']!='PASS':blockers.append('evidence_quality_not_full_pass')
    if r98['status']!='PASS':blockers.append('learning_health_not_pass')
    if critical_runtime_ok is not True:blockers.append('critical_runtime_not_verified')
    if exact_restore_ok is not True:blockers.append('exact_restore_not_verified')
    h=_f(audited_valid_forward_hours)
    if h is None or h<720:blockers.append('30d_valid_forward_maturity_not_verified')
    return {'status':'PASS' if not blockers else 'BLOCKED','blockers':blockers,'audited_valid_forward_hours':h,
            'required_valid_forward_hours':720,'wall_clock_credit_forbidden':True,'backfill_credit_forbidden':True,
            'live_execution_allowed':False,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'real_trading':False}

def paper_30d_proof_package(rows,audited_valid_forward_hours=None,runtime_evidence=None):
    m=_matured(rows);dates=[_dt(r.get('created_at')) for r in m];dates=[d for d in dates if d]
    h=_f(audited_valid_forward_hours)
    return {'status':'PROOF_READY' if h is not None and h>=720 else 'PENDING_30D_PROOF',
            'required_valid_forward_hours':720,'audited_valid_forward_hours':h,'matured_natural_rows':len(m),
            'first_natural_prediction':min(dates).isoformat() if dates else None,'last_natural_prediction':max(dates).isoformat() if dates else None,
            'calendar_span_days':((max(dates)-min(dates)).total_seconds()/86400) if len(dates)>=2 else 0.0,
            'calendar_span_is_not_maturity_credit':True,'regime_validation':multi_regime_validation(rows),
            'horizon_validation':multi_horizon_validation(rows),'evidence_quality':evidence_quality_v2(rows),
            'runtime_evidence':runtime_evidence or {},'immutable_requirements':['NO_LOOKAHEAD','NO_BACKFILL_CREDIT','EXACT_RESTORE','REAL_TRADING_FALSE'],
            'live_execution_allowed':False,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'real_trading':False}

def board(rows,audited_valid_forward_hours=None,critical_runtime_ok=None,exact_restore_ok=None,runtime_evidence=None):
    vals=[multi_regime_validation(rows),multi_horizon_validation(rows),cross_regime_generalization(rows),cross_horizon_generalization(rows),
          stability_vs_performance(rows),forward_consistency(rows),evidence_quality_v2(rows),autonomous_learning_health(rows),
          autonomous_paper_readiness_v2(rows,audited_valid_forward_hours,critical_runtime_ok,exact_restore_ok),
          paper_30d_proof_package(rows,audited_valid_forward_hours,runtime_evidence)]
    tasks={str(91+i):{'state':x.get('status'),'evidence':x} for i,x in enumerate(vals)}
    return {'status':'TASKS_91_100_EVALUATED','tasks':tasks,'automatic_promotion':False,'automatic_release':False,
            'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
