"""Evidence-gated expected-return and risk intelligence for paper/shadow decisions.

No expected return is manufactured from an uncalibrated score. Forward outcomes are
required for VERIFIED_FORWARD mode; until then a conservative RESEARCH_PROXY may be
reported for diagnostics but is never optimizer-eligible.
"""
from __future__ import annotations
import math, statistics
from radar_core import con

REAL_TRADING=False
MIN_FORWARD_OBS=20
MIN_SYMBOL_OBS=4


def _finite(x):
    return isinstance(x,(int,float)) and math.isfinite(float(x))


def forward_calibration(symbol=None,horizon='1m'):
    c=con()
    sql='''select p.symbol,p.score,p.confidence,o.return_pct,o.excess_return_pct
           from prediction_outcomes o join predictions p on p.id=o.prediction_id
           where p.horizon=?''';args=[horizon]
    if symbol:sql+=' and p.symbol=?';args.append(symbol)
    try:rows=c.execute(sql,tuple(args)).fetchall()
    except Exception:rows=[]
    c.close();clean=[r for r in rows if _finite(r[3])]
    excess=[float(r[4]) for r in clean if _finite(r[4])]
    returns=[float(r[3]) for r in clean]
    return {'symbol':symbol,'horizon':horizon,'n':len(clean),'excess_n':len(excess),
            'mean_return_pct':statistics.mean(returns) if returns else None,
            'median_return_pct':statistics.median(returns) if returns else None,
            'mean_excess_return_pct':statistics.mean(excess) if excess else None,
            'real_trading':False}


def expected_return_signal(candidate,horizon='1m'):
    symbol=candidate.get('symbol');global_ev=forward_calibration(None,horizon);symbol_ev=forward_calibration(symbol,horizon)
    enough=global_ev['n']>=MIN_FORWARD_OBS and global_ev['excess_n']>=MIN_FORWARD_OBS
    if enough:
        base=float(global_ev['mean_excess_return_pct']);source='GLOBAL_FORWARD_EXCESS_RETURN'
        if symbol_ev['n']>=MIN_SYMBOL_OBS and symbol_ev['excess_n']>=MIN_SYMBOL_OBS:
            base=.65*base+.35*float(symbol_ev['mean_excess_return_pct']);source='SHRUNK_SYMBOL_PLUS_GLOBAL_FORWARD_EXCESS_RETURN'
        confidence=min(1.0,global_ev['excess_n']/100.0)
        return {'status':'VERIFIED_FORWARD','expected_return':base/100.0,'confidence':confidence,'source':source,
                'forward_n':global_ev['n'],'forward_excess_n':global_ev['excess_n'],'optimizer_eligible':True,'real_trading':False}
    score=candidate.get('score');proxy=None
    if _finite(score):proxy=max(-.05,min(.05,float(score)/2000.0))
    return {'status':'INSUFFICIENT_FORWARD_EVIDENCE','expected_return':None,'research_proxy':proxy,
            'source':'UNCALIBRATED_SCORE_DIAGNOSTIC_ONLY','forward_n':global_ev['n'],'forward_excess_n':global_ev['excess_n'],
            'required_forward_n':MIN_FORWARD_OBS,'optimizer_eligible':False,'real_trading':False}


def risk_signal(candidate,horizon='1m'):
    base=candidate.get('base') or {};vol=base.get('volatility');risk= candidate.get('risk') or base.get('risk')
    tier={'bajo':.20,'intermedio':.45,'alto':.75}.get(str(risk),None)
    vol_component=None
    if _finite(vol):vol_component=max(0.0,min(1.0,abs(float(vol))/50.0))
    vals=[x for x in (tier,vol_component) if x is not None]
    if not vals:return {'status':'MISSING_RISK_EVIDENCE','risk_score':None,'optimizer_eligible':False,'real_trading':False}
    return {'status':'OBSERVED_MARKET_RISK_PROXY','risk_score':statistics.mean(vals),'components':{'risk_tier':tier,'volatility':vol_component},
            'optimizer_eligible':True,'real_trading':False}
