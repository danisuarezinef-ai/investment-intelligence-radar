"""PAPER-only portfolio intelligence tasks 71-80.

71 correlation intelligence; 72 concentration risk; 73 diversification score;
74 dynamic position sizing; 75 risk budget allocator; 76 portfolio expected shortfall;
77 correlation breakdown stress; 78 sector shock stress; 79 liquidity crisis stress;
80 portfolio survival gate.

These diagnostics may reduce or block PAPER risk. They cannot enable live trading,
broker submission, automatic promotion/release, or Setup 1.6.
"""
from __future__ import annotations
from collections import defaultdict
import math, statistics

REAL_TRADING=False
SECTOR_MAP={
 'MSFT':'technology','NVDA':'semiconductors','GOOGL':'technology','AMZN':'consumer','META':'technology',
 'AVGO':'semiconductors','ASML':'semiconductors','SAP':'technology','TSM':'semiconductors','TM':'consumer',
 'SHEL':'energy','RIO':'materials','LLY':'healthcare','V':'financials','BRK-B':'financials','NVS':'healthcare'
}


def _f(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def _pearson(a,b):
    if len(a)!=len(b) or len(a)<3:return None
    ma=statistics.mean(a);mb=statistics.mean(b)
    sa=sum((x-ma)**2 for x in a);sb=sum((y-mb)**2 for y in b)
    if sa<=0 or sb<=0:return None
    return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(sa*sb)

def _series_returns(price_series):
    out={}
    for sym,points in (price_series or {}).items():
        pts=[]
        for p in points or []:
            if isinstance(p,(list,tuple)) and len(p)>=2:
                d=str(p[0])[:10];px=_f(p[1])
                if px and px>0:pts.append((d,px))
        pts=sorted(dict(pts).items())
        out[sym]={pts[i][0]:pts[i][1]/pts[i-1][1]-1 for i in range(1,len(pts)) if pts[i-1][1]>0}
    return out

def correlation_intelligence(price_series, agent_statuses=None):
    rets=_series_returns(price_series);pairs={};syms=sorted(rets)
    for i,a in enumerate(syms):
        for b in syms[i+1:]:
            dates=sorted(set(rets[a])&set(rets[b]));x=[rets[a][d] for d in dates];y=[rets[b][d] for d in dates]
            pairs[f'{a}|{b}']={'n':len(dates),'correlation':_pearson(x,y)}
    valid=[v['correlation'] for v in pairs.values() if v['correlation'] is not None]
    return {'status':'PASS' if len(valid)>=3 else 'PENDING_SAMPLE','assets':syms,'pairs':pairs,
            'mean_abs_correlation':statistics.mean(abs(x) for x in valid) if valid else None,
            'agent_correlation_verified':False,'reason_agent':'requires aligned agent return timestamps',
            'can_increase_risk':False,'real_trading':False}

def concentration_risk(portfolio):
    positions=list((portfolio or {}).get('positions') or []);total=_f((portfolio or {}).get('total')) or 0.0
    values=[];sector=defaultdict(float)
    for p in positions:
        v=_f(p.get('value')) or 0.0;s=str(p.get('symbol') or '');values.append((s,v));sector[SECTOR_MAP.get(s,'unknown')]+=v
    denom=max(total,sum(v for _,v in values),1e-12)
    weights={s:v/denom for s,v in values};sector_w={k:v/denom for k,v in sector.items()}
    max_asset=max(weights.values(),default=0.0);max_sector=max(sector_w.values(),default=0.0);hhi=sum(w*w for w in weights.values())
    flags=[]
    if max_asset>.25:flags.append('asset_concentration')
    if max_sector>.45:flags.append('sector_concentration')
    if hhi>.30:flags.append('high_hhi')
    return {'status':'ATTENTION' if flags else 'PASS','asset_weights':weights,'sector_weights':sector_w,'hhi':hhi,
            'max_asset_weight':max_asset,'max_sector_weight':max_sector,'flags':flags,'real_trading':False}

def diversification_score(portfolio, corr):
    c=concentration_risk(portfolio);n=len(c['asset_weights']);base=min(1.0,n/5.0)
    corr_pen=min(1.0,float(corr.get('mean_abs_correlation') or 0));conc_pen=min(1.0,c['hhi']/0.30 if c['hhi'] else 0)
    score=max(0.0,100*(0.45*base+0.30*(1-corr_pen)+0.25*(1-conc_pen)))
    return {'status':'PASS' if n>=2 and corr.get('status')=='PASS' else 'PENDING_SAMPLE','score_0_100':round(score,2),
            'position_count':n,'uses_correlation':corr.get('status')=='PASS','uses_concentration':True,'real_trading':False}

def dynamic_position_sizing(signals, portfolio, corr):
    conc=concentration_risk(portfolio);out=[]
    for s in signals or []:
        if s.get('matured') is True:continue
        conf=max(0.0,min(1.0,_f(s.get('confidence')) or 0.0));unc=s.get('uncertainty') or {}
        regime=str(unc.get('regime') or 'UNKNOWN');base=min(.20,.04+.16*conf)
        if regime=='UNKNOWN':base*=.5
        if conc['status']=='ATTENTION':base*=.7
        out.append({'symbol':s.get('symbol'),'horizon':s.get('horizon'),'raw_confidence':conf,
                    'suggested_fraction':max(0.0,min(.20,base)),'paper_only':True})
    return {'status':'PASS' if out else 'PENDING_SAMPLE','suggestions':out[:20],
            'max_position_fraction':.20,'can_only_reduce_from_cap':True,'orders_created':False,'real_trading':False}

def risk_budget_allocator(signals, portfolio):
    sizing=dynamic_position_sizing(signals,portfolio,{'status':'PENDING_SAMPLE','mean_abs_correlation':None})
    items=sizing['suggestions'];raw=[max(0.0,x['suggested_fraction']) for x in items];total=sum(raw)
    budget=.70
    alloc=[]
    for x,w in zip(items,raw):
        frac=0.0 if total<=0 else min(.20,budget*w/total)
        alloc.append({'symbol':x['symbol'],'horizon':x['horizon'],'risk_budget_fraction':frac})
    return {'status':'PASS' if alloc else 'PENDING_SAMPLE','portfolio_risk_budget':budget,'allocations':alloc,
            'sum_allocated':sum(x['risk_budget_fraction'] for x in alloc),'orders_created':False,'real_trading':False}

def portfolio_expected_shortfall(rows, portfolio, alpha=.05):
    positions={str(p.get('symbol')):(_f(p.get('value')) or 0.0) for p in (portfolio or {}).get('positions') or []}
    denom=sum(positions.values());
    by_symbol=defaultdict(list)
    for r in rows or []:
        if r.get('matured') is True and r.get('natural') is True:
            v=_f(r.get('net_return'))
            if v is not None:by_symbol[str(r.get('symbol'))].append(v)
    samples=[]
    if denom>0:
        depth=max([len(by_symbol[s]) for s in positions if s in by_symbol] or [0])
        for i in range(depth):
            total=0.0;covered=0.0
            for s,val in positions.items():
                xs=by_symbol.get(s) or []
                if i<len(xs):total+=(val/denom)*xs[i];covered+=val/denom
            if covered>=.8:samples.append(total)
    xs=sorted(samples);k=max(1,math.ceil(len(xs)*alpha)) if xs else 0
    es=statistics.mean(xs[:k]) if xs else None
    return {'status':'PASS' if len(xs)>=30 else 'PENDING_SAMPLE','n':len(xs),'alpha':alpha,'expected_shortfall':es,
            'historical_forward_only':True,'synthetic_paths':False,'real_trading':False}

def correlation_breakdown_stress(portfolio):
    invested=sum(_f(p.get('value')) or 0 for p in (portfolio or {}).get('positions') or []);total=_f((portfolio or {}).get('total')) or invested
    shock=-.12;loss=invested*shock;post=total+loss
    return {'status':'STRESS_COMPLETE' if total>0 else 'PENDING_SAMPLE','scenario':'CORRELATION_TO_ONE','shock':shock,
            'portfolio_loss':loss,'post_stress_total':post,'synthetic_stress_only':True,'maturity_credit':False,'real_trading':False}

def sector_shock_stress(portfolio):
    scenarios={'technology':-.15,'semiconductors':-.20,'healthcare':-.10,'energy':-.18,'financials':-.12,'consumer':-.12,'materials':-.15,'unknown':-.15}
    losses=defaultdict(float);total=_f((portfolio or {}).get('total')) or 0.0
    for p in (portfolio or {}).get('positions') or []:
        sym=str(p.get('symbol') or '');v=_f(p.get('value')) or 0.0;sec=SECTOR_MAP.get(sym,'unknown');losses[sec]+=v*scenarios[sec]
    worst=min(losses.values(),default=0.0)
    return {'status':'STRESS_COMPLETE' if total>0 else 'PENDING_SAMPLE','sector_losses':dict(losses),'worst_sector_loss':worst,
            'synthetic_stress_only':True,'maturity_credit':False,'real_trading':False}

def liquidity_crisis_stress(portfolio, liquidity=None):
    liquidity=liquidity or {};positions=list((portfolio or {}).get('positions') or [])
    if positions and not liquidity:
        return {'status':'PENDING_DATA','reason':'NO_VERIFIED_LIQUIDITY_INPUT','imputed':False,'new_risk_allowed':False,'real_trading':False}
    impact=0.0;covered=0
    for p in positions:
        sym=str(p.get('symbol') or '');v=_f(p.get('value')) or 0.0;liq=liquidity.get(sym) if isinstance(liquidity,dict) else None
        if not isinstance(liq,dict):continue
        spread=_f(liq.get('spread_pct'));volume=_f(liq.get('volume'))
        if spread is None or volume is None or volume<=0:continue
        covered+=1;impact+=v*min(.10,max(.01,3*spread+.02))
    if positions and covered<len(positions):return {'status':'PENDING_DATA','coverage':covered/len(positions),'imputed':False,'new_risk_allowed':False,'real_trading':False}
    return {'status':'STRESS_COMPLETE' if positions else 'PENDING_SAMPLE','coverage':1.0 if positions else 0.0,'estimated_liquidity_loss':-impact,
            'spread_multiplier':3.0,'imputed':False,'maturity_credit':False,'real_trading':False}

def portfolio_survival_gate(portfolio,corr,es,corr_stress,sector_stress,liq_stress):
    total=_f((portfolio or {}).get('total')) or 0.0;blockers=[]
    if corr.get('status')!='PASS':blockers.append('correlation_not_verified')
    if es.get('status')!='PASS':blockers.append('expected_shortfall_not_mature')
    if liq_stress.get('status')!='STRESS_COMPLETE':blockers.append('liquidity_stress_not_verified')
    stress_loss=0.0
    for v in (corr_stress.get('portfolio_loss'),sector_stress.get('worst_sector_loss'),liq_stress.get('estimated_liquidity_loss')):
        if _f(v) is not None:stress_loss=min(stress_loss,float(v))
    if total>0 and abs(stress_loss)/total>.20:blockers.append('stress_loss_gt_20pct')
    survived=not blockers
    return {'status':'PASS' if survived else 'BLOCKED_EVIDENCE','blockers':blockers,'new_paper_risk_allowed':survived,
            'live_execution_allowed':False,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'real_trading':False}

def board(rows,signals,portfolio,price_series,agent_statuses=None,liquidity=None):
    t71=correlation_intelligence(price_series,agent_statuses);t72=concentration_risk(portfolio);t73=diversification_score(portfolio,t71)
    t74=dynamic_position_sizing(signals,portfolio,t71);t75=risk_budget_allocator(signals,portfolio);t76=portfolio_expected_shortfall(rows,portfolio)
    t77=correlation_breakdown_stress(portfolio);t78=sector_shock_stress(portfolio);t79=liquidity_crisis_stress(portfolio,liquidity)
    t80=portfolio_survival_gate(portfolio,t71,t76,t77,t78,t79)
    vals=[t71,t72,t73,t74,t75,t76,t77,t78,t79,t80]
    tasks={str(71+i):{'state':x.get('status'),'evidence':x} for i,x in enumerate(vals)}
    return {'status':'TASKS_71_80_EVALUATED','tasks':tasks,'automatic_promotion':False,'automatic_release':False,
            'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
