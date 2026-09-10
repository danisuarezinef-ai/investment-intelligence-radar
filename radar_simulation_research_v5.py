"""Strict out-of-sample research protocol v5.

Tasks 6-10: genuine chronological train/validation/test measurement, expanded stress,
return/risk/cost ranking incl. Sharpe+Sortino, anti-overfit gates, and a fail-closed
SIMULATED→SHADOW funnel. Historical evidence never becomes forward evidence.
"""
from __future__ import annotations
import math,statistics
from radar_simulation_research_v3 import evaluate_config
from radar_simulation_research_v4 import _transform_days
from radar_simulation_v2 import _series_by_day

REAL_TRADING=False

def _f(x,d=0.0):
    return float(x) if isinstance(x,(int,float)) else float(d)

def _partition_metrics(full,baseline):
    fm=list(full.get('equity_marks') or []); bm=list(baseline.get('equity_marks') or [])
    if not fm or len(fm)<=len(bm):return {'completed':False,'reason':'NO_OOS_MARKS','real_trading':False}
    marks=fm[max(0,len(bm)-1):]
    if len(marks)<2:return {'completed':False,'reason':'INSUFFICIENT_OOS_MARKS','real_trading':False}
    rets=[marks[i]/marks[i-1]-1 for i in range(1,len(marks)) if marks[i-1]>0]
    ret=(marks[-1]/marks[0]-1)*100 if marks[0] else 0.0
    peak=marks[0];dd=0.0
    for m in marks:
        peak=max(peak,m);dd=min(dd,(m/peak-1)*100 if peak else 0.0)
    sd=statistics.pstdev(rets) if len(rets)>1 else 0.0
    sharpe=statistics.mean(rets)/sd*math.sqrt(252) if sd else 0.0
    downside=[min(0.0,r) for r in rets];ds=math.sqrt(sum(x*x for x in downside)/len(downside)) if downside else 0.0
    sortino=statistics.mean(rets)/ds*math.sqrt(252) if ds else 0.0
    return {'completed':True,'return_pct':ret,'max_drawdown_pct':dd,'sharpe':sharpe,'sortino':sortino,'marks':len(marks),'real_trading':False}

def evaluate_oos(config,history,window,stress=None):
    # Warm state on history, then score only the appended OOS window.
    base=evaluate_config(config,list(history),stress=stress)
    full=evaluate_config(config,list(history)+list(window),stress=stress)
    out=_partition_metrics(full,base)
    out['history_days']=len(history);out['oos_days']=len(window);out['evidence_class']='SIMULATED_OOS_ONLY';return out

def chronological_walk_forward(config,days=None,folds=4,min_train=90,validation_days=20,test_days=20):
    days=list(days or _series_by_day());n=len(days);rows=[];cursor=int(min_train)
    if n<cursor+int(validation_days)+int(test_days):return {'completed':False,'reason':'INSUFFICIENT_HISTORY','folds':[],'lookahead':False,'real_trading':False}
    for fold in range(max(1,int(folds))):
        v0=cursor;v1=min(n,v0+int(validation_days));t1=min(n,v1+int(test_days))
        if v1-v0<10 or t1-v1<10:break
        train=days[:v0];val=days[v0:v1];test=days[v1:t1]
        vr=evaluate_oos(config,train,val);tr=evaluate_oos(config,train+val,test)
        rows.append({'fold':fold+1,'train_days':len(train),'validation_days':len(val),'test_days':len(test),'validation':vr,'test':tr,'train_end':train[-1][0],'validation_end':val[-1][0],'test_end':test[-1][0],'lookahead':False})
        cursor=t1
    valid=[r for r in rows if r['test'].get('completed')]
    rs=[_f(r['test'].get('return_pct')) for r in valid];dds=[abs(_f(r['test'].get('max_drawdown_pct'))) for r in valid]
    return {'completed':len(valid)>=2,'folds':rows,'mean_test_return_pct':statistics.mean(rs) if rs else None,'test_return_sd':statistics.pstdev(rs) if len(rs)>1 else 0.0,'positive_fraction':sum(x>0 for x in rs)/len(rs) if rs else 0.0,'worst_test_drawdown_pct':-max(dds) if dds else None,'lookahead':False,'evidence_class':'SIMULATED_WALK_FORWARD_OOS_ONLY','real_trading':False}

