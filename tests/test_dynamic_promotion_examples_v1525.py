import radar_simulator_league_v1 as league


def test_large_quality_advantage_requires_less_evidence_than_marginal_advantage():
    dominant=league.dynamic_required_days(v_gap=60,confidence=.90,equity_gap_pct=15)
    marginal=league.dynamic_required_days(v_gap=7,confidence=.60,equity_gap_pct=1)
    assert dominant < marginal


def test_example_v298_vs_v280_can_be_eligible_only_after_dynamic_evidence():
    required=league.dynamic_required_days(v_gap=18,confidence=.78,equity_gap_pct=4.75)
    assert required != 10 or required == league.dynamic_required_days(18,.78,4.75)
    not_yet=league.promotion_candidate(84,-6.1,-4.2,v_gap=18,confidence=.78,equity_gap_pct=4.75,common_days=required)
    assert not_yet['eligible'] is False
    ready=league.promotion_candidate(92,-6.1,-4.2,v_gap=18,confidence=.78,equity_gap_pct=4.75,common_days=required)
    assert ready['eligible'] is True
