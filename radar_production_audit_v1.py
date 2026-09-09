"""Full production audit aggregator for Windows/Cloud/PAPER/Forward/Learning.

The audit is fail-closed. Missing evidence remains UNKNOWN/BLOCKED and never implies
operational success. REAL_TRADING is permanently false in this phase.
"""
from __future__ import annotations
from radar_cloud_freshness_v1 import freshness_snapshot
from radar_reconciliation_v1 import reconciliation_status
from radar_legacy_registry_v1 import legacy_cleanup_plan
from radar_readiness_scorecard_v2 import readiness_scorecard

REAL_TRADING=False


def production_audit(*,timestamps=None,windows_ok=False,cloud_ok=False,persistence_ok=False,market_ok=False,forward_integrity_ok=False,mature_forward_n=0,promotion_gate_ready=False):
    freshness=freshness_snapshot(timestamps or {})
    readiness=readiness_scorecard(windows_ok=windows_ok,cloud_ok=cloud_ok,persistence_ok=persistence_ok,market_ok=market_ok,forward_integrity_ok=forward_integrity_ok,mature_forward_n=mature_forward_n,promotion_gate_ready=promotion_gate_ready,real_broker_connected=False)
    checks={
      'windows':'PASS' if windows_ok else 'NOT_VERIFIED',
      'cloud':'PASS' if cloud_ok else 'NOT_VERIFIED',
      'persistence':'PASS' if persistence_ok else 'NOT_VERIFIED',
      'market':'PASS' if market_ok else 'NOT_VERIFIED',
      'forward_integrity':'PASS' if forward_integrity_ok else 'NOT_VERIFIED',
      'cloud_freshness':'PASS' if freshness['status']=='FRESH' else 'BLOCKED',
      'promotion_gate':'PASS' if promotion_gate_ready else 'BLOCKED',
      'mature_forward_evidence':'PASS' if int(mature_forward_n)>0 else 'INSUFFICIENT_EVIDENCE',
    }
    blockers=[k for k,v in checks.items() if v!='PASS']
    return {
      'status':'PASS_PAPER_SHADOW' if not blockers else 'BLOCKED_OR_INCOMPLETE',
      'checks':checks,'blockers':blockers,'freshness':freshness,'readiness':readiness,
      'reconciliation':reconciliation_status(),'legacy_cleanup':legacy_cleanup_plan(ci_green=False),
      'performance_claim':'INSUFFICIENT_EVIDENCE' if int(mature_forward_n)<=0 else 'FORWARD_EVIDENCE_PRESENT_NOT_REAL_MONEY_AUTHORIZATION',
      'can_trade':False,'real_trading':False,
    }
