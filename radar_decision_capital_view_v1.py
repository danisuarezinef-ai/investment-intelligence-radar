"""Decision/capital view model v1 for Radar de Inversión desktop UI."""
from __future__ import annotations
REAL_TRADING=False

def decision_capital_view(portfolio=None,decisions=None,performance=None,promotion=None):
    portfolio=portfolio or {}; decisions=decisions or []; performance=performance or {}; promotion=promotion or {}
    ranked=sorted(decisions,key=lambda x:float(x.get('recommended_budget') or 0),reverse=True)
    top=ranked[0] if ranked else None
    return {
        'capital':{
            'total':portfolio.get('total'),'cash':portfolio.get('cash'),'invested':portfolio.get('invested'),
            'pnl_pct':portfolio.get('pnl_pct')},
        'current_recommendation':top,
        'opportunities':ranked[:10],
        'forward_performance':performance,
        'promotion':promotion,
        'labels':{'performance':'FORWARD' if performance.get('performance_verified') else 'NOT VERIFIED',
                  'execution':'PAPER/SHADOW ONLY'},
        'live_execution_allowed':False,'real_trading':False}
