"""Point-in-time valuation evidence engine.
No missing fundamental or valuation field is silently imputed as neutral.
"""
from __future__ import annotations
from typing import Any

REAL_TRADING = False
REQUIRED = ('price','revenue_growth','operating_margin','free_cash_flow','net_debt','valuation_multiple','known_at')

def valuation_card(symbol: str, evidence: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in REQUIRED if evidence.get(k) is None]
    complete = not missing
    score = None
    if complete:
        growth=float(evidence['revenue_growth']); margin=float(evidence['operating_margin'])
        fcf=float(evidence['free_cash_flow']); debt=float(evidence['net_debt']); multiple=float(evidence['valuation_multiple'])
        # Transparent heuristic, deliberately not labelled empirically optimal.
        score = growth*0.30 + margin*0.25 + (1.0 if fcf>0 else -1.0)*0.20 - max(debt,0)*0.000001 - multiple*0.01
    return {'symbol': symbol, 'evidence_complete': complete, 'missing_fields': missing,
            'valuation_score': score, 'method': 'TRANSPARENT_HEURISTIC_NOT_EMPIRICALLY_OPTIMAL',
            'point_in_time_required': True, 'can_trade': False, 'real_trading': False}
