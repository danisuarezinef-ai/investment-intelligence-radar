from radar_observable_paper_v1 import build_live_activity, observable_snapshot, timeline


def test_observability_is_paper_read_only():
    snap = observable_snapshot({"active": True, "paper": {"total": 1012.5}}, {}, "equity", "today")
    assert snap["safety"] == {"mode": "PAPER", "REAL_TRADING": False, "read_only": True}
    assert snap["summary"]["real_trading"] is False
    assert "maturity" not in snap


def test_activity_separates_analysis_opportunity_and_action():
    rows = build_live_activity({"activity": [
        {"symbol": "AAA", "stage": "analysis", "score": 0.61},
        {"symbol": "BBB", "stage": "opportunity", "score": 0.82},
        {"symbol": "CCC", "action": "PAPER BUY", "confidence": 0.91},
    ]})
    assert [x["stage"] for x in rows] == ["ANALYZING", "OPPORTUNITY", "PAPER_ACTION"]
    assert all(x["paper_only"] for x in rows)


def test_equity_and_pnl_timeline_are_observed_only():
    eq = {"daily_equity_30d": [{"date": "2026-09-15", "equity": 1000}, {"date": "2026-09-16", "equity": 1010}]}
    assert [x["value"] for x in timeline(eq, {}, "equity")] == [1000.0, 1010.0]
    assert [x["value"] for x in timeline(eq, {}, "pnl")] == [0.0, 10.0]
