import radar_simulation_desktop_v6 as ui


def sim():
    return {"status":"ACTIVE","paper":{"equity":110,"cash":40,"positions":[]},
      "activity":[
       {"ts":"2026-09-20T10:00:00Z","symbol":"A","stage":"analysis","reason":"scan","agent":"balanced"},
       {"ts":"2026-09-20T10:01:00Z","symbol":"B","stage":"candidate","confidence":.7,"reason":"setup","agent":"balanced"},
       {"ts":"2026-09-20T10:02:00Z","symbol":"C","stage":"discarded","reason":"risk","agent":"conservative"},
       {"ts":"2026-09-20T10:03:00Z","symbol":"D","action":"BUY","confidence":.8,"reason":"paper decision","agent":"balanced"}]}


def test_thinking_pipeline_keeps_opportunity_distinct_from_trade():
    m=ui.thinking_model(sim())
    c={x["stage"]:x["count"] for x in m["pipeline"]}
    assert c=={"ANALYZING":1,"OPPORTUNITY":1,"DISCARDED":1,"PAPER_ACTION":1}
    assert m["opportunity_is_trade"] is False
    assert m["read_only"] is True


def test_reasons_agents_and_real_confidence_are_exposed_without_fabrication():
    m=ui.thinking_model(sim())
    a=m["items"][0]; b=m["items"][1]
    assert a["confidence"] is None
    assert a["reason"]=="scan" and a["agent"]=="balanced"
    assert b["confidence"]==.7


def test_chart_selectors_are_presentation_only_and_no_maturity_credit():
    equity={"series":[{"ts":"2026-09-20T10:00:00Z","equity":100},{"ts":"2026-09-20T11:00:00Z","equity":110}]}
    m=ui.chart_model(sim(),equity,"pnl","week")
    assert m["metric_label"]=="P&L" and m["window_label"]=="Semana"
    assert m["series"][-1]["value"]==10
    assert m["read_only"] is True and m["maturity_credit"] is False
    assert ui.REAL_TRADING is False


def test_only_actual_paper_actions_become_trade_markers():
    m=ui.chart_model(sim(),{},"operations","today")
    assert len(m["trade_markers"])==1
    assert m["trade_markers"][0]["symbol"]=="D"
    assert m["trade_markers"][0]["paper_only"] is True
