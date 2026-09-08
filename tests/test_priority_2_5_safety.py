import radar_allocation_engine_v1 as alloc
import radar_risk_engine_v2 as risk
import radar_decision_allocation_v1 as integ
import radar_oos_audit_v3 as oos


def test_priority_2_5_modules_never_enable_real_trading():
    assert alloc.REAL_TRADING is False
    assert risk.REAL_TRADING is False
    assert integ.REAL_TRADING is False
    assert oos.REAL_TRADING is False
