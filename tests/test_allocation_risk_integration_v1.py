import math

from radar_allocation_engine_v1 import allocate_capital, opportunity_utility
from radar_risk_engine_v2 import risk_gate_v2
from radar_decision_allocation_v1 import integrated_portfolio_plan


def buy(symbol='AAA', er=12.0, downside=-4.0, conf=.8, valuation=2.0):
    return {
        'symbol': symbol, 'horizon': '30d', 'action': 'BUY',
        'evidence_complete': True, 'expected_return_pct': er,
        'downside_pct': downside, 'confidence': conf,
        'valuation_risk': valuation,
    }


def portfolio():
    return {
        'total': 1000.0, 'cash': 700.0, 'invested': 300.0,
        'max_drawdown_pct': -2.0,
        'positions': [
            {'symbol': 'OLD', 'value': 300.0, 'sector': 'industrial',
             'geography': 'EU', 'fx': 'EUR'}
        ],
    }


def test_allocation_only_uses_complete_buy_evidence():
    cards = [
        buy('AAA'),
        {**buy('BBB'), 'action': 'WATCH'},
        {**buy('CCC'), 'evidence_complete': False},
    ]
    out = allocate_capital(cards, portfolio())
    assert [x['symbol'] for x in out['allocations']] == ['AAA']
    assert out['total_budget'] <= 200.0
    assert out['real_trading'] is False


def test_allocation_blocks_incomplete_capital_state():
    out = allocate_capital([buy()], {'total': 1000.0})
    assert out['blocked'] is True
    assert 'capital_state_incomplete' in out['blockers']


def test_risk_v2_blocks_missing_material_metadata():
    proposal = {
        'symbol': 'AAA', 'action': 'BUY', 'requested_budget': 100.0,
        'confidence': .8,
    }
    out = risk_gate_v2(portfolio(), proposal, metadata={}, correlations={('AAA', 'OLD'): .2})
    assert out['blocked'] is True
    assert 'sector_evidence_missing' in out['blockers']
    assert 'liquidity_evidence_missing' in out['blockers']


def test_risk_v2_blocks_high_pair_correlation():
    proposal = {
        'symbol': 'AAA', 'action': 'BUY', 'requested_budget': 100.0,
        'confidence': .8,
    }
    meta = {'sector': 'technology', 'geography': 'US', 'fx': 'USD', 'liquidity_score': .9}
    out = risk_gate_v2(portfolio(), proposal, meta, {('AAA', 'OLD'): .91})
    assert out['blocked'] is True
    assert 'pair_correlation_limit' in out['blockers']


def test_risk_v2_allows_only_bounded_budget_when_evidence_complete():
    proposal = {
        'symbol': 'AAA', 'action': 'BUY', 'requested_budget': 500.0,
        'confidence': .8,
    }
    meta = {'sector': 'technology', 'geography': 'US', 'fx': 'USD', 'liquidity_score': .9}
    out = risk_gate_v2(portfolio(), proposal, meta, {('AAA', 'OLD'): .2})
    assert out['blocked'] is False
    assert 0 < out['allowed_budget'] <= 200.0
    assert out['real_trading'] is False


def test_integrated_pipeline_never_enables_execution():
    meta = {'AAA': {'sector': 'technology', 'geography': 'US', 'fx': 'USD', 'liquidity_score': .9}}
    out = integrated_portfolio_plan(
        portfolio=portfolio(), cards=[buy('AAA')], metadata_by_symbol=meta,
        correlations={('AAA', 'OLD'): .2},
    )
    assert out['pipeline'] == 'DECISION_LAB_V5 -> ALLOCATION_V1 -> RISK_V2'
    assert out['approved_count'] == 1
    assert out['execution_enabled'] is False
    assert out['can_trade'] is False
    assert out['real_trading'] is False


def test_opportunity_utility_rejects_watch():
    assert opportunity_utility({**buy(), 'action': 'WATCH'}) is None