def expanded_stress_suite(config,days=None):
    days=list(days or _series_by_day());cut=max(90,len(days)-60);hist=days[:cut];oos=days[cut:]
    scenarios={
      'base':({},{}),'costs_2x':({}, {'cost_multiplier':2}),'costs_4x':({}, {'cost_multiplier':4}),
      'gap_-12':({'kind':'gap','pct':-12},{}),'gap_-20':({'kind':'gap','pct':-20},{}),
      'volatility_12':({'kind':'volatility','amp':.12},{}),'volatility_20':({'kind':'volatility','amp':.20},{}),
      'sideways':({'kind':'sideways'},{}),'missing_data':({'kind':'missing_data','every':5},{}),
      'shock_-20':({}, {'shock_pct':-20}),'shock_-30':({}, {'shock_pct':-30})}
    rows={}
    for name,(tx,stress) in scenarios.items():
        transformed=_transform_days(days,tx);h=transformed[:cut];w=transformed[cut:];rows[name]=evaluate_oos(config,h,w,stress)
    ok=[r for r in rows.values() if r.get('completed')];dds=[abs(_f(r.get('max_drawdown_pct'))) for r in ok];rets=[_f(r.get('return_pct')) for r in ok]
    survival=len(ok)==len(rows) and all(x<45 for x in dds) and (min(rets) if rets else -999)>-35
    return {'completed':len(ok)==len(rows),'scenarios':rows,'survival_pass':survival,'worst_drawdown_pct':-max(dds) if dds else None,'worst_return_pct':min(rets) if rets else None,'real_trading':False}

def anti_overfit_gate(walk,stress,max_test_sd=12.0,min_positive_fraction=.5,max_val_test_gap=20.0):
    folds=[r for r in walk.get('folds',[]) if r['test'].get('completed') and r['validation'].get('completed')];block=[]
    tests=[_f(r['test'].get('return_pct')) for r in folds];vals=[_f(r['validation'].get('return_pct')) for r in folds]
    sd=statistics.pstdev(tests) if len(tests)>1 else 0.0;pos=sum(x>0 for x in tests)/len(tests) if tests else 0.0;gap=statistics.mean(abs(a-b) for a,b in zip(vals,tests)) if tests else None
    if len(folds)<2:block.append('TOO_FEW_OOS_FOLDS')
    if sd>max_test_sd:block.append('UNSTABLE_OOS_RETURNS')
    if pos<min_positive_fraction:block.append('LOW_OOS_POSITIVE_FRACTION')
    if gap is not None and gap>max_val_test_gap:block.append('VALIDATION_TEST_DIVERGENCE')
    if not stress.get('survival_pass'):block.append('STRESS_SURVIVAL_FAILED')
    return {'status':'PASS_RESEARCH' if not block else 'REJECT','blockers':block,'oos_return_sd':sd,'positive_test_fraction':pos,'mean_validation_test_gap':gap,'eligible_next_stage':'SHADOW_REVIEW' if not block else 'GRAVEYARD','can_promote_to_paper':False,'automatic_live_promotion':False,'real_trading':False}

def multidimensional_score(base,walk,stress,gate):
    if not base.get('completed') or gate.get('status')!='PASS_RESEARCH':return -1e9
    ret=_f(base.get('return_pct'));dd=abs(_f(base.get('max_drawdown_pct')));sh=_f(base.get('sharpe'));so=_f(base.get('sortino'));stab=max(0,100-_f(walk.get('test_return_sd'))-abs(_f(walk.get('worst_test_drawdown_pct'))));tail=abs(_f(stress.get('worst_drawdown_pct')))
    return .25*ret+.30*sh+.30*so+.25*stab-.75*dd-.45*tail

def research_protocol(config,days=None):
    days=list(days or _series_by_day());cut=max(90,int(len(days)*.75));cut=min(cut,max(1,len(days)-30));base=evaluate_oos(config,days[:cut],days[cut:]);walk=chronological_walk_forward(config,days);stress=expanded_stress_suite(config,days);gate=anti_overfit_gate(walk,stress);score=multidimensional_score(base,walk,stress,gate)
    return {'base':base,'walk_forward':walk,'stress':stress,'gate':gate,'research_score':score,'ranking_dimensions':['OOS_RETURN','MAX_DRAWDOWN','SHARPE','SORTINO','STABILITY','TAIL_RISK'],'funnel':'SIMULATED→SHADOW_REVIEW_OR_GRAVEYARD; PAPER_REQUIRES_INDEPENDENT_FORWARD_GATE','evidence_class':'SIMULATED_RESEARCH_OOS_ONLY','automatic_live_promotion':False,'real_trading':False}
