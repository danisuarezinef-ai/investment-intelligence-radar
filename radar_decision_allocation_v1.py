"""Decision → Allocation → Risk integration v1.

Read-only capital recommendation pipeline. It combines Decision Lab v5 cards,
portfolio allocation, and Risk Engine v2 gates. It never executes orders.
"""
from __future__ import annotations

from radar_decision_lab_v5 import decision_lab_v5_snapshot
from radar_allocation_engine_v1 import allocate_capital
from radar_risk_engine_v2 import risk_gate_v2, portfolio_risk_summary

REAL_TRADING = False


def integrated_portfolio_plan(*, portfolio, metadata_by_symbol=None,
                              correlations=None, cards=None,
                              allocation_policy=None, risk_limits=None,
                              decision_limit=50):
    """Return comparable decisions plus risk-gated target budgets.

    Metadata is deliberately caller-supplied. Missing sector/geography/FX/
    liquidity/correlation evidence blocks new capital instead of being guessed.
    """
    if cards is None:
        decision = decision_lab_v5_snapshot(decision_limit)
        cards = decision.get('cards') or []
    else:
        decision = {
            'version': 'v5-external-cards',
            'cards': list(cards or []),
            'count': len(list(cards or [])),
            'can_trade': False,
            'real_trading': False,
        }

    allocation = allocate_capital(cards, portfolio, allocation_policy)
    metadata_by_symbol = metadata_by_symbol or {}
    correlations = correlations or {}
    approved = []
    rejected = []

    for proposal in allocation.get('allocations') or []:
        symbol = str(proposal.get('symbol') or '')
        gate = risk_gate_v2(
            portfolio,
            proposal,
            metadata=metadata_by_symbol.get(symbol),
            correlations=correlations,
            limits=risk_limits,
        )
        row = {
            **proposal,
            'risk': gate,
            'approved_budget': gate.get('allowed_budget', 0.0),
            'target_fraction': (gate.get('allowed_budget', 0.0) / float(portfolio.get('total')))
                if portfolio and portfolio.get('total') else 0.0,
            'can_trade': False,
            'real_trading': False,
        }
        (approved if not gate.get('blocked') else rejected).append(row)

    total_approved = sum(float(x.get('approved_budget') or 0.0) for x in approved)
    return {
        'decision_lab': decision,
        'allocation': allocation,
        'risk_summary': portfolio_risk_summary(portfolio, risk_limits),
        'approved': approved,
        'rejected': rejected,
        'approved_total_budget': total_approved,
        'approved_count': len(approved),
        'rejected_count': len(rejected),
        'pipeline': 'DECISION_LAB_V5 -> ALLOCATION_V1 -> RISK_V2',
        'execution_enabled': False,
        'can_trade': False,
        'real_trading': False,
    }
