from radar_calibration_health_v1 import calibration_health
from radar_turnover_cost_governor_v1 import turnover_cost_gate
from radar_diversification_guard_v1 import diversification_guard
from radar_evidence_lineage_v1 import validate_lineage
from radar_release_guard_v1 import release_guard


def test_calibration_requires_mature_forward_and_no_backfill():
    out=calibration_health(mature_forward_n=20,calibration_error=0.05,benchmark_coverage=1,cost_coverage=1)
    assert out['status']=='BLOCKED'
    assert 'INSUFFICIENT_MATURE_FORWARD' in out['blockers']
    out=calibration_health(mature_forward_n=60,calibration_error=0.05,benchmark_coverage=1,cost_coverage=1,backfilled_n=1)
    assert 'BACKFILL_PRESENT' in out['blockers']


def test_turnover_cost_governor_blocks_churn_and_expensive_edge():
    assert turnover_cost_gate(proposed_turnover_pct=.5,estimated_cost_bps=5,expected_return_bps=50)['status']=='BLOCKED'
    assert turnover_cost_gate(proposed_turnover_pct=.1,estimated_cost_bps=20,expected_return_bps=40)['status']=='BLOCKED'


def test_diversification_guard_blocks_single_name_and_sector_concentration():
    out=diversification_guard(positions=[{'weight':.25,'sector':'TECH'},{'weight':.25,'sector':'TECH'}])
    assert 'SINGLE_NAME_CONCENTRATION' in out['blockers']
    assert 'SECTOR_CONCENTRATION' in out['blockers']


def test_lineage_rejects_missing_sources_and_future_cutoff():
    rec={'decision_id':'d1','model_version':'m1','created_at':'2026-09-09T10:00:00Z','target_date':'2026-09-10T10:00:00Z','data_cutoff':'2026-09-09T11:00:00Z','sources':[]}
    out=validate_lineage(rec)
    assert out['status']=='BLOCKED'
    assert 'FUTURE_DATA_CUTOFF' in out['blockers']
    assert 'MISSING_SOURCES' in out['blockers']


def test_release_guard_never_treats_missing_verification_as_pass():
    out=release_guard(core_ci=True,windows_build=True,simulation_smoke=True,installer_verified=True,updater_verified=False,forward_integrity=True,real_trading_flag=False)
    assert out['status']=='BLOCKED'
    assert out['real_trading'] is False
    ok=release_guard(core_ci=True,windows_build=True,simulation_smoke=True,installer_verified=True,updater_verified=True,forward_integrity=True,real_trading_flag=False)
    assert ok['status']=='RELEASE_READY'
    assert ok['real_trading'] is False
