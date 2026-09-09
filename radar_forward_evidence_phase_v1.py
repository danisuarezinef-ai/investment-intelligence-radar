"""Classify prospective evidence maturity without inventing performance."""
from __future__ import annotations
REAL_TRADING=False

def evidence_phase(*,matured_n=0,prospective_days=0,cost_aware_n=0,benchmark_aware_n=0,backfilled_n=0):
    n=max(0,int(matured_n));days=max(0,int(prospective_days));cost=max(0,int(cost_aware_n));bench=max(0,int(benchmark_aware_n));back=max(0,int(backfilled_n))
    eligible=max(0,min(n,cost,bench)-back)
    if eligible==0:phase='ACCUMULATING'
    elif eligible<30 or days<14:phase='EARLY_EVIDENCE'
    elif eligible<100 or days<60:phase='DEVELOPING_EVIDENCE'
    else:phase='MATURE_PAPER_EVIDENCE'
    return {'phase':phase,'matured_n':n,'eligible_n':eligible,'prospective_days':days,'performance_claim':'INSUFFICIENT_EVIDENCE' if phase!='MATURE_PAPER_EVIDENCE' else 'PAPER_FORWARD_EVIDENCE_ONLY','real_trading':False}
