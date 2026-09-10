"""Research layer for continuous Simulation Lab experimentation.

Historical/simulated evidence is research-only. It may nominate SHADOW candidates,
but cannot create forward evidence or authorize real trading.

Signals are calculated only from observations available before the execution day.
This prevents same-close lookahead: today's close may be used as today's execution/
marking price, but it cannot influence the signal that triggers that execution.
"""
from __future__ import annotations
import math,statistics
from radar_simulation_v2 import _series_by_day

REAL_TRADING=False
SIGNAL_LAG_DAYS=1


def _momentum(history,symbol,lookback):
    pts=[px[symbol] for _,px in history[-int(lookback):] if symbol in px]
    return (pts[-1]/pts[0]-1) if len(pts)>=4 and pts[0] else None


def evaluate_config(config, days=None, initial_cash=1000.0, stress=None, return_marks=False):
    days=list(days or _series_by_day())
    if len(days)<20:return {'completed':False,'reason':'INSUFFICIENT_HISTORY','real_trading':False}
    stress=stress or {};cash=float(initial_cash);positions={};peak=cash;marks=[];costs=0.0;trades=0
    lf=int(config.get('lookback_fast',20));ls=int(config.get('lookback_slow',60));wf=float(config.get('fast_weight',.65));ws=float(config.get('slow_weight',.35));exit_m=float(config.get('exit_momentum',-5))/100
    fee=.001*float(config.get('cost_multiplier',1))*float(stress.get('cost_multiplier',1));max_positions=max(1,int(config.get('max_positions',5)));per_position=min(.25,max(.02,float(config.get('per_position',.12))))
    history=[]
    for day,prices in days:
        # IMPORTANT: signals use only prior observations. Append the current day only
        # after all decisions/executions for this day have been completed.
        for sym in list(positions):
            if sym not in prices:continue
            m=_momentum(history,sym,lf)
            if m is not None and m<exit_m:
                gross=positions[sym]*prices[sym];c=gross*fee;cash+=gross-c;costs+=c;trades+=1;del positions[sym]
        equity=cash+sum(q*prices.get(s,0) for s,q in positions.items());slots=max_positions-len(positions)
        ranked=[]
        for sym in prices:
            if sym in positions:continue
            a=_momentum(history,sym,lf);b=_momentum(history,sym,ls)
            if a is None:continue
            score=wf*a+ws*(b if b is not None else a);ranked.append((score,sym))
        ranked.sort(reverse=True)
        for score,sym in ranked:
            if slots<=0 or score<=0:break
            budget=min(equity*per_position,cash*.95)
            if budget<10:break
            gross=budget/(1+fee);c=gross*fee;qty=gross/prices[sym];cash-=gross+c;costs+=c;trades+=1;positions[sym]=qty;slots-=1
        equity=cash+sum(q*prices.get(s,0) for s,q in positions.items())
        if stress.get('shock_pct') and len(history)+1==max(1,len(days)//2):equity*=1+float(stress['shock_pct'])/100
        peak=max(peak,equity);marks.append(equity)
        history.append((day,prices))
    rets=[marks[i]/marks[i-1]-1 for i in range(1,len(marks)) if marks[i-1]>0];ret=(marks[-1]/marks[0]-1)*100 if marks and marks[0] else 0;dd=min((m/max(marks[:i+1])-1)*100 for i,m in enumerate(marks)) if marks else 0
    sd=statistics.pstdev(rets) if len(rets)>1 else 0;sharpe=(statistics.mean(rets)/sd*math.sqrt(252)) if sd else 0
    result={'completed':True,'return_pct':ret,'max_drawdown_pct':dd,'sharpe':sharpe,'costs':costs,'trades':trades,'marks':len(marks),'signal_lag_days':SIGNAL_LAG_DAYS,'lookahead':False,'evidence_class':'SIMULATED_HISTORICAL_ONLY','real_trading':False}
    if return_marks:result['equity_marks']=marks
    return result


def walk_forward(config, days=None, folds=4, min_train=60):
    days=list(days or _series_by_day());n=len(days)
    if n<min_train+20:return {'completed':False,'reason':'INSUFFICIENT_HISTORY','folds':[],'real_trading':False}
    test=max(10,(n-min_train)//max(1,int(folds)));out=[]
    start=min_train
    while start<n and len(out)<folds:
        end=min(n,start+test);segment=days[:end];res=evaluate_config(config,segment);res['train_days']=start;res['test_days']=end-start;out.append(res);start=end
    valid=[x for x in out if x.get('completed')]
    returns=[x['return_pct'] for x in valid];dds=[abs(x['max_drawdown_pct']) for x in valid]
    stability=0.0 if not returns else max(0.0,100.0-(statistics.pstdev(returns) if len(returns)>1 else 0.0)-statistics.mean(dds))
    return {'completed':bool(valid),'folds':out,'mean_return_pct':statistics.mean(returns) if returns else None,'worst_drawdown_pct':-max(dds) if dds else None,'stability_score':stability,'lookahead':False,'signal_lag_days':SIGNAL_LAG_DAYS,'evidence_class':'SIMULATED_WALK_FORWARD_ONLY','real_trading':False}


def stress_suite(config,days=None):
    scenarios={'base':{},'costs_2x':{'cost_multiplier':2},'costs_4x':{'cost_multiplier':4},'shock_-15':{'shock_pct':-15},'shock_-30':{'shock_pct':-30}}
    rows={k:evaluate_config(config,days,stress=v) for k,v in scenarios.items()}
    completed=[r for r in rows.values() if r.get('completed')]
    survival=bool(completed) and all(r['max_drawdown_pct']>-50 for r in completed)
    return {'completed':bool(completed),'scenarios':rows,'survival_pass':survival,'signal_lag_days':SIGNAL_LAG_DAYS,'real_trading':False}


def overfit_gate(walk,stress,max_fold_return_sd=25.0):
    folds=[x for x in walk.get('folds',[]) if x.get('completed')];rets=[x['return_pct'] for x in folds]
    sd=statistics.pstdev(rets) if len(rets)>1 else 0.0;blockers=[]
    if len(folds)<2:blockers.append('TOO_FEW_WALK_FORWARD_FOLDS')
    if sd>float(max_fold_return_sd):blockers.append('UNSTABLE_ACROSS_FOLDS')
    if not stress.get('survival_pass'):blockers.append('STRESS_SURVIVAL_FAILED')
    return {'status':'PASS_RESEARCH' if not blockers else 'REJECT','blockers':blockers,'fold_return_sd':sd,'eligible_next_stage':'SHADOW_REVIEW' if not blockers else 'GRAVEYARD','can_promote_to_paper':False,'real_trading':False}
