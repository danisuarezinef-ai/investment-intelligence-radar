"""PAPER-only explainability, counterfactual and policy intelligence tasks 81-90.

81 decision causal graph; 82 signal contribution; 83 failure root-cause; 84 learning from abstention;
85 near-miss learning; 86 opportunity cost; 87 regret minimization score; 88 counterfactual portfolio replay;
89 policy comparison; 90 adaptive policy challenger.

All outputs are diagnostic/advisory. Counterfactuals never earn forward maturity and no task can trade,
promote, release, mutate Champion automatically, or enable Setup 1.6.
"""
from __future__ import annotations
from collections import defaultdict,Counter
import math,statistics

REAL_TRADING=False
MIN_N=20


def _f(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def _regime(r):return str(((r.get('uncertainty') or {}).get('regime') or 'UNKNOWN')).strip() or 'UNKNOWN'
def _matured(rows):return [r for r in rows or [] if r.get('matured') is True and r.get('natural') is True]
def _actions(rows):return [r for r in _matured(rows) if str(r.get('decision_state') or '').upper() in {'BUY','SELL'}]
def _correct(r):
    x=_f(r.get('net_return'));a=str(r.get('decision_state') or '').upper()
    if x is None:return None
    if a=='BUY':return x>0
    if a=='SELL':return x<0
    if a in {'WAIT','HOLD','ABSTAIN'}:return x==0
    return None


def decision_causal_graph(rows):
    """Build an evidence graph of recorded decision inputs; edges are explanatory, not causal proof."""
    latest=list(rows or [])[-100:];graphs=[]
    for r in latest:
        unc=r.get('uncertainty') or {};prov=r.get('provenance') or {};q=r.get('quality_checks') or {}
        nodes=[
            {'id':'signal','kind':'decision','value':str(r.get('decision_state') or 'UNKNOWN')},
            {'id':'confidence','kind':'input','value':_f(r.get('confidence'))},
            {'id':'regime','kind':'input','value':_regime(r)},
            {'id':'pit','kind':'provenance','value':bool(q.get('pit_valid'))},
            {'id':'model','kind':'identity','value':r.get('model_version')},
        ]
        if isinstance(unc,dict):
            for k,v in sorted(unc.items()):
                if k!='regime' and isinstance(v,(int,float,str,bool)):nodes.append({'id':'uncertainty.'+str(k),'kind':'uncertainty','value':v})
        graphs.append({'prediction_id':r.get('prediction_id'),'symbol':r.get('symbol'),'horizon':r.get('horizon'),'nodes':nodes,
                       'edges':[{'from':n['id'],'to':'signal','relation':'RECORDED_DECISION_CONTEXT'} for n in nodes if n['id']!='signal'],
                       'causal_proof':False})
    return {'status':'PASS' if graphs else 'PENDING_SAMPLE','graphs':graphs[:30],'graph_count':len(graphs),
            'edge_semantics':'EXPLANATORY_NOT_CAUSAL','real_trading':False}


def signal_contribution_analysis(rows):
    """Quantify contribution only for fields explicitly recorded in evidence; otherwise remain partial."""
    vals=[]
    for r in _matured(rows):
        conf=_f(r.get('confidence'));ret=_f(r.get('net_return'));reg=_regime(r)
        if conf is None or ret is None:continue
        vals.append((conf,ret,reg,str(r.get('decision_state') or '').upper()))
    if not vals:return {'status':'PENDING_SAMPLE','n':0,'real_trading':False}
    hi=[ret for conf,ret,_,_ in vals if conf>=.65];lo=[ret for conf,ret,_,_ in vals if conf<.65]
    regimes=defaultdict(list)
    for _,ret,reg,_ in vals:regimes[reg].append(ret)
    return {'status':'PARTIAL' if len(vals)>=MIN_N else 'PENDING_SAMPLE','n':len(vals),
            'confidence_split':{'high_n':len(hi),'high_mean':statistics.mean(hi) if hi else None,'low_n':len(lo),'low_mean':statistics.mean(lo) if lo else None},
            'regime_means':{k:{'n':len(v),'mean_net_return':statistics.mean(v)} for k,v in regimes.items()},
            'feature_level_attribution_verified':False,'reason':'normalized forward evidence lacks full prospective feature vector',
            'causal_claim':False,'real_trading':False}


def failure_root_cause(rows):
    c=Counter();examples=[]
    for r in _actions(rows):
        ret=_f(r.get('net_return'));gross=_f(r.get('gross_return'));cost=_f(r.get('cost'));bench=_f(r.get('benchmark_return'));ex=_f(r.get('excess_return'))
        if ret is None or ret>=0:continue
        q=r.get('quality_checks') or {};reg=_regime(r)
        if q.get('pit_valid') is not True:reason='DATA_PROVENANCE'
        elif gross is not None and gross>0 and ret<=0 and cost is not None:reason='COST_DRAG'
        elif reg=='UNKNOWN':reason='REGIME_UNCERTAINTY'
        elif bench is not None and ex is not None and ex<0 and ret>=bench:reason='BENCHMARK_SELECTION'
        else:reason='DIRECTION_TIMING_OR_SIZING'
        c[reason]+=1
        if len(examples)<25:examples.append({'prediction_id':r.get('prediction_id'),'symbol':r.get('symbol'),'reason':reason,'net_return':ret})
    n=sum(c.values())
    return {'status':'PASS' if n>=MIN_N else 'PENDING_SAMPLE','failures_n':n,'categories':dict(c),'examples':examples,
            'root_cause_is_diagnostic_not_causal':True,'real_trading':False}


def learning_from_abstention(rows):
    skipped=[]
    for r in _matured(rows):
        if str(r.get('decision_state') or '').upper() not in {'WAIT','HOLD','ABSTAIN'}:continue
        ret=_f(r.get('net_return'));ex=_f(r.get('excess_return'))
        if ret is not None:skipped.append({'ret':ret,'ex':ex,'confidence':_f(r.get('confidence'))})
    if not skipped:return {'status':'PENDING_SAMPLE','n':0,'real_trading':False}
    opportunity=sum(1 for x in skipped if x['ret']>0);avoided=sum(1 for x in skipped if x['ret']<0)
    return {'status':'PASS' if len(skipped)>=MIN_N else 'PENDING_SAMPLE','n':len(skipped),
            'missed_positive_rate':opportunity/len(skipped),'avoided_negative_rate':avoided/len(skipped),
            'mean_skipped_return':statistics.mean(x['ret'] for x in skipped),'threshold_auto_change':False,
            'prospective_only':True,'real_trading':False}


def near_miss_learning(rows, low=.45, high=.60):
    xs=[]
    for r in _matured(rows):
        c=_f(r.get('confidence'));ret=_f(r.get('net_return'));a=str(r.get('decision_state') or '').upper()
        if c is None or ret is None:continue
        if low<=c<high:xs.append((c,ret,a))
    return {'status':'PASS' if len(xs)>=MIN_N else 'PENDING_SAMPLE','n':len(xs),'confidence_band':[low,high],
            'mean_return':statistics.mean(x[1] for x in xs) if xs else None,
            'positive_rate':sum(x[1]>0 for x in xs)/len(xs) if xs else None,
            'band_tuned_automatically':False,'real_trading':False}


def opportunity_cost_engine(rows):
    acted=[];skipped=[]
    for r in _matured(rows):
        ret=_f(r.get('net_return'));a=str(r.get('decision_state') or '').upper()
        if ret is None:continue
        if a in {'BUY','SELL'}:acted.append(ret if a=='BUY' else -ret)
        elif a in {'WAIT','HOLD','ABSTAIN'}:skipped.append(ret)
    missed=sum(max(0,x) for x in skipped);avoided=sum(max(0,-x) for x in skipped)
    return {'status':'PASS' if len(acted)+len(skipped)>=MIN_N else 'PENDING_SAMPLE','acted_n':len(acted),'skipped_n':len(skipped),
            'missed_upside_sum':missed,'avoided_downside_sum':avoided,
            'net_abstention_opportunity_cost':missed-avoided,'counterfactual_not_maturity_evidence':True,'real_trading':False}


def regret_minimization_score(rows):
    observations=[]
    for r in _matured(rows):
        ret=_f(r.get('net_return'));a=str(r.get('decision_state') or '').upper()
        if ret is None:continue
        realized=ret if a=='BUY' else (-ret if a=='SELL' else 0.0)
        hindsight=max(ret,-ret,0.0)
        regret=max(0.0,hindsight-realized);observations.append(regret)
    if not observations:return {'status':'PENDING_SAMPLE','n':0,'score_0_100':None,'real_trading':False}
    mean_regret=statistics.mean(observations);score=100/(1+100*mean_regret)
    return {'status':'PASS' if len(observations)>=MIN_N else 'PENDING_SAMPLE','n':len(observations),'mean_regret':mean_regret,
            'score_0_100':round(score,2),'uses_outcomes_only_after_evaluation':True,'no_operational_lookahead':True,
            'cannot_train_on_same_outcome_before_decision':True,'real_trading':False}


def counterfactual_portfolio_replay(rows, policies=None):
    policies=policies or {'conservative':.70,'balanced':.55,'selective':.65}
    matured=_matured(rows);out={}
    for name,threshold in policies.items():
        returns=[]
        for r in matured:
            conf=_f(r.get('confidence'));ret=_f(r.get('net_return'));a=str(r.get('decision_state') or '').upper()
            if conf is None or ret is None or conf<threshold or a not in {'BUY','SELL'}:continue
            returns.append(ret if a=='BUY' else -ret)
        equity=1.0;curve=[]
        for x in returns:equity*=1+x;curve.append(equity)
        peak=1.0;maxdd=0.0
        for e in curve:peak=max(peak,e);maxdd=min(maxdd,e/peak-1)
        out[name]={'threshold':threshold,'n':len(returns),'ending_equity_multiple':equity,'mean_return':statistics.mean(returns) if returns else None,'max_drawdown':maxdd}
    return {'status':'PASS' if any(v['n']>=MIN_N for v in out.values()) else 'PENDING_SAMPLE','policies':out,
            'replay_is_counterfactual':True,'maturity_credit':False,'state_mutation':False,'real_trading':False}


def policy_comparison(rows):
    replay=counterfactual_portfolio_replay(rows);eligible=[]
    for name,v in replay['policies'].items():
        if v['n']>=MIN_N and v['mean_return'] is not None:
            utility=v['mean_return']+0.25*v['max_drawdown']
            eligible.append((utility,name,v))
    eligible.sort(reverse=True)
    return {'status':'PASS' if len(eligible)>=2 else 'PENDING_SAMPLE',
            'ranking':[{'policy':name,'utility':u,'n':v['n'],'mean_return':v['mean_return'],'max_drawdown':v['max_drawdown']} for u,name,v in eligible],
            'selection_metric':'mean_return_plus_0.25_max_drawdown','counterfactual_only':True,
            'automatic_policy_switch':False,'maturity_credit':False,'real_trading':False}


def adaptive_policy_challenger(rows):
    comp=policy_comparison(rows);ranking=comp.get('ranking') or []
    challenger=ranking[0] if ranking else None
    return {'status':'SHADOW_CHALLENGER_READY' if challenger and comp['status']=='PASS' else 'PENDING_SAMPLE',
            'challenger':challenger,'scope':'SHADOW_PAPER_ONLY','champion_mutated':False,
            'automatic_replacement':False,'automatic_promotion':False,'requires_new_prospective_forward_test':True,
            'counterfactual_results_cannot_promote':True,'live_execution_allowed':False,'real_trading':False}


def board(rows):
    vals=[decision_causal_graph(rows),signal_contribution_analysis(rows),failure_root_cause(rows),learning_from_abstention(rows),
          near_miss_learning(rows),opportunity_cost_engine(rows),regret_minimization_score(rows),counterfactual_portfolio_replay(rows),
          policy_comparison(rows),adaptive_policy_challenger(rows)]
    tasks={str(81+i):{'state':x.get('status'),'evidence':x} for i,x in enumerate(vals)}
    return {'status':'TASKS_81_90_EVALUATED','tasks':tasks,'automatic_promotion':False,'automatic_release':False,
            'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
