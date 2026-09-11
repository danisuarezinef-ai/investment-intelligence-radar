import math

import radar_strategy_evaluation_v1 as ev


def test_fifo_closed_decisions_accounts_for_costs_and_partial_exit():
    trades=[
        {'ts':'2026-01-01T10:00:00+00:00','symbol':'AAA','side':'BUY','qty':10,'price':10,'gross':100,'costs':2,'reason':'entry'},
        {'ts':'2026-01-03T10:00:00+00:00','symbol':'AAA','side':'SELL','qty':4,'price':12,'gross':48,'costs':1,'reason':'partial'},
        {'ts':'2026-01-05T10:00:00+00:00','symbol':'AAA','side':'SELL','qty':6,'price':9,'gross':54,'costs':1.2,'reason':'exit'},
    ]
    result=ev.fifo_closed_decisions(trades)
    assert result['closed_count']==2
    assert result['open_lots']==0
    assert result['unmatched_sell_qty']==0
    assert result['closed'][0]['outcome_class']=='WIN'
    assert result['closed'][1]['outcome_class']=='LOSS'
    assert result['closed'][0]['duration_hours']==48
    assert all(r['forward_evidence'] is False for r in result['closed'])


def test_decision_metrics_distinguish_hit_rate_from_profit_quality_and_luck():
    rows=[
        {'realized_pnl':100,'return_pct':20,'entry_capital':500,'costs':2},
        {'realized_pnl':2,'return_pct':1,'entry_capital':200,'costs':1},
        {'realized_pnl':-8,'return_pct':-4,'entry_capital':200,'costs':1},
    ]
    m=ev.decision_metrics(rows)
    assert m['mature_decisions']==3
    assert math.isclose(m['hit_rate'],2/3)
    assert m['profit_factor']>1
    assert m['largest_win_share']>0.95
    assert m['anti_luck_score']<10
    assert m['error_cost_ratio']>0


def test_drawdown_profile_measures_depth_duration_and_recovery():
    marks=[
        {'ts':'2026-01-01T00:00:00+00:00','total':100},
        {'ts':'2026-01-02T00:00:00+00:00','total':90},
        {'ts':'2026-01-03T00:00:00+00:00','total':95},
        {'ts':'2026-01-04T00:00:00+00:00','total':101},
    ]
    d=ev.drawdown_profile(marks)
    assert math.isclose(d['max_drawdown_pct'],-10,abs_tol=1e-9)
    assert math.isclose(d['current_drawdown_pct'],0,abs_tol=1e-9)
    assert d['max_drawdown_duration_hours']>=48
    assert d['max_recovery_hours']>=72


def test_risk_attribution_penalizes_overshoot_and_concentration():
    diversified=ev.risk_attribution({'total':100,'invested':70,'positions':[{'value':35},{'value':35}]},70)
    concentrated=ev.risk_attribution({'total':100,'invested':90,'positions':[{'value':90}]},70)
    assert diversified['risk_budget_compliance_score']>concentrated['risk_budget_compliance_score']
    assert concentrated['top_position_share']==1


def test_abstention_quality_requires_counterfactual_evidence():
    result=ev.abstention_metrics([
        {'decision_state':'NO_TRADE','outcome':{'counterfactual_return_pct':-3}},
        {'decision_state':'ABSTAIN','outcome':{'counterfactual_return_pct':2}},
        {'decision_state':'NO_TRADE','outcome':{}},
        {'decision_state':'BUY','outcome':{'counterfactual_return_pct':-5}},
    ])
    assert result['evaluated']==2
    assert result['good_abstentions']==1
    assert result['bad_abstentions']==1
    assert result['quality']==0.5


def test_v_change_explanation_is_component_level_and_read_only():
    out=ev.v_change_explanation(
        {'v_score':210,'v_components':{'decision_quality':50,'risk_control':60}},
        {'v_score':224,'v_components':{'decision_quality':58,'risk_control':57}},
    )
    assert out['v_delta']==14
    assert out['component_changes'][0]['component']=='decision_quality'
    assert out['real_trading'] is False


def test_module_has_no_live_trading_authority():
    assert ev.REAL_TRADING is False
