from datetime import datetime, timedelta, timezone

import radar_simulator_hardening_8_12_v1 as h


def test_priority8_risk_blocks_sector_cluster_drawdown_and_circuit_breaker():
    positions=[
        {'symbol':'A','sector':'TECH','market_value':180.0},
        {'symbol':'B','sector':'TECH','market_value':180.0},
    ]
    out=h.paper_risk_gate(equity=1000,cash=640,positions=positions,drawdown_pct=0.12,
        portfolio_volatility=0.20,uncertainty=0.30,
        correlated_clusters={'mega-tech':['A','B']},circuit_breaker={'triggered':True})
    assert out['status']=='BLOCKED_PAPER_RISK'
    assert 'sector_concentration' in out['blockers']
    assert 'correlated_cluster' in out['blockers']
    assert 'drawdown' in out['blockers']
    assert 'circuit_breaker_clear' in out['blockers']
    assert out['new_paper_risk_allowed'] is False
    assert out['existing_positions_may_be_reduced'] is True
    assert out['live_execution_allowed'] is False
    assert out['real_trading'] is False


def test_priority8_risk_passes_bounded_paper_portfolio():
    positions=[
        {'symbol':'A','sector':'TECH','market_value':100.0},
        {'symbol':'B','sector':'HEALTH','market_value':100.0},
    ]
    out=h.paper_risk_gate(equity=1000,cash=800,positions=positions,drawdown_pct=0.03,
        portfolio_volatility=0.18,uncertainty=0.20,
        correlated_clusters={'cluster':['A','B']},circuit_breaker={'triggered':False})
    assert out['status']=='PASS_PAPER_RISK'
    assert out['new_paper_risk_allowed'] is True


def test_priority9_historical_or_backfilled_challenger_never_qualifies():
    champion={'forward_only':True,'backfilled':False,'mean_net_return':0.01,'max_drawdown_pct':0.05}
    challenger={'forward_only':False,'matured_only':True,'backfilled':True,'forward_n':500,
        'forward_days':100,'cost_aware':True,'benchmark_aware':True,'mean_net_return':0.08,
        'max_drawdown_pct':0.03,'forward_regimes':['bull','bear'],'forward_horizons':['1d','1w'],
        'return_correlation_to_champion':0.2}
    out=h.challenger_review_gate(champion=champion,challenger=challenger)
    assert out['status']=='SHADOW_ONLY'
    assert out['historical_can_satisfy_forward_gate'] is False
    assert out['automatic_replacement'] is False
    assert out['automatic_promotion'] is False
    assert out['live_execution_allowed'] is False


def test_priority9_requires_regime_horizon_stability_and_diversity():
    champion={'forward_only':True,'backfilled':False,'mean_net_return':0.01,'max_drawdown_pct':0.10}
    challenger={'forward_only':True,'matured_only':True,'backfilled':False,'forward_n':80,
        'forward_days':30,'cost_aware':True,'benchmark_aware':True,'mean_net_return':0.03,
        'max_drawdown_pct':0.08,'forward_regimes':['bull','bear'],'forward_horizons':['1d','1w'],
        'return_correlation_to_champion':0.50,'critical_instability':False}
    out=h.challenger_review_gate(champion=champion,challenger=challenger)
    assert out['status']=='ELIGIBLE_FOR_MANUAL_PAPER_REVIEW'
    assert out['automatic_replacement'] is False
    assert out['promotion_scope']=='MANUAL_REVIEW_PAPER_ONLY'


def test_priority10_disagreement_produces_explicit_abstention_not_forced_trade():
    signals=[{'action':'BUY','confidence':0.8},{'action':'SELL','confidence':0.8}]
    out=h.abstention_disagreement_gate(signals,max_disagreement=0.35)
    assert out['status']=='ABSTAIN'
    assert out['action']=='ABSTAIN'
    assert 'EXCESSIVE_DISAGREEMENT' in out['reasons']
    assert out['journal_required'] is True
    assert out['forced_trade'] is False
    assert out['real_trading'] is False


