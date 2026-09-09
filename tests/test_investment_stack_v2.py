from datetime import datetime, timezone

import radar_risk_engine_v21 as risk21
import radar_allocation_engine_v2 as alloc2
import radar_global_universe_v2 as universe2
import radar_asset_evidence_engine_v1 as evidence1
import radar_decision_lab_v6 as dl6


def base_portfolio():
    return {'total':1000,'cash':1000,'invested':0,'max_drawdown_pct':0,'positions':[]}


def buy_card(symbol='AAA', er=12, down=-4, conf=.8, risk=1):
    return {'symbol':symbol,'action':'BUY','evidence_complete':True,'expected_return_pct':er,
            'downside_pct':down,'confidence':conf,'risk_score':risk,'valuation_risk':risk,'horizon':'3m'}


def test_risk_v21_requires_volatility_and_regime():
    r=risk21.risk_gate_v21(base_portfolio(), {'symbol':'AAA','action':'BUY','requested_budget':100,'confidence':.8},
        metadata={'sector':'tech','geography':'US','fx':'USD','liquidity_score':1}, correlations={}, regime={})
    assert r['blocked'] is True
    assert 'volatility_evidence_missing' in r['blockers']
    assert 'regime_evidence_missing' in r['blockers']
    assert r['real_trading'] is False


def test_risk_v21_allows_complete_bounded_case():
    r=risk21.risk_gate_v21(base_portfolio(), {'symbol':'AAA','action':'BUY','requested_budget':100,'confidence':.8},
        metadata={'sector':'tech','geography':'US','fx':'USD','liquidity_score':1,'annualized_vol_pct':20},
        correlations={}, regime={'state':'NEUTRAL','risk_multiplier':.8})
    assert r['blocked'] is False
    assert 0 < r['allowed_budget'] <= 100


def test_allocation_v2_keeps_cash_floor_and_competes():
    cards=[buy_card('AAA',15),buy_card('BBB',8)]
    result=alloc2.allocate_capital_v2(cards, base_portfolio())
    assert result['cash_is_competitor'] is True
    assert result['cash_target'] >= 150
    assert result['allocated_budget'] <= 750
    assert result['allocations'][0]['symbol']=='AAA'
    assert result['real_trading'] is False


def test_universe_v2_fail_closed_on_unverified_tradability():
    r=universe2.universe_triage([
        {'symbol':'AAA','tradable':True,'liquidity_score':.9,'geography':'US','currency':'USD','price_fresh':True},
        {'symbol':'BAD','tradable':False,'liquidity_score':.9,'geography':'US','currency':'USD'}])
    assert r['accepted_count']==1
    assert r['decision_lab_symbols']==['AAA']
    assert r['rejected_count']==1


def test_asset_evidence_marks_stale_required_data_incomplete():
    now=datetime(2026,9,9,tzinfo=timezone.utc)
    r=evidence1.build_asset_evidence('AAA',{
        'market':{'timestamp':'2026-09-01T00:00:00Z','source':'x'},
        'fundamentals':{'timestamp':'2026-09-08T00:00:00Z','source':'y'},
        'risk':{'timestamp':'2026-09-08T00:00:00Z','source':'z'}},now=now)
    assert r['evidence_complete'] is False
    assert 'market_stale' in r['blockers']
    assert r['real_trading'] is False


def test_decision_lab_v6_compares_and_exposes_opportunity_cost():
    cards=[buy_card('AAA',15),buy_card('BBB',8)]
    allocation={'allocations':[{'symbol':'AAA','target_budget':100,'target_fraction':.1}]}
    out=dl6.decision_lab_v6(cards,allocation=allocation)
    assert out['best_symbol']=='AAA'
    aaa=next(x for x in out['cards'] if x['symbol']=='AAA')
    bbb=next(x for x in out['cards'] if x['symbol']=='BBB')
    assert aaa['action_v6']=='BUY'
    assert bbb['opportunity_cost_utility'] > 0
    assert out['real_trading'] is False


def test_stack_has_no_real_trading():
    assert risk21.REAL_TRADING is False
    assert alloc2.REAL_TRADING is False
    assert universe2.REAL_TRADING is False
    assert evidence1.REAL_TRADING is False
    assert dl6.REAL_TRADING is False
