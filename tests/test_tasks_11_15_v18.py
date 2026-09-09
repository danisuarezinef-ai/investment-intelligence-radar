from datetime import datetime,timezone,timedelta
from radar_cloud_freshness_v1 import freshness_snapshot
from radar_reconciliation_v1 import reconciliation_status
from radar_legacy_registry_v1 import legacy_cleanup_plan
from radar_readiness_scorecard_v2 import readiness_scorecard
from radar_production_audit_v1 import production_audit


def test_cloud_freshness_blocks_missing_core_surfaces():
    x=freshness_snapshot({},now=datetime(2026,9,9,tzinfo=timezone.utc))
    assert x['status']=='DEGRADED' and x['real_trading'] is False


def test_cloud_freshness_accepts_recent_core_surfaces():
    now=datetime(2026,9,9,tzinfo=timezone.utc);ts=(now-timedelta(seconds=10)).isoformat()
    x=freshness_snapshot({'pc_sync':ts,'node_heartbeat':ts,'market':ts,'forward_ledger':ts,'provider_telemetry':ts},now=now)
    assert x['status']=='FRESH'


def test_pr_reconciliation_has_7_10_20_and_no_mechanical_merge():
    x=reconciliation_status();assert set(x['prs'])=={7,10,20};assert x['mechanical_merge_required'] is False


def test_legacy_cleanup_never_deletes_automatically():
    x=legacy_cleanup_plan(ci_green=True);assert x['automatic_delete'] is False


def test_readiness_separates_paper_from_real_money():
    x=readiness_scorecard(windows_ok=True,cloud_ok=True,persistence_ok=True,market_ok=True,forward_integrity_ok=True,promotion_gate_ready=True,mature_forward_n=200)
    assert x['paper_shadow']['status']=='READY_PAPER'
    assert x['real_money']['status']=='BLOCKED_REAL'
    assert x['real_trading'] is False


def test_production_audit_fail_closed_without_evidence():
    x=production_audit()
    assert x['status']=='BLOCKED_OR_INCOMPLETE'
    assert x['performance_claim']=='INSUFFICIENT_EVIDENCE'
    assert x['can_trade'] is False and x['real_trading'] is False
