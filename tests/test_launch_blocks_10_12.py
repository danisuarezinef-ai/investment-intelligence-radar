from pathlib import Path
import radar_adversarial_launch_v1 as a
import radar_launch_security_v1 as s

def test_installer_is_conventional_and_contains_updater():
    t=Path("installer/RadarSetup.iss").read_text(encoding="utf-8")
    assert "RadarDeInversion.exe" in t and "updater" in t
    assert "[Icons]" in t and "UninstallDisplayIcon" in t
    assert "python" not in t.lower() and "powershell" not in t.lower()

def test_adversarial_matrix_never_mutates_paper():
    for scenario in a.SCENARIOS:
        d=a.disposition(scenario)
        assert d["paper_mutation"] is False
        assert d["mode"] in ("READ_ONLY","FAIL_CLOSED")

def test_unknown_scenario_is_blocked():
    assert a.disposition("new_failure")["mode"]=="BLOCKED"

def test_runtime_security_blocks_unsafe_authority():
    good=s.runtime_security({"REAL_TRADING":"false","broker_execution_enabled":False,"auto_promotion":False,"payments_enabled":False})
    assert good["ok"]
    bad=s.runtime_security({"REAL_TRADING":"true","broker_execution_enabled":True})
    assert not bad["ok"] and "REAL_TRADING_NOT_FALSE" in bad["failures"]

def test_secrets_are_redacted():
    x=s.redact({"RADAR_TOKEN":"abc","API_KEY":"def","status":"ok"})
    assert x=={"RADAR_TOKEN":"[REDACTED]","API_KEY":"[REDACTED]","status":"ok"}

def test_release_security_requires_every_proof():
    assert not s.release_security_gate(True,True,False,True,True)["allowed"]
    g=s.release_security_gate(True,True,True,True,True)
    assert g["allowed"] and g["real_trading"] is False
