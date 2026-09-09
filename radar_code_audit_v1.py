"""Static code-audit registry for high-risk production invariants."""
from __future__ import annotations
REAL_TRADING=False
REQUIRED_INVARIANTS=('real_trading_disabled','no_backfill_promotion','missing_is_not_zero','forward_only_learning','paper_only_execution')

def code_audit(invariants=None):
    seen=dict(invariants or {})
    checks={name:seen.get(name) is True for name in REQUIRED_INVARIANTS}
    blockers=[k for k,v in checks.items() if not v]
    return {'status':'PASS' if not blockers else 'BLOCKED','checks':checks,'blockers':blockers,'real_trading':False}
