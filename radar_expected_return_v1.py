"""Evidence-gated expected-return and risk intelligence for paper/shadow decisions.

No expected return is manufactured from an uncalibrated score. The authoritative
source is the immutable forward ledger outcome JSON produced by radar_forward_engine.
Legacy prediction_outcomes rows are accepted only as a compatibility fallback.
"""
from __future__ import annotations
import json, math, statistics
from radar_core import con

REAL_TRADING=False
MIN_FORWARD_OBS=20
MIN_SYMBOL_OBS=4


def _finite(x):
    return isinstance(x,(int,float)) and math.isfinite(float(x))


def _as_json(x):
    if isinstance(x,dict): return x
    if isinstance(x,str):
        try:
            y=json.loads(x); return y if isinstance(y,dict) else {}
        except Exception:return {}
    return {}


def _ledger_calibration(c,symbol,horizon):
    sql='select asset,outcome from prediction_ledger where outcome is not null and horizon=?';args=[horizon]
    if symbol:sql+=' and asset=?';args.append(symbol)
    rows=c.execute(sql,tuple(args)).fetchall();returns=[];excess=[]
    for asset,outcome in rows:
        o=_as_json(outcome)
        # Forward engine stores decimals: 0.02 == 2%.
        r=o.get('net_return',o.get('return'))
        e=o.get('excess_return')
        if _finite(r):returns.append(float(r)*100.0)
        if _finite(e) and o.get('backfilled') is not True:excess.append(float(e)*100.0)
    return returns,excess


def _legacy_calibration(c,symbol,horizon):
    sql='''select o.return_pct,o.excess_return_pct
           from prediction_outcomes o join predictions p on p.id=o.prediction_id
           where p.horizon=?''';args=[horizon]
    if symbol:sql+=' and p.symbol=?';args.append(symbol)
    rows=c.execute(sql,tuple(args)).fetchall();returns=[];excess=[]
    for r,e in rows:
        if _finite(r):returns.append(float(r))
        if _finite(e):excess.append(float(e))
    return returns,excess


def forward_calibration(symbol=None,horizon='1m'):
    c=con();returns=[];excess=[];source='FORWARD_LEDGER'
    try:
        returns,excess=_ledger_calibration(c,symbol,horizon)
    except Exception:
        returns=[];excess=[]
    if not returns:
        try:
            returns,excess=_legacy_calibration(c,symbol,horizon);source='LEGACY_PREDICTION_OUTCOMES'
        except Exception:
            returns=[];excess=[];source='NO_FORWARD_OUTCOME_SOURCE'
    c.close()
    return {'symbol':symbol,'horizon':horizon,'n':len(returns),'excess_n':len(excess),
            'mean_return_pct':statistics.mean(returns) if returns else None,
            'median_return_pct':statistics.median(returns) if returns else None,
            'mean_excess_return_pct':statistics.mean(excess) if excess else None,
            'evidence_source':source,'real_trading':False}


def expected_return_signal(candidate,horizon='1m'):
    symbol=candidate.get('symbol');global_ev=forward_calibration(None,horizon);symbol_ev=forward_calibration(symbol,horizon)
    enough=global_ev['n']>=MIN_FORWARD_OBS and global_ev['excess_n']>=MIN_FORWARD_OBS
    if enough:
        base=float(global_ev['mean_excess_return_pct']);source='GLOBAL_FORWARD_EXCESS_RETURN'
        if symbol_ev['n']>=MIN_SYMBOL_OBS and symbol_ev['excess_n']>=MIN_SYMBOL_OBS:
            base=.65*base+.35*float(symbol_ev['mean_excess_return_pct']);source='SHRUNK_SYMBOL_PLUS_GLOBAL_FORWARD_EXCESS_RETURN'
        confidence=min(1.0,global_ev['excess_n']/100.0)
        return {'status':'VERIFIED_FORWARD','expected_return':base/100.0,'confidence':confidence,'source':source,
                'evidence_source':global_ev.get('evidence_source'),'forward_n':global_ev['n'],'forward_excess_n':global_ev['excess_n'],
                'optimizer_eligible':True,'real_trading':False}
    score=candidate.get('score');proxy=None
    if _finite(score):proxy=max(-.05,min(.05,float(score)/2000.0))
    return {'status':'INSUFFICIENT_FORWARD_EVIDENCE','expected_return':None,'research_proxy':proxy,
            'source':'UNCALIBRATED_SCORE_DIAGNOSTIC_ONLY','evidence_source':global_ev.get('evidence_source'),
            'forward_n':global_ev['n'],'forward_excess_n':global_ev['excess_n'],'required_forward_n':MIN_FORWARD_OBS,
            'optimizer_eligible':False,'real_trading':False}


def risk_signal(candidate,horizon='1m'):
    base=candidate.get('base') or {};vol=base.get('volatility');risk=candidate.get('risk') or base.get('risk')
    tier={'bajo':.20,'intermedio':.45,'alto':.75}.get(str(risk),None)
    vol_component=None
    if _finite(vol):vol_component=max(0.0,min(1.0,abs(float(vol))/50.0))
    vals=[x for x in (tier,vol_component) if x is not None]
    if not vals:return {'status':'MISSING_RISK_EVIDENCE','risk_score':None,'optimizer_eligible':False,'real_trading':False}
    return {'status':'OBSERVED_MARKET_RISK_PROXY','risk_score':statistics.mean(vals),'components':{'risk_tier':tier,'volatility':vol_component},
            'optimizer_eligible':True,'real_trading':False}
