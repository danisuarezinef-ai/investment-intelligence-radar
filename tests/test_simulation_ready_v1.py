import radar_cost_model as costs
import radar_simulation_factory as factory
import radar_simulation_readiness as readiness
import radar_corporate_actions as actions


def test_real_trading_off_everywhere():
    assert factory.REAL_TRADING is False
    assert readiness.REAL_TRADING is False
    assert costs.REAL_TRADING is False
    assert actions.REAL_TRADING is False


def test_experiment_id_is_reproducible_and_order_independent():
    assert factory.experiment_id({"a":1,"b":2}) == factory.experiment_id({"b":2,"a":1})


def test_cost_model_is_explicit_and_positive():
    result=costs.estimate_cost(10000,fx_bps=3)
    assert result["total"] > 0
    assert result["real_trading"] is False


def test_readiness_fails_closed_until_evidence_verified():
    result=readiness.audit_simulation_ready()
    assert result["simulation_ready"] is False
    assert result["blocking"]
    assert result["real_trading"] is False
