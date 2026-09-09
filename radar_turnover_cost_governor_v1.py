"""PAPER turnover/cost governor. Blocks churn before it erodes expected edge."""
REAL_TRADING=False


def turnover_cost_gate(*, proposed_turnover_pct=0.0, estimated_cost_bps=None, expected_return_bps=None, max_turnover_pct=0.35, max_cost_share=0.35):
    blockers=[]
    turnover=float(proposed_turnover_pct or 0.0)
    if turnover<0 or turnover>1: blockers.append('INVALID_TURNOVER')
    elif turnover>float(max_turnover_pct): blockers.append('TURNOVER_LIMIT')
    if estimated_cost_bps is None: blockers.append('COST_NOT_VERIFIED')
    if expected_return_bps is None: blockers.append('EXPECTED_RETURN_NOT_VERIFIED')
    if estimated_cost_bps is not None and expected_return_bps is not None:
        edge=float(expected_return_bps)
        cost=float(estimated_cost_bps)
        if edge<=0: blockers.append('NO_POSITIVE_EXPECTED_EDGE')
        elif cost/edge>float(max_cost_share): blockers.append('COST_CONSUMES_EDGE')
    return {'status':'PASS' if not blockers else 'BLOCKED','blockers':blockers,'proposed_turnover_pct':turnover,'real_trading':False}
