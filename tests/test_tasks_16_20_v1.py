from radar_resilience_v2 import restart_resilience
from radar_windows_app_v2 import windows_app_v2_status
from radar_operational_panel_v2 import operational_panel
from radar_mobile_widget_v2 import mobile_widget_v2
from radar_code_audit_v1 import code_audit,REQUIRED_INVARIANTS


def test_resilience_fails_closed_then_passes():
    assert restart_resilience()['status']=='BLOCKED'
    assert restart_resilience(duplicate_forward=0,duplicate_paper_fills=0,state_recovered=True,persistence_roundtrip=True)['status']=='PASS'


def test_windows_v2_requires_all_components():
    assert windows_app_v2_status(installer_ok=True)['status']=='BLOCKED_WINDOWS'
    assert windows_app_v2_status(installer_ok=True,updater_ok=True,simulator_ok=True,cloud_sync_ok=True,single_shortcut_ok=True)['status']=='READY_WINDOWS'


def test_panel_and_widget_are_paper_only():
    p=operational_panel({'balance':{'equity':1000,'cash':500,'drawdown_pct':-0.08},'forward_evidence':{'matured':0},'evidence_state':'INSUFFICIENT_EVIDENCE','positions':[]})
    assert p['real_trading'] is False and p['banner']=='REAL TRADING OFF'
    w=mobile_widget_v2(p)
    assert w['mode']=='PAPER' and w['real_trading'] is False and w['alert']=='DRAWDOWN_WARNING'


def test_code_audit_requires_all_safety_invariants():
    assert code_audit({})['status']=='BLOCKED'
    good={k:True for k in REQUIRED_INVARIANTS}
    out=code_audit(good)
    assert out['status']=='PASS' and out['real_trading'] is False
