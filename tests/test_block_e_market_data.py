from datetime import datetime, timezone
import urllib.error

import radar_block_e_market_data_v2 as e


def test_universe_is_frozen_and_bounded():
    u=e.frozen_universe_v1()
    assert u['frozen'] is True
    assert 20 <= u['count'] <= 50
    assert len(u['hash']) == 64
    assert 'MSFT' in u['members'] and 'SPY' in u['members']
    assert u['real_trading'] is False


def test_gate_fresh_open_quote_is_paper_eligible():
    now=datetime(2026,9,14,14,45,tzinfo=timezone.utc)
    q=e.MarketQuote('MSFT',500,'2026-09-14T14:44:30Z','fixture','OK','USD','OPEN',499.9,500.1,None,e._iso(now),'INTRADAY_QUOTE')
    g=e.market_data_gate(q,now=now)
    assert g['fresh'] is True
    assert g['analysis_valid'] is True
    assert g['paper_execution_eligible'] is True
    assert g['can_submit_broker_order'] is False


def test_gate_stale_open_quote_rejected():
    now=datetime(2026,9,14,14,45,tzinfo=timezone.utc)
    q=e.MarketQuote('NVDA',180,'2026-09-14T14:30:00Z','fixture','OK','USD','OPEN',source_kind='INTRADAY_QUOTE')
    g=e.market_data_gate(q,now=now)
    assert g['paper_execution_eligible'] is False
    assert 'open_market_quote_stale' in g['blockers']


def test_market_closed_is_not_provider_failure():
    now=datetime(2026,9,14,14,45,tzinfo=timezone.utc)
    q=e.MarketQuote('GOOGL',210,'2026-09-13T20:00:00Z','fixture','OK','USD','CLOSED',source_kind='INTRADAY_QUOTE')
    g=e.market_data_gate(q,now=now)
    assert g['provider_status']=='OK'
    assert g['market_state']=='CLOSED'
    assert g['paper_execution_eligible'] is False


def test_provider_404_uses_fallback():
    now=datetime(2026,9,14,14,45,tzinfo=timezone.utc)
    quote=e.MarketQuote('MSFT',500,'2026-09-14T14:44:30Z','fixture','OK','USD','OPEN',source_kind='INTRADAY_QUOTE')
    def broken(symbol,now=None):
        raise urllib.error.HTTPError('x',404,'not found',{},None)
    result=e.fetch_best_quote('MSFT',now=now,providers=[('broken',broken),('fallback',lambda symbol,now=None:quote)])
    assert result['status']=='QUOTE_SELECTED'
    assert result['fallback_used'] is True
    assert result['attempts'][0]['status']=='PROVIDER_HTTP_404'


def test_bad_bid_ask_rejected():
    now=datetime(2026,9,14,14,45,tzinfo=timezone.utc)
    q=e.MarketQuote('AAPL',200,'2026-09-14T14:44:30Z','fixture','OK','USD','OPEN',201,200,source_kind='INTRADAY_QUOTE')
    g=e.market_data_gate(q,now=now)
    assert 'bid_ask_incoherent' in g['blockers']
    assert g['paper_execution_eligible'] is False


def test_stooq_daily_can_never_be_paper_execution_eligible():
    now=datetime(2026,9,14,14,45,tzinfo=timezone.utc)
    q=e.MarketQuote('MSFT',500,'2026-09-14T00:00:00Z','StooqDaily:fixture','OK','USD','UNKNOWN',source_kind='FALLBACK_DAILY')
    g=e.market_data_gate(q,now=now)
    assert g['paper_execution_eligible'] is False


def test_corporate_action_normalization_preserves_raw():
    split=e.normalize_corporate_action(100,{'type':'SPLIT','symbol':'XYZ','ratio':2})
    assert split['raw_price']==100
    assert split['derived_adjusted_price']==50
    assert split['raw_mutated'] is False
    div=e.normalize_corporate_action(100,{'type':'DIVIDEND','symbol':'XYZ','cash_amount':1.25})
    assert div['cash_distribution']==1.25
    assert div['raw_price']==100


def test_deterministic_block_e_validation_passes():
    out=e.deterministic_block_e_validation()
    assert out['status']=='PASS'
    assert out['market_data_test_set']=='DETERMINISTIC_READY'
    assert out['provider_chain_version']=='E_PROVIDER_CHAIN_V2'
    assert out['real_trading'] is False
