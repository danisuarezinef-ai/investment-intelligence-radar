"""Predeclared Paper -> Tiny Live review policy. It cannot enable live trading."""
from __future__ import annotations
from typing import Any
REAL_TRADING=False
POLICY={'min_days':120,'min_decisions':75,'max_drawdown':-0.10,'min_benchmark_coverage':.95,'min_cost_coverage':.95,'min_positive_months':4}

def evaluate(metrics:dict[str,Any], *, human_approved:bool=False)->dict[str,Any]:
    checks={
      'duration':(metrics.get('days') or 0)>=POLICY['min_days'],
      'decisions':(metrics.get('decisions') or 0)>=POLICY['min_decisions'],
      'drawdown':isinstance(metrics.get('max_drawdown'),(int,float)) and metrics['max_drawdown']>=POLICY['max_drawdown'],
      'benchmark':(metrics.get('benchmark_coverage') or 0)>=POLICY['min_benchmark_coverage'],
      'costs':(metrics.get('cost_coverage') or 0)>=POLICY['min_cost_coverage'],
      'positive_months':(metrics.get('positive_months') or 0)>=POLICY['min_positive_months'],
      'degradation_clear':metrics.get('degradation_clear') is True,
      'forward_verified':metrics.get('performance_verified') is True,
      'no_backfill':metrics.get('backfill_used') is False,
      'model_competition_ready':metrics.get('model_competition_ready') is True,
    }
    evidence_pass=all(checks.values())
    blockers=[k for k,v in checks.items() if not v]
    return {'policy':POLICY,'checks':checks,'blockers':blockers,'evidence_pass':evidence_pass,'human_approved':bool(human_approved),
            'ready_for_tiny_live_review':evidence_pass and bool(human_approved),'review_only':True,
            'auto_promote':False,'live_execution_allowed':False,'can_trade':False,'real_trading':False}
