"""Fail-closed maturity gate for PAPER/SHADOW evidence."""
from __future__ import annotations
REAL_TRADING=False

def maturity_gate(*,eligible_n=0,prospective_days=0,cost_coverage=0.0,benchmark_coverage=0.0,backfilled_n=0,integrity_ok=False):
    checks={
      'eligible_n':int(eligible_n)>=100,
      'prospective_days':int(prospective_days)>=60,
      'cost_coverage':float(cost_coverage)>=0.95,
      'benchmark_coverage':float(benchmark_coverage)>=0.95,
      'no_backfill':int(backfilled_n)==0,
      'integrity':bool(integrity_ok),
    }
    passed=all(checks.values())
    return {'status':'MATURE_PAPER' if passed else 'IMMATURE','checks':checks,'paper_promotion_allowed':passed,'real_money_allowed':False,'real_trading':False}
