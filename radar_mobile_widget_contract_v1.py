"""Compact mobile/widget contract focused on PAPER balance and safety state."""
REAL_TRADING=False

def widget_payload(dashboard):
    d=dashboard or {};b=d.get('balance') or {};f=d.get('forward_evidence') or {}
    alert='OK'
    if d.get('evidence_state')!='MATURE':alert='EVIDENCE_PENDING'
    dd=b.get('drawdown_pct')
    if isinstance(dd,(int,float)) and dd<=-0.07:alert='DRAWDOWN_WARNING'
    return {'balance':b.get('equity'),'cash':b.get('cash'),'drawdown_pct':dd,'alert_state':alert,'forward_predictions':f.get('predictions'),'forward_matured':f.get('matured'),'cloud_operational':d.get('cloud_operational'),'real_trading':False,'display_mode':'PAPER'}
