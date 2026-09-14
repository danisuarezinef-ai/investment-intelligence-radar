from datetime import datetime, timezone, timedelta

import radar_block_f_pipeline_v1 as f
import radar_block_e_market_data_v2 as e
from radar_paper_accounting_v1 import new_account


def regime():
    return {'status':'OK','regime':'RISK_ON','risk_multiplier':1.0,'confidence_multiplier':1.0,'real_trading':False}


def candidate(symbol='MSFT',score=8.0,risk='bajo'):
    return {'symbol':symbol,'score':score,'expected_return_pct':11.0,'downside_pct':4.0,'risk':risk,'data_quality':.95}


def quote(age_seconds=0,market_state='OPEN'):
    now=datetime.now(timezone.utc); ts=now-timedelta(seconds=age_seconds)
    return e.MarketQuote('MSFT',500.0,e.v1._iso(ts),'fixture','OK','USD',market_state,
                         ingestion_timestamp=e.v1._iso(now),source_kind='INTRADAY_QUOTE')


def test_exactly_five_distinct_brains_and_schema():
    rows=f.five_brain_decisions(candidate(),regime_state=regime(),observed_price=500)
    assert len(rows)==5
    assert {x['brain_id'] for x in rows}==set(f.BRAIN_ORDER)
    required={'action','conviction','horizon','observed_price','thesis','pros','risks','invalidation','decision_id'}
    assert all(required <= set(x) for x in rows)
    assert all(x['real_trading'] is False for x in rows)


def test_369_preserves_disagreement_and_abstention_fields():
    cs=[candidate(f'S{i:02d}',8-i*.5,('bajo','intermedio','alto')[i%3]) for i in range(12)]
    out=f.opportunity_radar_369(cs,regime_state=regime())
    assert [len(out[k]) for k in ('top3','top6','top9')]==[3,6,9]
    assert all('abstentions' in x and 'disagreement' in x for x in out['all'])
    assert out['real_trading'] is False


def test_ensemble_can_explicitly_not_invest():
    unknown={'status':'INSUFFICIENT_EVIDENCE','regime':'UNKNOWN','risk_multiplier':0,'confidence_multiplier':0}
    out=f.ensemble_decision(candidate(),regime_state=unknown,observed_price=500)
    assert out['action']=='NO_INVERTIR'
    assert out['can_submit_broker_order'] is False


def test_stale_quote_cannot_execute():
    state,trace=f.decision_to_paper_execution(candidate(),quote(3600),
        regime_snapshot={'volatility_pct':17,'trend_pct':11,'breadth_pct':67},account=new_account(10000))
    assert trace['status']=='BLOCKED'
    assert trace['reason']=='market_data_gate_failed'
    assert not state['positions']


def test_buy_flow_creates_complete_paper_trace():
    state,trace=f.decision_to_paper_execution(candidate(),quote(),
        regime_snapshot={'volatility_pct':17,'trend_pct':11,'breadth_pct':67},account=new_account(10000))
    assert trace['status']=='PAPER_FILLED'
    assert state['positions']['MSFT']['qty']>0
    assert all(trace['trace_links'][k] for k in ('decision_id','order_id','fill_id','position_symbol'))
    assert trace['real_trading'] is False
    assert trace['can_submit_broker_order'] is False


def test_block_f_validation_passes():
    out=f.block_f_validation()
    assert out['status']=='PASS',out
    assert out['end_to_end_paper_pipeline']=='VERIFIED'
    assert out['real_trading'] is False
