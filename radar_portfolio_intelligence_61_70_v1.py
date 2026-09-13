"""Autonomous PAPER intelligence tasks 61-70.

61 agent specialization map; 62 agent failure map; 63 dynamic ensemble;
64 disagreement intelligence; 65 abstention optimizer; 66 counterfactual abstention;
67 cost stress ladder; 68 liquidity stress; 69 tail-event simulator;
70 portfolio intelligence engine.

All outputs are PAPER/shadow diagnostics. No live-trading, promotion, release or Setup 1.6 authority exists here.
"""
from __future__ import annotations
from collections import defaultdict
import math, statistics

REAL_TRADING=False
MIN_N=20


def _f(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def _matured(rows):return [r for r in rows or [] if r.get('matured') is True and r.get('natural') is True]
def _actions(rows):return [r for r in _matured(rows) if str(r.get('decision_state') or '').upper() in {'BUY','SELL'}]
def _regime(r):return str(((r.get('uncertainty') or {}).get('regime') or 'UNKNOWN')).strip() or 'UNKNOWN'

def agent_specialization_map(agent_states):
    out={}
    for a in agent_states or []:
        aid=str(a.get('agent_id') or '')
        if not aid:continue
        positions=a.get('positions') or [];trades=a.get('trades') or []
        out[aid]={'pnl_pct':_f(a.get('pnl_pct')),'sharpe':_f(a.get('sharpe')),'max_drawdown_pct':_f(a.get('max_drawdown_pct')),
                  'marks':int(a.get('marks') or 0),'positions_n':len(positions),'trades_observed':len(trades),
                  'symbols':sorted({str(x.get('symbol')) for x in positions if x.get('symbol')}),
                  'regime_horizon_specialization_verified':False}
    sufficient=[x for x in out.values() if x['marks']>=20]
    return {'status':'PARTIAL_CONTEXT' if out else 'PENDING_SAMPLE','agents':out,'sufficient_agent_histories':len(sufficient),
            'note':'actual PAPER agent performance is mapped; regime/horizon attribution remains unverified until agent decisions carry prospective regime+horizon labels',
            'automatic_reweighting':False,'real_trading':False}

def agent_failure_map(agent_states):
    out={}
    for a in agent_states or []:
        aid=str(a.get('agent_id') or '')
        if not aid:continue
        pos=a.get('positions') or [];losers=[p for p in pos if (_f(p.get('pnl_pct')) or 0)<0]
        dd=_f(a.get('max_drawdown_pct')) or 0.0
        out[aid]={'negative_open_positions':len(losers),'max_drawdown_pct':dd,'current_pnl_pct':_f(a.get('pnl_pct')),
                  'failure_flags':(['DRAWDOWN'] if dd<=-5 else [])+(['OPEN_LOSERS'] if losers else [])}
    return {'status':'PASS' if out else 'PENDING_SAMPLE','agents':out,'causal_failure_claim':False,
            'diagnostic_only':True,'automatic_demotion':False,'real_trading':False}

def dynamic_ensemble(agent_states):
    eligible=[]
    for a in agent_states or []:
        marks=int(a.get('marks') or 0);pnl=_f(a.get('pnl_pct'));dd=abs(_f(a.get('max_drawdown_pct')) or 0.0)
        if marks<20 or pnl is None:continue
        score=max(0.0,1.0+pnl/100.0)/(1.0+dd/10.0)
        eligible.append((str(a.get('agent_id')),score))
    total=sum(s for _,s in eligible)
    weights={k:(s/total if total>0 else 0.0) for k,s in eligible}
    return {'status':'PASS' if len(weights)>=2 else 'PENDING_SAMPLE','weights':weights,'eligible_agents':len(weights),
            'weights_are_shadow_advisory':True,'automatic_execution':False,'real_trading':False}

def disagreement_intelligence(rows):
    by=defaultdict(list)
    for r in rows or []:
        if r.get('matured') is True:continue
        key=(r.get('symbol'),r.get('horizon'));by[key].append(r)
    cells=[]
    for key,xs in by.items():
        acts={str(x.get('decision_state') or '').upper() for x in xs};cs=[_f(x.get('confidence')) for x in xs];cs=[x for x in cs if x is not None]
        cells.append({'symbol':key[0],'horizon':key[1],'signals':len(xs),'actions':sorted(acts),
                      'action_disagreement':len(acts)>1,'confidence_range':(max(cs)-min(cs)) if len(cs)>=2 else 0.0})
    high=[x for x in cells if x['action_disagreement'] or x['confidence_range']>.20]
    return {'status':'PASS' if cells else 'PENDING_SAMPLE','cells':len(cells),'high_disagreement_n':len(high),
            'high_disagreement_examples':high[:20],'disagreement_reduces_risk_only':True,'real_trading':False}

def abstention_optimizer(rows):
    actions=_actions(rows);candidates=[]
    for floor in (.50,.55,.60,.65,.70,.75):
        kept=[];skipped=[]
        for r in actions:
            c=_f(r.get('confidence'));ex=_f(r.get('excess_return'))
            if c is None or ex is None:continue
            (kept if c>=floor else skipped).append(ex)
        candidates.append({'confidence_floor':floor,'kept_n':len(kept),'skipped_n':len(skipped),
                           'kept_mean_excess':statistics.mean(kept) if kept else None,
                           'skipped_mean_excess':statistics.mean(skipped) if skipped else None})
    valid=[x for x in candidates if x['kept_n']>=10 and x['skipped_n']>=10 and x['kept_mean_excess'] is not None]
    best=max(valid,key=lambda x:x['kept_mean_excess'],default=None)
    return {'status':'PASS' if best else 'PENDING_SAMPLE','tested':candidates,'best_shadow_threshold':best,
            'automatic_threshold_change':False,'real_trading':False}

def counterfactual_abstention(rows):
    vals=[]
    for r in _matured(rows):
        if str(r.get('decision_state') or '').upper() not in {'WAIT','HOLD','ABSTAIN'}:continue
        raw=_f((r.get('outcome') or {}).get('return'))
        if raw is not None:vals.append(raw)
    return {'status':'PASS' if len(vals)>=MIN_N else 'PENDING_SAMPLE','n':len(vals),
            'mean_counterfactual_asset_return':statistics.mean(vals) if vals else None,
            'negative_rate':sum(x<0 for x in vals)/len(vals) if vals else None,
            'no_synthetic_prices':True,'real_trading':False}

def cost_stress_ladder(rows):
    gross=[]
    for r in _actions(rows):
        net=_f(r.get('net_return'));cost=_f(r.get('cost'))
        if net is not None and cost is not None:gross.append(net+cost)
    base=statistics.mean([_f(r.get('cost')) or 0 for r in _actions(rows)]) if _actions(rows) else 0.0
    ladder=[]
    for mult in (1.0,1.5,2.0,3.0):
        vals=[g-base*mult for g in gross]
        ladder.append({'cost_multiplier':mult,'n':len(vals),'mean_net_return':statistics.mean(vals) if vals else None,
                       'positive_rate':sum(v>0 for v in vals)/len(vals) if vals else None})
    return {'status':'PASS' if len(gross)>=MIN_N else 'PENDING_SAMPLE','ladder':ladder,'base_observed_mean_cost':base,
            'synthetic_trades_added':False,'real_trading':False}

def liquidity_stress(rows):
    measurable=[]
    for r in rows or []:
        p=r.get('payload') or {};features=p.get('features') or {}
        liq=_f(features.get('volume') or features.get('liquidity') or p.get('volume'))
        alloc=_f((r.get('paper_allocation') or {}).get('notional') if isinstance(r.get('paper_allocation'),dict) else None)
        if liq is not None:measurable.append({'symbol':r.get('symbol'),'liquidity_proxy':liq,'paper_notional':alloc})
    return {'status':'PASS' if len(measurable)>=MIN_N else 'PENDING_DATA','n':len(measurable),'observations':measurable[:30],
            'missing_liquidity_is_not_imputed':True,'automatic_size_increase':False,'real_trading':False}

def tail_event_simulator(rows,champion=None):
    rets=[_f(r.get('net_return')) for r in _actions(rows)];rets=[x for x in rets if x is not None]
    scenarios=[{'name':'gap_down_5pct','shock':-.05},{'name':'flash_crash_10pct','shock':-.10},
               {'name':'volatility_liquidity_shock','shock':-.15},{'name':'correlation_to_one','shock':-.08}]
    total=_f((champion or {}).get('total'))
    for s in scenarios:s['paper_loss_estimate']=total*abs(s['shock']) if total is not None else None
    return {'status':'PASS' if total is not None else 'PENDING_PORTFOLIO','observed_return_n':len(rets),'scenarios':scenarios,
            'stress_is_hypothetical_not_forward_evidence':True,'cannot_mature_forward_gate':True,'real_trading':False}

def portfolio_intelligence(rows,champion=None):
    open_rows=[r for r in rows or [] if r.get('matured') is not True and str(r.get('decision_state') or '').upper()=='BUY']
    latest={}
    for r in open_rows:
        sym=str(r.get('symbol') or '')
        if sym and (sym not in latest or str(r.get('created_at') or '')>str(latest[sym].get('created_at') or '')):latest[sym]=r
    scored=[]
    for sym,r in latest.items():
        c=_f(r.get('confidence')) or 0.0;u=r.get('uncertainty') or {};unknown=str(u.get('regime') or 'UNKNOWN')=='UNKNOWN'
        score=max(0.0,c-(.20 if unknown else 0.0));scored.append((sym,score))
    scored=sorted(scored,key=lambda x:x[1],reverse=True)[:5];den=sum(s for _,s in scored)
    weights={sym:(s/den if den>0 else 0.0) for sym,s in scored}
    return {'status':'PASS' if weights else 'PENDING_SAMPLE','shadow_weights':weights,'max_positions':5,
            'uses_confidence_and_regime_uncertainty':True,'correlation_optimization_verified':False,
            'orders_created':False,'automatic_execution':False,'real_trading':False}

def board(rows,agent_states=None,champion=None):
    funcs=[lambda:agent_specialization_map(agent_states),lambda:agent_failure_map(agent_states),lambda:dynamic_ensemble(agent_states),
           lambda:disagreement_intelligence(rows),lambda:abstention_optimizer(rows),lambda:counterfactual_abstention(rows),
           lambda:cost_stress_ladder(rows),lambda:liquidity_stress(rows),lambda:tail_event_simulator(rows,champion),lambda:portfolio_intelligence(rows,champion)]
    tasks={str(61+i):{'state':(e:=f()).get('status'),'evidence':e} for i,f in enumerate(funcs)}
    return {'status':'TASKS_61_70_EVALUATED','tasks':tasks,'automatic_promotion':False,'automatic_release':False,
            'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
