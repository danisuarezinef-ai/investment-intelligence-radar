"""Scalable global opportunity funnel.
Cheap screening is separated from expensive deep review so coverage can grow
without pretending every security has been deeply analysed.
"""
from __future__ import annotations
from typing import Any, Iterable

REAL_TRADING = False

def build_global_funnel(candidates: Iterable[dict[str, Any]], *, screen_limit: int = 500,
                        deep_limit: int = 40, decision_limit: int = 12) -> dict[str, Any]:
    rows = [dict(x) for x in candidates if x.get('symbol')]
    def cheap_score(x: dict[str, Any]) -> float:
        vals = [x.get('liquidity_score'), x.get('data_quality'), x.get('momentum_score')]
        usable = [float(v) for v in vals if isinstance(v, (int, float))]
        return sum(usable) / len(usable) if usable else -1.0
    screened = sorted(rows, key=cheap_score, reverse=True)[:max(0, screen_limit)]
    deep = [x for x in screened if x.get('deep_evidence_ready') is True][:max(0, deep_limit)]
    decision = [x for x in deep if x.get('decision_evidence_complete') is True][:max(0, decision_limit)]
    return {
        'universe_count': len(rows), 'screened_count': len(screened), 'deep_review_count': len(deep),
        'decision_set_count': len(decision), 'screened': screened, 'deep_review': deep, 'decision_set': decision,
        'coverage_verified': len(rows) > 0, 'global_coverage_claim': 'OBSERVED_INPUT_ONLY',
        'can_trade': False, 'real_trading': False,
    }
