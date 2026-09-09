"""Evidence-aware degradation detection across market, model and portfolio state."""
REAL_TRADING=False

def degradation_v2(*,market=None,forward=None,model=None,paper=None,provider=None):
    market=market or {};forward=forward or {};model=model or {};paper=paper or {};provider=provider or {}
    alerts=[]
    exp=int(market.get('assets_expected') or 0);obs=int(market.get('assets_observed') or 0)
    if exp and obs/exp<0.9:alerts.append({'type':'MARKET_COVERAGE','severity':'HIGH','value':obs/exp})
    if provider.get('failure_rate') is not None and float(provider['failure_rate'])>0.20:alerts.append({'type':'PROVIDER_FAILURE_RATE','severity':'HIGH','value':float(provider['failure_rate'])})
    matured=int(forward.get('matured') or 0)
    if matured==0:alerts.append({'type':'FORWARD_EVIDENCE','severity':'INFO','value':0})
    if model.get('status')=='DEGRADED':alerts.append({'type':'MODEL_DEGRADATION','severity':'HIGH','value':model.get('score')})
    dd=(paper.get('equity') or {}).get('drawdown_pct') if isinstance(paper.get('equity'),dict) else paper.get('drawdown_pct')
    if dd is not None and float(dd)<=-0.12:alerts.append({'type':'PAPER_DRAWDOWN','severity':'HIGH','value':float(dd)})
    elif dd is not None and float(dd)<=-0.07:alerts.append({'type':'PAPER_DRAWDOWN','severity':'MEDIUM','value':float(dd)})
    hard=any(a['severity']=='HIGH' for a in alerts)
    return {'status':'DEGRADED' if hard else ('WARNING' if any(a['severity']=='MEDIUM' for a in alerts) else 'OK_OR_EVIDENCE_PENDING'),'alerts':alerts,'new_capital_allowed':False if hard else None,'real_trading':False}
