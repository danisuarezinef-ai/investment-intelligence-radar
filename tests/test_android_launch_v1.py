import radar_android_launch_v1 as a
import radar_android_package_v1 as p
import radar_android_adversarial_v1 as x
import radar_android_release_candidate_v1 as rc

def test_single_install_no_manual_setup():
    c=a.install_contract()
    assert c["single_install"] and not c["manual_setup"] and not c["python_required"] and not c["terminal_required"]
    assert c["real_trading"] is False

def test_android_preferences_cannot_persist_financial_authority():
    q=a.sanitize_preferences({"window":"week","metric":"pnl","cash":99,"orders":[1],"REAL_TRADING":True})
    assert q=={"window":"week","metric":"pnl"}

def test_resume_is_read_only_or_blocked_until_cloud_is_safe():
    assert a.resume_mode(False,False,False,False,False)["mode"]=="OFFLINE_READ_ONLY"
    assert a.resume_mode(True,True,False,True,True)["mode"]=="RECOVERY_BLOCKED"
    assert a.resume_mode(True,True,True,True,True)=={"mode":"CLOUD_OBSERVER","paper_mutation":False}

def test_package_requires_signature_and_paper_state():
    base={"version":"1","version_code":1,"artifact":"apk","package_id":"app.radar","sha256":"abc",
          "signature_verified":True,"min_sdk":26,"target_sdk":35,"real_trading":False}
    assert p.package_gate(base)["allowed"]
    assert not p.package_gate(dict(base,signature_verified=False))["allowed"]
    assert not p.package_gate(dict(base,real_trading=True))["allowed"]

def test_android_adversarial_cases_never_mutate_paper():
    for s in x.SCENARIOS:
        d=x.disposition(s); assert d["paper_mutation"] is False
        assert d["mode"] in ("READ_ONLY","FAIL_CLOSED")

def test_rc_cannot_pass_on_partial_evidence():
    assert rc.rc_gate({"unit_tests":True,"real_trading_false":True})["status"]=="NOT_VERIFIED"
