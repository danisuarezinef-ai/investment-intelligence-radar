import hashlib
import radar_windows_resilience_v1 as r
import radar_update_contract_v1 as u
import radar_release_channels_v1 as c

def test_windows_state_only_persists_ui(tmp_path):
    p=tmp_path/"state.json"
    r.atomic_save_ui_state(p,{"window":"week","metric":"pnl","cash":999,"orders":["x"],"real_trading":True})
    assert r.load_ui_state(p)=={"window":"week","metric":"pnl"}
    assert r.REAL_TRADING is False

def test_windows_never_becomes_second_engine():
    assert r.recovery_plan(True,True,True,True)=={"mode":"CLOUD_OBSERVER","engine_start":False,"paper_mutation":False}
    assert r.recovery_plan(False,False,False,False)["mode"]=="OFFLINE_READ_ONLY"
    assert r.recovery_plan(True,False,True,True)["mode"]=="RECOVERY_BLOCKED"

def test_update_hash_signature_and_safety_are_fail_closed():
    data=b"package"; h=hashlib.sha256(data).hexdigest()
    m={"version":"1.1","channel":"stable","sha256":h,"signature":"sig","package":"radar.exe","real_trading":False}
    assert u.validate_manifest(m,"1.0")["ok"]
    assert not u.verify_package(data,m,False)["ok"]
    assert not u.verify_package(b"tampered",m,True)["ok"]
    assert u.verify_package(data,m,True)["ok"]
    unsafe=dict(m,real_trading=True)
    assert not u.validate_manifest(unsafe,"1.0")["ok"]

def test_failed_post_update_health_requires_rollback():
    assert u.update_plan(True,False,"1.0")=={"action":"ROLLBACK","rollback":True,"target":"1.0"}

def test_stable_requires_full_evidence():
    partial={"tests_green":True,"ci_green":True,"real_trading_false":True}
    g=c.promotion_gate("candidate","stable",partial)
    assert not g["allowed"] and "rollback_tested" in g["missing"]
    full={k:True for k in ("tests_green","ci_green","clean_install","upgrade_previous","launch_ok","restore_ok","smoke_ok","rollback_tested","real_trading_false")}
    assert c.promotion_gate("candidate","stable",full)["allowed"]
