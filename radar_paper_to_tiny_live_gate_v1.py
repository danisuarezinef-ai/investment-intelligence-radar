"""Paper -> Tiny Live governance gate v1.

Designs the evidence boundary only. Passing this gate can never activate real
trading automatically.
"""
from __future__ import annotations

REAL_TRADING=False
DEFAULT_POLICY={
 'min_paper_days':90,'min_decisions':60,'min_matured_outcomes':100,
 'max_drawdown_pct':-10.0,'min_benchmark_coverage':0.95,'min_cost_coverage':0.95,
 'min_positive_months':4,'require_model_degradation_clear':True,
 'require_shadow_gate':True,'require_human_approval':True,
}

def _f(x):
    try:return float(x)
    except (TypeError,ValueError):return None

def paper_to_tiny_live_gate(evidence,policy=None,human_approved=False):
    p={**DEFAULT_POLICY,**(policy or {})};e=evidence or {};fails=[]
    def need(name,ok):
        if not ok:fails.append(name)
    need('paper_days',_f(e.get('paper_days')) is not None and _f(e.get('paper_days'))>=p['min_paper_days'])
    need('decision_count',_f(e.get('decisions')) is not None and _f(e.get('decisions'))>=p['min_decisions'])
    need('matured_outcomes',_f(e.get('matured_outcomes')) is not None and _f(e.get('matured_outcomes'))>=p['min_matured_outcomes'])
    dd=_f(e.get('max_drawdown_pct'));need('drawdown',dd is not None and dd>=p['max_drawdown_pct'])
    bc=_f(e.get('benchmark_coverage'));need('benchmark_coverage',bc is not None and bc>=p['min_benchmark_coverage'])
    cc=_f(e.get('cost_coverage'));need('cost_coverage',cc is not None and cc>=p['min_cost_coverage'])
    need('positive_months',_f(e.get('positive_months')) is not None and _f(e.get('positive_months'))>=p['min_positive_months'])
    if p['require_model_degradation_clear']:need('model_degradation_clear',e.get('degradation_clear') is True)
    if p['require_shadow_gate']:need('shadow_gate',e.get('shadow_gate_passed') is True)
    if p['require_human_approval']:need('human_approval',bool(human_approved))
    review_ready=not fails
    return {'ready_for_tiny_live_review':review_ready,'failed':fails,'policy':p,
            'auto_promote':False,'live_execution_allowed':False,'can_trade':False,'real_trading':False,
            'note':'Gate passage permits governance review only; it never enables broker execution.'}
