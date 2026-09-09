"""Fail-closed PAPER risk budget.

Controls gross exposure, single-name concentration, cash reserve and drawdown.
Never authorises real trading.
"""
from __future__ import annotations
REAL_TRADING=False
DEFAULT_LIMITS={'max_gross_pct':0.75,'max_position_pct':0.15,'min_cash_pct':0.20,'max_drawdown_pct':0.10}


def assess_risk(*,equity,cash,positions,drawdown_pct,limits=None):
    lim={**DEFAULT_LIMITS,**(limits or {})}
    eq=float(equity or 0)
    if eq<=0:return {'status':'BLOCKED','reason':'INVALID_EQUITY','real_trading':False}
    pos=list(positions or [])
    notionals=[abs(float(p.get('market_value') or 0)) for p in pos]
    gross=sum(notionals)/eq
    largest=(max(notionals)/eq) if notionals else 0.0
    cash_pct=float(cash or 0)/eq
    dd=abs(float(drawdown_pct or 0))
    checks={
      'gross':gross<=float(lim['max_gross_pct']),
      'single_position':largest<=float(lim['max_position_pct']),
      'cash_reserve':cash_pct>=float(lim['min_cash_pct']),
      'drawdown':dd<=float(lim['max_drawdown_pct']),
    }
    ok=all(checks.values())
    return {'status':'PASS_PAPER' if ok else 'BLOCKED','checks':checks,'gross_pct':gross,'largest_position_pct':largest,'cash_pct':cash_pct,'drawdown_pct':dd,'limits':lim,'real_trading':False}