def test_priority10_low_confidence_or_bad_data_abstains():
    signals=[{'action':'BUY','confidence':0.4},{'action':'BUY','confidence':0.45}]
    out=h.abstention_disagreement_gate(signals,data_integrity_ok=False)
    assert out['action']=='ABSTAIN'
    assert 'DATA_INTEGRITY_FAILURE' in out['reasons']
    assert 'LOW_CONFIDENCE' in out['reasons']


def test_priority11_accounting_truth_reconciles_and_never_silent_corrects():
    out=h.accounting_truth_gate(cash=600,positions=[{'symbol':'A','market_value':400}],
        reported_equity=1000,realized_pnl=20,unrealized_pnl=15,total_costs=5,reported_total_pnl=30)
    assert out['status']=='RECONCILED'
    assert out['calculated_equity']==1000
    assert out['silent_auto_correction'] is False
    assert out['new_paper_risk_allowed'] is True


def test_priority11_accounting_mismatch_is_critical_and_blocks_new_risk():
    out=h.accounting_truth_gate(cash=600,positions=[{'symbol':'A','market_value':400}],
        reported_equity=1100,realized_pnl=20,unrealized_pnl=15,total_costs=5,reported_total_pnl=30)
    assert out['status']=='CRITICAL_RECONCILIATION_FAILURE'
    assert 'equity_identity' in out['blockers']
    assert out['new_paper_risk_allowed'] is False
    assert out['silent_auto_correction'] is False


def _interval(start, hours, **overrides):
    base={
        'start_at':start.isoformat(),
        'end_at':(start+timedelta(hours=hours)).isoformat(),
        'evidence_class':'PROSPECTIVE_PAPER','backfilled':False,'historical':False,
        'simulated_maturity':False,'runtime_healthy':True,'persistence_exact':True,
        'session_continuity':True,'data_integrity':True,'critical_failure':False,
    }
    base.update(overrides); return base


def test_priority12_maturity_counts_only_valid_forward_runtime():
    start=datetime(2026,9,12,12,tzinfo=timezone.utc)
    intervals=[
        _interval(start,40),
        _interval(start+timedelta(hours=40),40,backfilled=True),
        _interval(start+timedelta(hours=80),20,runtime_healthy=False),
        _interval(start+timedelta(hours=100),32),
    ]
    out=h.forward_maturity_clock(intervals)
    assert out['valid_forward_hours']==72.0
    assert out['milestones']['72h']['status']=='PASS'
    assert out['milestones']['7d']['status']=='PENDING_VALID_FORWARD_TIME'
    assert len(out['accepted_intervals'])==2
    assert len(out['rejected_intervals'])==2
    assert out['downtime_counts'] is False
    assert out['wall_time_is_not_maturity'] is True
    assert out['backfill_allowed'] is False


def test_priority12_historical_and_simulated_time_cannot_advance_maturity():
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    intervals=[
        _interval(start,1000,evidence_class='HISTORICAL',historical=True),
        _interval(start+timedelta(hours=1000),1000,simulated_maturity=True),
    ]
    out=h.forward_maturity_clock(intervals)
    assert out['valid_forward_hours']==0.0
    assert all(v['status']=='PENDING_VALID_FORWARD_TIME' for v in out['milestones'].values())


def test_priorities_8_12_composite_preserves_all_safety_boundaries():
    risk={'status':'PASS_PAPER_RISK'}
    champion={'automatic_replacement':False,'automatic_promotion':False}
    abstention={'journal_required':True,'forced_trade':False}
    accounting={'status':'RECONCILED'}
    maturity={'status':'VALID_FORWARD_CLOCK','backfill_allowed':False}
    out=h.priorities_8_12_gate(risk=risk,champion=champion,abstention=abstention,
                               accounting=accounting,maturity=maturity)
    assert out['status']=='PASS'
    assert out['paper_execution_allowed'] is True
    assert out['live_execution_allowed'] is False
    assert out['automatic_promotion'] is False
    assert out['automatic_release'] is False
    assert out['setup_1_6_allowed'] is False
    assert out['real_trading'] is False
