import radar_causal_scoring_v2 as causal


def test_causal_health_is_observational_only():
    health=causal.causal_scoring_health([])
    assert health['symbols_checked']==0
    assert health['max_score_adjustment']==1.5
    assert health['one_contribution_per_independent_event'] is True
    assert health['promotion_authorized'] is False
    assert health['real_trading'] is False


def test_causal_adjustment_remains_bounded():
    assert causal.MAX_SCORE_ADJUSTMENT == 1.5
    assert causal.REAL_TRADING is False
    assert causal.RELATION_SIGN['exposed_to'] == 0.0
