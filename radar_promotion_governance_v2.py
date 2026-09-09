"""Promotion governance v2: Shadow -> Paper review only.

Adds explicit human-review boundary, stable forward-evidence requirements and
prevents any Shadow/Paper result from authorizing real trading.
"""
from __future__ import annotations
from radar_shadow_to_paper_gate_v1 import shadow_to_paper_gate

REAL_TRADING=False


def promotion_governance(evidence, *, human_approved=False):
    gate=shadow_to_paper_gate(evidence or {})
    gate_pass=bool(gate.get('ready_for_paper_review'))
    paper_allowed=gate_pass and bool(human_approved)
    return {
        'gate':gate,
        'shadow_gate_passed':gate_pass,
        'human_approved':bool(human_approved),
        'paper_execution_allowed':paper_allowed,
        'paper_execution_mode':'SIMULATED_ONLY' if paper_allowed else 'BLOCKED',
        'live_review_allowed':False,
        'live_execution_allowed':False,
        'auto_promote':False,
        'can_trade':False,
        'real_trading':False,
    }
