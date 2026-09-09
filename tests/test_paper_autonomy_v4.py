import pytest

import radar_simulator_engine_v3 as sim
import radar_paper_to_tiny_live_gate_v1 as gate
import radar_autonomous_investment_loop_v2 as loop


def test_simulator_falls_back_only_to_labelled_simulation(monkeypatch):
    monkeypatch.setattr(sim,'decision_lab_v5_snapshot',lambda limit=20:{'cards':[]})
    monkeypatch.setattr(sim,'opportunity_rankings',lambda n:{
        'bajo':[{'symbol':'AAA','score':3,'risk':'bajo'}], 'intermedio':[], 'alto':[]})
    out=sim.simulator_decision_context()
    assert out['mode']=='SIMULATION_ONLY_HEURISTIC'
    assert out['fallback_used'] is True
    assert out['performance_claim']=='SIMULATED / NOT VERIFIED'
    assert out['real_trading'] is False


def test_verified_cards_disable_heuristic_fallback(monkeypatch):
    monkeypatch.setattr(sim,'decision_lab_v5_snapshot',lambda limit=20:{'cards':[
        {'symbol':'AAA','action':'BUY','evidence_complete':True}]})
    out=sim.simulator_decision_context()
    assert out['mode']=='VERIFIED_DECISION_CARDS'
    assert out['fallback_used'] is False


def test_tiny_live_gate_never_enables_execution():
    e={'paper_days':100,'decisions':100,'matured_outcomes':120,'max_drawdown_pct':-5,
       'benchmark_coverage':1,'cost_coverage':1,'positive_months':6,
       'degradation_clear':True,'shadow_gate_passed':True}
    out=gate.paper_to_tiny_live_gate(e,human_approved=True)
    assert out['ready_for_tiny_live_review'] is True
    assert out['auto_promote'] is False
    assert out['live_execution_allowed'] is False
    assert out['real_trading'] is False


def test_tiny_live_gate_fails_closed_on_missing_evidence():
    out=gate.paper_to_tiny_live_gate({},human_approved=False)
    assert out['ready_for_tiny_live_review'] is False
    assert out['failed']


def test_autonomous_loop_read_only_never_trades(monkeypatch):
    monkeypatch.setattr(loop,'simulator_decision_context',lambda:{'mode':'SIMULATION_ONLY_HEURISTIC','buy_candidates':[]})
    monkeypatch.setattr(loop,'paper_portfolio_v4_status',lambda:{'real_trading':False})
    out=loop.autonomous_loop_v2(run_paper=False)
    assert out['execution_mode']=='READ_ONLY'
    assert out['broker_connected'] is False
    assert out['live_execution_allowed'] is False
    assert out['real_trading'] is False
