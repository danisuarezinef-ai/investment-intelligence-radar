"""Governed 24/7 forward evidence orchestration.

This module coordinates existing components without enabling live execution.
Every cycle freezes decisions before outcomes and reports missing evidence rather
than manufacturing it.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Callable

REAL_TRADING = False

@dataclass(frozen=True)
class CycleReceipt:
    cycle_id: str
    created_at: str
    stages: dict[str, str]
    decision_frozen: bool
    outcome_known_at_decision: bool
    can_trade: bool = False
    real_trading: bool = False

def run_forward_cycle(*, observe: Callable[[], Any], discover: Callable[[Any], Any],
                      decide: Callable[[Any], Any], freeze: Callable[[Any], Any],
                      mature: Callable[[], Any] | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    stages: dict[str, str] = {}
    obs = observe(); stages['OBSERVE'] = 'VERIFIED' if obs is not None else 'INSUFFICIENT_DATA'
    opportunities = discover(obs); stages['DISCOVER'] = 'VERIFIED' if opportunities is not None else 'INSUFFICIENT_DATA'
    decision = decide(opportunities); stages['DECIDE'] = 'VERIFIED' if decision is not None else 'INSUFFICIENT_DATA'
    frozen = False
    if decision is not None:
        freeze(decision); frozen = True; stages['FREEZE'] = 'VERIFIED'
    else:
        stages['FREEZE'] = 'BLOCKED'
    if mature is not None:
        matured = mature(); stages['MATURE_OUTCOMES'] = 'VERIFIED' if matured is not None else 'INSUFFICIENT_DATA'
    receipt = CycleReceipt(
        cycle_id=f"cycle-{now.strftime('%Y%m%dT%H%M%S%fZ')}", created_at=now.isoformat(),
        stages=stages, decision_frozen=frozen, outcome_known_at_decision=False)
    return {'receipt': asdict(receipt), 'observation': obs, 'opportunities': opportunities, 'decision': decision,
            'execution': {'allowed': False, 'reason': 'REAL_TRADING_FALSE'}}
