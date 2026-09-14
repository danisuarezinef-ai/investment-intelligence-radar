from radar_first_paper_trial_v1 import *


def test_safety_and_universe():
    assert REAL_TRADING is False
    assert 20 <= len(FROZEN_UNIVERSE) <= 50
    assert len(set(FROZEN_UNIVERSE)) == len(FROZEN_UNIVERSE)


def test_market_gate_fail_closed_and_ready():
    now="2026-09-14T13:00:00+00:00"
    quotes=[{"symbol":s,"price":100+i,"observed_at":now,"provider":"observed-test-provider"} for i,s in enumerate(FROZEN_UNIVERSE)]
    assert market_data_gate(quotes,now_iso=now)["status"] == "READY"
    assert market_data_gate(quotes[:-1],now_iso=now)["status"] == "NOT_READY"
    stale=[dict(q,observed_at="2026-09-14T10:00:00+00:00") for q in quotes]
    assert market_data_gate(stale,now_iso=now)["status"] == "NOT_READY"


def _decision(agent="balanced",symbol="MSFT",action="BUY",conviction=.8):
    return {"decision_id":f"d-{agent}-{symbol}","agent":agent,"symbol":symbol,"action":action,
            "conviction":conviction,"horizon":"1d","observed_price":100,"thesis":"test thesis",
            "factors":["momentum"],"risks":["drawdown"],"invalidation":"price break","expected_return":.02,
            "risk_adjusted_score":conviction}


def test_agents_369_ensemble_and_abstain():
    ds=[_decision(a,"MSFT","BUY",.8) for a in AGENTS]
    assert all(validate_agent_decision(d)["status"]=="PASS" for d in ds)
    assert opportunity_369(ds)["top3_high_confidence"]
    assert ensemble(ds)["decisions"][0]["action"] == "BUY"
    mixed=[_decision("conservative","MSFT","BUY"),_decision("balanced","MSFT","SELL"),_decision("aggressive","MSFT","HOLD"),_decision("high_conviction","MSFT","ABSTAIN"),_decision("experimental","MSFT","BUY")]
    assert ensemble(mixed)["decisions"][0]["action"] == "ABSTAIN"


def test_e2e_lineage_and_trial_report():
    d=_decision(); o={"order_id":"o1","decision_id":d["decision_id"]}; f={"fill_id":"f1","order_id":"o1"}; p={"origin_decision_id":d["decision_id"]}
    assert end_to_end_link(d,o,f,p)["status"] == "VERIFIED"
    m=trial_manifest(git_sha="abc",initial_capital=100000,risk_rules={"max_position_pct":10})
    checks={k:True for k in ("market_data","paper_accounting","persistence","decision_execution_linkage","restart_recovery")}
    r=trial_report(m,technical_checks=checks,metrics={"return":0.01},decisions=[d],lessons=[])
    assert r["verdict"] == "PASS"
    assert r["automatic_real_money_transition"] is False
