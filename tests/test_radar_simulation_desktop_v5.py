import radar_simulation_desktop_v5 as ui


def sample():
    return {
        "status": "ACTIVE", "active": True, "completed_cycles": 42,
        "paper": {"equity": 10325.5, "cash": 4120, "pnl_today": 25.5, "pnl_total": 325.5,
                  "positions": [{"symbol": "MSFT"}, {"symbol": "NVDA"}]},
        "activity": [{"symbol": "MSFT", "stage": "candidate", "confidence": .71,
                      "reason": "observed setup", "agent": "balanced"}],
    }


def test_launch_home_is_paper_read_only():
    m=ui.launch_home_model(sample(), {})
    assert m["mode_banner"] == "PAPER · REAL_TRADING OFF 🔒"
    assert m["safety"] == {"mode":"PAPER","real_trading":False,"read_only":True}
    assert m["read_only"] is True
    assert ui.REAL_TRADING is False


def test_launch_home_exposes_core_operator_state():
    m=ui.launch_home_model(sample(), {})
    assert m["cards"]["open_positions"] == 2
    assert m["engine"]["runtime"] == "ACTIVE"
    assert m["engine"]["last_cycle"] == "42"
    assert m["engine"]["autonomy"] == "PAPER"
    assert m["activity"][0]["stage"] == "OPPORTUNITY"


def test_missing_telemetry_never_fabricates_values():
    m=ui.launch_home_model({}, {})
    assert m["cards"]["equity"] == "—"
    assert m["cards"]["cash"] == "—"
    assert m["cards"]["open_positions"] == 0
    assert m["engine"]["runtime"] == "UNKNOWN"
