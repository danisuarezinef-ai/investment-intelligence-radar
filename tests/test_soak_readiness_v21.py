from radar_soak_readiness_v1 import soak_readiness


def test_soak_gate_fails_closed():
    r=soak_readiness()
    assert r['status']=='NOT_READY' and r['blockers'] and r['real_trading'] is False


def test_soak_gate_ready_only_when_all_verified():
    r=soak_readiness(cloud_fresh=True,market_collection=True,simulator_available=True,research_brain_live=True,paper_persistent=True,forward_outcomes_live=True,learning_live=True,restart_tested=True,resilience_tested=True,windows_simulator_smoke=True)
    assert r['status']=='READY_FOR_UNATTENDED_SOAK'
    assert r['real_trading'] is False
