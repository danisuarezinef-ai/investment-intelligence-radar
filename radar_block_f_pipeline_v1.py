"""Block F — five-brain PAPER decision and execution pipeline.

Composes existing agent profiles, Block E market-data gate, regime intelligence,
realistic PAPER execution and Block D accounting into one auditable path.
There is deliberately no broker transport and REAL_TRADING is always false.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

from radar_agents import AGENTS
import radar_block_e_market_data_v2 as market_data
from radar_regime_intelligence_v1 import classify_regime
from radar_paper_execution_v2 import simulate_fill
from radar_paper_accounting_v1 import new_account, apply_fill, accounting_invariants, mark_to_market

REAL_TRADING=False
BRAIN_ORDER=('conservative','balanced','aggressive','high_conviction','experimental')
HORIZON_BY_BRAIN={
    'conservative':'3m','balanced':'1m','aggressive':'1w','high_conviction':'1m','experimental':'1d'
}
RISK_PENALTY={'bajo':0.0,'intermedio':1.4,'alto':3.2}


def _clamp(x,a=0.0,b=1.0): return max(a,min(b,float(x)))
def _trace_id(prefix,payload):
    raw=json.dumps(payload,sort_keys=True,separators=(',',':'),default=str).encode()
    return f"{prefix}-"+hashlib.sha256(raw).hexdigest()[:20]


def brain_decision(agent_id,candidate,*,regime_state=None,observed_price=None):
    """Standard independent decision schema for one existing PAPER brain."""
    if agent_id not in AGENTS: raise KeyError(agent_id)
    cfg=AGENTS[agent_id]; c=dict(candidate or {})
    symbol=str(c.get('symbol') or '').upper(); risk=str(c.get('risk') or 'intermedio')
    score=float(c.get('score') or 0.0); expected=float(c.get('expected_return_pct') or score)
    downside=max(0.0,float(c.get('downside_pct') or 0.0))
    quality=_clamp(c.get('data_quality',.85)); regime_state=regime_state or {'status':'OK','regime':'NEUTRAL','risk_multiplier':.8,'confidence_multiplier':.9}
    regime_mult=float(regime_state.get('confidence_multiplier') or 0.0) if regime_state.get('status')=='OK' else 0.0
    risk_ok=risk in cfg['tiers']; margin=score-float(cfg['min_score'])-RISK_PENALTY.get(risk,1.5)*.15
    confidence=_clamp((.46+.065*margin+.12*quality)*regime_mult)
    if regime_state.get('status')!='OK' or quality<.45:
        action='HOLD'; reason='insufficient regime or market evidence'
    elif margin>=2.0 and risk_ok:
        action='BUY'; reason='score clears brain threshold with acceptable risk tier'
    elif margin<=-2.0 or expected<0:
        action='SELL'; reason='opportunity deteriorated below brain threshold'
    else:
        action='HOLD'; reason='edge insufficient for a new PAPER position'
    conviction=_clamp(confidence*(.45+min(1.0,abs(margin)/5.0)*.55))
    pros=[f"score {score:.2f}",f"expected return {expected:.2f}%",f"data quality {quality:.2f}"]
    risks=[f"risk tier {risk}",f"downside {downside:.2f}%",f"regime {regime_state.get('regime','UNKNOWN')}"]
    invalidation=f"invalidate if score falls below {float(cfg['min_score'])-2.0:.2f} or market-data gate fails"
    payload={'brain_id':agent_id,'brain_name':cfg['name'],'symbol':symbol,'action':action,
             'conviction':conviction,'confidence':confidence,'horizon':HORIZON_BY_BRAIN[agent_id],
             'observed_price':float(observed_price) if observed_price is not None else None,
             'score':score,'expected_return_pct':expected,'downside_pct':downside,'risk':risk,
             'thesis':reason,'pros':pros,'risks':risks,'invalidation':invalidation,
             'abstained':action=='HOLD','real_trading':False}
    payload['decision_id']=_trace_id('brain',payload)
    return payload


def five_brain_decisions(candidate,*,regime_state=None,observed_price=None):
    return [brain_decision(a,candidate,regime_state=regime_state,observed_price=observed_price) for a in BRAIN_ORDER]


def opportunity_radar_369(candidates,*,regime_state=None):
    """Rank opportunities while preserving per-brain votes, HOLDs and disagreement."""
    rows=[]
    for c in candidates or []:
        decisions=five_brain_decisions(c,regime_state=regime_state,observed_price=c.get('observed_price'))
        buys=sum(d['action']=='BUY' for d in decisions); sells=sum(d['action']=='SELL' for d in decisions); holds=5-buys-sells
        mean_conv=sum(d['conviction'] for d in decisions)/5.0
        score=float(c.get('score') or 0.0)
        consensus=(buys-sells)/5.0
        radar_score=score+4.0*consensus+1.5*mean_conv
        rows.append({**dict(c),'brain_decisions':decisions,'buy_votes':buys,'hold_votes':holds,'sell_votes':sells,
                     'abstentions':holds,'disagreement':len({d['action'] for d in decisions})>1,
                     'consensus':consensus,'mean_conviction':mean_conv,'radar_score':radar_score,'real_trading':False})
    rows.sort(key=lambda x:(x['radar_score'],x['mean_conviction']),reverse=True)
    for i,r in enumerate(rows,1): r['rank']=i
    return {'top3':deepcopy(rows[:3]),'top6':deepcopy(rows[:6]),'top9':deepcopy(rows[:9]),'all':rows,
            'preserves_abstentions':True,'preserves_disagreement':True,'real_trading':False}


def ensemble_decision(candidate,*,regime_state=None,observed_price=None):
    regime_state=regime_state or {'status':'INSUFFICIENT_EVIDENCE','regime':'UNKNOWN','risk_multiplier':0,'confidence_multiplier':0}
    ds=five_brain_decisions(candidate,regime_state=regime_state,observed_price=observed_price)
    weights={'conservative':1.15,'balanced':1.15,'aggressive':.95,'high_conviction':1.05,'experimental':.70}
    signed={'BUY':1.0,'HOLD':0.0,'SELL':-1.0}
    denom=sum(weights[d['brain_id']] for d in ds)
    vote=sum(weights[d['brain_id']]*signed[d['action']]*d['conviction'] for d in ds)/denom
    buy_count=sum(d['action']=='BUY' for d in ds); sell_count=sum(d['action']=='SELL' for d in ds)
    confidence=sum(weights[d['brain_id']]*d['confidence'] for d in ds)/denom
    regime_ok=regime_state.get('status')=='OK' and float(regime_state.get('risk_multiplier') or 0)>0
    if not regime_ok or confidence<.45 or abs(vote)<.16:
        action='NO_INVERTIR'; reason='insufficient ensemble confidence, disagreement or regime evidence'
    elif vote>0 and buy_count>=3:
        action='BUY'; reason='weighted multi-brain consensus supports PAPER entry'
    elif vote<0 and sell_count>=3:
        action='SELL'; reason='weighted multi-brain consensus supports PAPER exit'
    else:
        action='NO_INVERTIR'; reason='no qualified majority after weighted disagreement'
    out={'symbol':str(candidate.get('symbol') or '').upper(),'action':action,'confidence':_clamp(confidence),
         'weighted_vote':vote,'buy_votes':buy_count,'sell_votes':sell_count,
         'hold_votes':5-buy_count-sell_count,'disagreement':len({d['action'] for d in ds})>1,
         'regime':regime_state.get('regime','UNKNOWN'),'regime_state':regime_state,
         'brain_decisions':ds,'reason':reason,'broker_connected':False,'can_submit_broker_order':False,
         'live_execution_allowed':False,'real_trading':False}
    out['ensemble_decision_id']=_trace_id('ensemble',out)
    return out


def decision_to_paper_execution(candidate,quote,*,regime_snapshot,account=None,budget_fraction=.10,available_volume=100000.0):
    """One complete market→decision→order→fill→position trace. PAPER only."""
    account=deepcopy(account or new_account(10000.0)); gate=market_data.market_data_gate(quote)
    regime=classify_regime(regime_snapshot)
    ensemble=ensemble_decision(candidate,regime_state=regime,observed_price=quote.price)
    trace={'market_gate':gate,'regime':regime,'ensemble':ensemble,'order':None,'fill':None,'accounting':None,
           'position_after':None,'broker_connected':False,'can_submit_broker_order':False,
           'live_execution_allowed':False,'real_trading':False}
    if not gate.get('paper_execution_eligible'):
        trace['status']='BLOCKED';trace['reason']='market_data_gate_failed';trace['trace_id']=_trace_id('trace',trace);return account,trace
    if ensemble['action']!='BUY':
        trace['status']='NO_INVERTIR';trace['reason']=ensemble['reason'];trace['trace_id']=_trace_id('trace',trace);return account,trace
    risk_mult=float(regime.get('risk_multiplier') or 0.0)
    cash=float(account.get('cash') or 0.0); budget=max(0.0,cash*float(budget_fraction)*risk_mult)
    if budget<1.0:
        trace['status']='BLOCKED';trace['reason']='risk_budget_too_small';trace['trace_id']=_trace_id('trace',trace);return account,trace
    qty=budget/float(quote.price); order={'side':'BUY','quantity':qty,'symbol':quote.symbol}
    order_id=_trace_id('order',{'decision':ensemble['ensemble_decision_id'],**order})
    order['order_id']=order_id; trace['order']=order
    fill=simulate_fill(order,{'mid_price':float(quote.price),'available_volume':float(available_volume)})
    fill_id=_trace_id('fill',{'order_id':order_id,'fill':fill}); fill['fill_id']=fill_id;trace['fill']=fill
    if fill.get('status') not in ('FILLED','PARTIAL'):
        trace['status']='UNFILLED';trace['reason']=fill.get('reason');trace['trace_id']=_trace_id('trace',trace);return account,trace
    new_state,acct=apply_fill(account,fill_id=fill_id,order_id=order_id,symbol=quote.symbol,side='BUY',
                              qty=fill['filled_quantity'],price=fill['fill_price'],fee=fill['fees'])
    trace['accounting']=acct;trace['position_after']=(new_state.get('positions') or {}).get(quote.symbol)
    trace['status']='PAPER_FILLED' if acct.get('status')=='APPLIED' else 'ACCOUNTING_REJECTED'
    trace['trace_links']={'decision_id':ensemble['ensemble_decision_id'],'order_id':order_id,'fill_id':fill_id,
                          'position_symbol':quote.symbol}
    trace['trace_id']=_trace_id('trace',trace)
    return new_state,trace


def _fixtures():
    syms=('MSFT','NVDA','GOOGL','AAPL','AMZN','META','AVGO','JPM','XOM','LLY','SPY','QQQ')
    out=[]
    for i,s in enumerate(syms):
        out.append({'symbol':s,'score':7.5-i*.55,'expected_return_pct':10.0-i*.45,
                    'downside_pct':4.0+i*.35,'risk':('bajo','intermedio','alto')[i%3],
                    'data_quality':.92-i*.015,'observed_price':100+i})
    return out


def block_f_validation():
    regime_snapshot={'volatility_pct':17,'trend_pct':11,'breadth_pct':67,'inflation_trend':'stable'}
    regime=classify_regime(regime_snapshot); candidates=_fixtures(); radar=opportunity_radar_369(candidates,regime_state=regime)
    five=five_brain_decisions(candidates[0],regime_state=regime,observed_price=503.0)
    # Explicit abstention/NO_INVERTIR scenario.
    no_regime={'status':'INSUFFICIENT_EVIDENCE','regime':'UNKNOWN','risk_multiplier':0,'confidence_multiplier':0}
    noinv=ensemble_decision(candidates[0],regime_state=no_regime,observed_price=503.0)
    now=datetime.now(timezone.utc)
    quote=market_data.MarketQuote('MSFT',503.0,market_data.v1._iso(now),'fixture','OK','USD','OPEN',
                                  ingestion_timestamp=market_data.v1._iso(now),source_kind='INTRADAY_QUOTE')
    state,trace=decision_to_paper_execution(candidates[0],quote,regime_snapshot=regime_snapshot,account=new_account(10000.0))
    inv=accounting_invariants(state,{'MSFT':503.0})
    # Replay exact applied fill against the post-fill state must be idempotent.
    replay_ok=False
    if trace.get('fill') and trace.get('order') and trace.get('accounting',{}).get('status')=='APPLIED':
        f=trace['fill'];o=trace['order']; before=deepcopy(state)
        replay,rr=apply_fill(state,fill_id=f['fill_id'],order_id=o['order_id'],symbol='MSFT',side='BUY',
                             qty=f['filled_quantity'],price=f['fill_price'],fee=f['fees'])
        replay_ok=rr.get('status')=='DUPLICATE_IGNORED' and replay==before
    checks={
        'five_distinct_brains':len(five)==5 and {d['brain_id'] for d in five}==set(BRAIN_ORDER),
        'decision_schema_complete':all(all(k in d for k in ('action','conviction','horizon','observed_price','thesis','pros','risks','invalidation','decision_id')) for d in five),
        'radar_3_6_9':len(radar['top3'])==3 and len(radar['top6'])==6 and len(radar['top9'])==9,
        'abstention_preserved':all('abstentions' in r for r in radar['all']),
        'disagreement_preserved':all('disagreement' in r for r in radar['all']),
        'explicit_no_invertir':noinv['action']=='NO_INVERTIR',
        'paper_trade_completed':trace.get('status')=='PAPER_FILLED',
        'trace_complete':all((trace.get('trace_links') or {}).get(k) for k in ('decision_id','order_id','fill_id','position_symbol')),
        'position_created':float((trace.get('position_after') or {}).get('qty') or 0)>0,
        'accounting_pass':inv.get('status')=='PASS',
        'retry_idempotent':replay_ok,
        'real_trading_false':all(x is False for x in (REAL_TRADING,trace['real_trading'],trace['can_submit_broker_order'],trace['live_execution_allowed'])),
    }
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'five_brains':five,'radar_369':radar,
            'no_invertir_probe':noinv,'paper_execution_trace':trace,'accounting':inv,
            'end_to_end_paper_pipeline':'VERIFIED' if all(checks.values()) else 'NOT_VERIFIED',
            'broker_connected':False,'live_execution_allowed':False,'real_money_orders_allowed':False,'real_trading':False}


def live_block_f_probe(symbol='MSFT'):
    result=market_data.fetch_best_quote(symbol)
    qd=result.get('quote')
    if not qd:
        return {'status':'FAILED','reason':'no_live_quote','provider_attempts':result.get('attempts'),
                'end_to_end_paper_pipeline':'NOT_VERIFIED','real_trading':False}
    q=market_data.MarketQuote(**qd)
    candidate={'symbol':symbol,'score':7.5,'expected_return_pct':10.0,'downside_pct':4.0,'risk':'bajo','data_quality':.95}
    regime_snapshot={'volatility_pct':17,'trend_pct':11,'breadth_pct':67,'inflation_trend':'stable'}
    state,trace=decision_to_paper_execution(candidate,q,regime_snapshot=regime_snapshot,account=new_account(10000.0))
    inv=accounting_invariants(state,{symbol:float(q.price)})
    ok=result.get('status')=='QUOTE_SELECTED' and trace.get('status')=='PAPER_FILLED' and inv.get('status')=='PASS'
    return {'status':'PASS' if ok else 'FAILED','market_provider':q.provider,'market_timestamp':q.market_timestamp,
            'trace':trace,'accounting':inv,'end_to_end_paper_pipeline':'VERIFIED' if ok else 'NOT_VERIFIED',
            'broker_connected':False,'live_execution_allowed':False,'real_money_orders_allowed':False,'real_trading':False}
