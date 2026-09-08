def test_simulation_desktop_imports_without_starting_ui():
    import radar_simulation_desktop as m
    assert m.REAL_TRADING is False
    assert callable(m.main)
