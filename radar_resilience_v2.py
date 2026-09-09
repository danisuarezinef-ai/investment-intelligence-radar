"""Restart/idempotence resilience checks for PAPER/SHADOW state."""
from __future__ import annotations
REAL_TRADING=False

def restart_resilience(*,duplicate_forward=0,duplicate_paper_fills=0,state_recovered=False,persistence_roundtrip=False):
    checks={'forward_idempotent':int(duplicate_forward)==0,'paper_fill_idempotent':int(duplicate_paper_fills)==0,'state_recovered':bool(state_recovered),'persistence_roundtrip':bool(persistence_roundtrip)}
    blockers=[k for k,v in checks.items() if not v]
    return {'status':'PASS' if not blockers else 'BLOCKED','checks':checks,'blockers':blockers,'real_trading':False}
