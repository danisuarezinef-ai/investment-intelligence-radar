"""Promotion gate from Shadow to Paper review. Never auto-promotes or trades."""
from __future__ import annotations
REAL_TRADING=False
DEFAULT_POLICY={'min_forward_days':90,'min_decisions':40,'min_marks':100,'max_drawdown_pct':-10.0,'min_benchmark_coverage':0.95,'min_cost_coverage':0.95,'min_positive_months':3,'require_oos_pass':True,'require_degradation_clear':True}

def _f(x):
    try:return float(x)
    except (TypeError,ValueError):return None

def shadow_to_paper_gate(evidence,policy=None):
    p=dict(DEFAULT_POLICY); p.update(policy or {}); e=evidence or {}; failed=[]
    if _f(e.get('forward_days')) is None or _f(e.get('forward_days'))<p['min_forward_days']:failed.append('forward_days')
    if int(e.get('decisions') or 0)<p['min_decisions']:failed.append('decisions')
    if int(e.get('marks') or 0)<p['min_marks']:failed.append('marks')
    dd=_f(e.get('max_drawdown_pct'))
    if dd is None or dd<p['max_drawdown_pct']:failed.append('drawdown')
    if _f(e.get('benchmark_coverage')) is None or _f(e.get('benchmark_coverage'))<p['min_benchmark_coverage']:failed.append('benchmark_coverage')
    if _f(e.get('cost_coverage')) is None or _f(e.get('cost_coverage'))<p['min_cost_coverage']:failed.append('cost_coverage')
    if int(e.get('positive_months') or 0)<p['min_positive_months']:failed.append('positive_months')
    if p['require_oos_pass'] and e.get('oos_pass') is not True:failed.append('oos_integrity')
    if p['require_degradation_clear'] and e.get('degradation_clear') is not True:failed.append('degradation')
    ready=not failed
    return {'ready_for_paper_review':ready,'failed':failed,'policy':p,'auto_promote':False,'paper_trading_enabled':False,'real_trading':False,
            'note':'Passing this gate permits human review for paper trading only; it does not enable execution.'}
