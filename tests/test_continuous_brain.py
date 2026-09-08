from radar_continuous_brain import (
    BrainCandidate, EvidenceScore, promotion_gate, transfer_weight,
    retire_component, REAL_TRADING,
)


def score(n=40, objective=.55, brier=.20, drawdown=-.10):
    return EvidenceScore(n=n, objective=objective, brier=brier, drawdown=drawdown)


def test_historical_success_cannot_promote_without_live():
    c = BrainCandidate("3.1", "3.0", score(1000, .90), None, None,
                       provenance_ok=True, immutable_forward=True)
    result = promotion_gate(c)
    assert not result["accepted"]
    assert "insufficient_live_observations" in result["reasons"]


def test_mature_live_gain_can_pass_gate():
    c = BrainCandidate("3.1", "3.0", score(1000, .90), score(50, .56), score(50, .54),
                       complexity_delta=.02, provenance_ok=True, immutable_forward=True)
    assert promotion_gate(c)["accepted"]


def test_bad_calibration_blocks_promotion():
    c = BrainCandidate("3.1", "3.0", None, score(50, .60, brier=.30), score(50, .54, brier=.20),
                       provenance_ok=True, immutable_forward=True)
    assert "calibration_regression" in promotion_gate(c)["reasons"]


def test_historical_transfer_requires_live_directional_agreement():
    assert transfer_weight(.10, -.01, 1000, 50) == 0.0
    assert 0 < transfer_weight(.10, .02, 1000, 50) <= .75


def test_complexity_retirement_waits_for_repeated_live_evidence():
    assert not retire_component([-.01, -.01])
    assert retire_component([-.01, 0.0, -.005])


def test_real_trading_off():
    assert REAL_TRADING is False
