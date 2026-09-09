"""Read-only integration: Evidence -> Decision v6 -> Risk v2.1 -> Allocation v2."""
from __future__ import annotations

from radar_decision_lab_v6 import decision_lab_v6
from radar_risk_engine_v21 import risk_gate_v21
from radar_allocation_engine_v2 import allocate_capital_v2

REAL_TRADING = False


def integrated_investment_stack_v2(cards, portfolio, metadata_by_symbol=None, correlations=None, regime=None):
    metadata_by_symbol = metadata_by_symbol or {}; correlations = correlations or {}
    risk_results = {}
    for card in cards or []:
        symbol = str((card or {}).get('symbol') or '')
        if not symbol: continue
        proposal = {
            'symbol': symbol,
            'action': (card or {}).get('action'),
            'requested_budget': float((portfolio or {}).get('total') or 0) * 0.10,
            'confidence': (card or {}).get('confidence'),
        }
        risk_results[symbol] = risk_gate_v21(portfolio, proposal,
            metadata=metadata_by_symbol.get(symbol), correlations=correlations, regime=regime)
    allocation = allocate_capital_v2(cards, portfolio, risk_results=risk_results)
    decisions = decision_lab_v6(cards, allocation=allocation, risk_results=risk_results)
    return {'risk':risk_results,'allocation':allocation,'decisions':decisions,
            'can_trade':False,'real_trading':False}
