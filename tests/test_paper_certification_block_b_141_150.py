from radar_paper_certification_131_160_v1 import (
    market_reliability,
    symbol_health,
    provider_failover,
    price_consensus,
    spread_capture,
    liquidity_v2,
    market_hours,
    execution_v3,
    order_idempotency,
    execution_accounting_atomicity,
)


def test_block_b_141_150_happy_path_is_paper_only():
    results = [
        market_reliability({
            'coverage': 0.995, 'latency_ms_p95': 250, 'stale_rate': 0.005,
            'gap_rate': 0.005, 'duplicate_rate': 0.001,
            'timestamp_error_rate': 0,
        }),
        symbol_health({'MSFT': {'healthy': True}, 'NVDA': {'healthy': True}}),
        provider_failover({
            'primary': 'p1', 'secondary': 'p2', 'pit_compatible': True,
            'fail_closed_on_divergence': True, 'tested': True,
        }),
        price_consensus({'providers': 2, 'max_cross_provider_divergence': 0.005}),
        spread_capture([{'bid': 100, 'ask': 100.1, 'observed_at': '2026-09-16T08:00:00Z', 'source': 'p1'}]),
        liquidity_v2([{'spread': 0.1, 'volume': 1000, 'observed_at': '2026-09-16T08:00:00Z', 'source': 'p1'}]),
        market_hours({
            'calendar_loaded': True, 'holidays_supported': True,
            'early_close_supported': True, 'timezone_aware': True,
            'closed_market_orders_blocked': True,
        }),
        execution_v3({k: True for k in (
            'partial_fills','rejects','cancellations','market_hours','spread',
            'slippage','commissions','liquidity_limits','idempotency_key'
        )}),
        order_idempotency([{'idempotency_key': 'k1', 'order_id': 'o1'}]),
        execution_accounting_atomicity([{
            'fill_id': 'f1', 'fill_committed': True,
            'accounting_committed': True, 'transaction_id': 'tx1',
        }]),
    ]
    assert [r['task'] for r in results] == list(range(141, 151))
    assert all(r['status'] == 'PASS' for r in results)
    assert all(r['real_trading'] is False for r in results)
    assert all(r['evidence']['real_trading'] is False for r in results)


def test_block_b_fail_closed_and_attention_paths():
    assert market_reliability({
        'coverage': .9, 'latency_ms_p95': 500, 'stale_rate': .1,
        'gap_rate': .1, 'duplicate_rate': .1, 'timestamp_error_rate': 1,
    })['status'] == 'ATTENTION'
    assert symbol_health({'MSFT': {'healthy': False}})['status'] == 'ATTENTION'
    assert spread_capture([{'bid': 101, 'ask': 100, 'observed_at': '2026-09-16T08:00:00Z', 'source': 'p1'}])['status'] == 'FAIL_CLOSED'
    assert order_idempotency([{'idempotency_key': 'same', 'order_id': 'o1'}, {'idempotency_key': 'same', 'order_id': 'o2'}])['status'] == 'FAIL_CLOSED'
    assert execution_accounting_atomicity([{'fill_id': 'f1', 'fill_committed': True, 'accounting_committed': False, 'transaction_id': 'tx1'}])['status'] == 'FAIL_CLOSED'
