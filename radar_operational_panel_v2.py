"""Operational panel v2 derived from evidence-first dashboard state."""
REAL_TRADING=False

def operational_panel(dashboard):
    d=dashboard or {};b=d.get('balance') or {};f=d.get('forward_evidence') or {};m=d.get('market') or {}
    return {'balance':b.get('equity'),'cash':b.get('cash'),'drawdown_pct':b.get('drawdown_pct'),'positions':d.get('positions') or [],'evidence_state':d.get('evidence_state','INSUFFICIENT_EVIDENCE'),'forward_matured':f.get('matured',0),'market_coverage_complete':m.get('coverage_complete'),'learning_state':d.get('learning_state'),'optimizer_state':d.get('optimizer_state'),'banner':'REAL TRADING OFF','real_trading':False}
