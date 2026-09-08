"""Portfolio Intelligence v2. Produces target paper allocations only; cannot execute trades."""
import math
REAL_TRADING=False

def clamp(x,a=0,b=1): return max(a,min(b,float(x)))

def target_weights(opportunities, max_position=.15, max_sector=.35, cash_floor=.10):
    """opportunities: [{symbol, score, confidence, sector, correlation_penalty, tail_risk}]"""
    rows=[]
    for x in opportunities:
        utility=max(0,float(x.get('score',0)))*clamp(x.get('confidence',0))
        utility*=1-.50*clamp(x.get('correlation_penalty',0))
        utility*=1-.65*clamp(x.get('tail_risk',0))
        rows.append([x['symbol'],x.get('sector','unknown'),utility])
    total=sum(r[2] for r in rows)
    investable=max(0,1-clamp(cash_floor))
    if total<=0:return {'weights':{},'cash':1.0,'abstain':True,'real_trading':False}
    weights={r[0]:min(max_position,investable*r[2]/total) for r in rows}
    # sector cap: scale crowded sectors, leaving excess as cash rather than forcing it elsewhere
    sectors={}
    for sym,sector,_ in rows:sectors.setdefault(sector,[]).append(sym)
    for syms in sectors.values():
        s=sum(weights.get(x,0) for x in syms)
        if s>max_sector:
            scale=max_sector/s
            for x in syms:weights[x]*=scale
    used=sum(weights.values())
    return {'weights':{k:round(v,6) for k,v in weights.items() if v>0},'cash':round(max(0,1-used),6),'abstain':used<.05,'real_trading':False}

def portfolio_risk(weights, vol, corr):
    syms=list(weights);var=0
    for a in syms:
        for b in syms:
            rho=1 if a==b else float(corr.get((a,b),corr.get((b,a),0)))
            var+=weights[a]*weights[b]*float(vol.get(a,0))*float(vol.get(b,0))*rho
    return math.sqrt(max(0,var))

def rank_vs_alternatives(candidates, alternatives):
    base=max([float(x.get('expected_return',0)) for x in alternatives] or [0])
    out=[]
    for x in candidates:
        y=dict(x);y['best_alternative_return']=base;y['excess_vs_best_alternative']=float(x.get('expected_return',0))-base;out.append(y)
    return sorted(out,key=lambda x:x['excess_vs_best_alternative']*float(x.get('confidence',0)),reverse=True)
