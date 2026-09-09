import radar_risk_engine_v21 as risk21
import radar_allocation_engine_v2 as alloc2
import radar_global_universe_v2 as universe2
import radar_asset_evidence_engine_v1 as evidence1
import radar_decision_lab_v6 as dl6


def test_every_new_module_keeps_real_trading_disabled():
    assert all(m.REAL_TRADING is False for m in (risk21, alloc2, universe2, evidence1, dl6))
