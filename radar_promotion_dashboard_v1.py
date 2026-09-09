"""Promotion dashboard v1: transparent gate accounting across shadow, paper and tiny-live review."""
from __future__ import annotations
REAL_TRADING=False

def promotion_dashboard(shadow_gate=None,paper_gate=None,performance=None):
    shadow_gate=shadow_gate or {}; paper_gate=paper_gate or {}; performance=performance or {}
    blockers=[]
    if not shadow_gate.get('ready_for_paper_review'): blockers.append('shadow_to_paper_gate')
    if not paper_gate.get('ready_for_tiny_live_review'): blockers.append('paper_to_tiny_live_gate')
    if performance.get('performance_verified') is not True: blockers.append('forward_performance_not_verified')
    if performance.get('benchmark_coverage',0)<0.95: blockers.append('benchmark_coverage')
    if performance.get('cost_coverage',0)<0.95: blockers.append('cost_coverage')
    return {
        'shadow_to_paper_ready':bool(shadow_gate.get('ready_for_paper_review')),
        'paper_to_tiny_live_ready':bool(paper_gate.get('ready_for_tiny_live_review')),
        'blockers':blockers,
        'next_required_gate':blockers[0] if blockers else 'HUMAN_REVIEW_ONLY',
        'live_execution_allowed':False,'auto_promote':False,'can_trade':False,'real_trading':False}
