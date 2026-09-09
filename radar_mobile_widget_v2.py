"""Mobile widget v2: balance-first compact PAPER status."""
REAL_TRADING=False

def mobile_widget_v2(panel):
    p=panel or {};alert='OK'
    if p.get('evidence_state')!='MATURE':alert='EVIDENCE_PENDING'
    dd=p.get('drawdown_pct')
    if isinstance(dd,(int,float)) and dd<=-0.07:alert='DRAWDOWN_WARNING'
    return {'primary_value':p.get('balance'),'cash':p.get('cash'),'drawdown_pct':dd,'alert':alert,'forward_matured':p.get('forward_matured',0),'cloud_fresh':p.get('cloud_fresh'),'mode':'PAPER','real_trading':False}
