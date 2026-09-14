from radar_execution_reality_171_190_v1 import board,execution_model

def _states(b):return {int(x['task']):x['status'] for x in b['tasks']}

def test_empty_board_fail_closed():
    b=board(maturity={'valid_forward_hours':0},restart={'downtime_credit':False})
    s=_states(b)
    assert s[174]=='PENDING_TIME' and s[175]=='PENDING_TIME' and s[176]=='PENDING_TIME'
    assert s[184]=='PENDING_DATA' and s[190]=='BLOCKED'
    assert b['real_trading'] is False and b['live_execution_allowed'] is False

def test_maturity_thresholds_use_audited_hours_only():
    b=board(maturity={'valid_forward_hours':72,'overlap_guard':True,'no_backfill':True},restart={'downtime_credit':False})
    s=_states(b)
    assert s[174]=='PASS' and s[175]=='PENDING_TIME' and s[176]=='PENDING_TIME'

def test_execution_requires_observed_liquidity():
    out=execution_model({'side':'BUY','requested_qty':10},{'bid':100,'ask':101})
    assert out['status']=='REJECTED'
    assert out['real_trading'] is False

def test_partial_fill_is_bounded_by_volume():
    out=execution_model({'side':'BUY','requested_qty':100},{'bid':100,'ask':101,'volume':1000,'market_open':True},liquidity_fraction=.01)
    assert out['status']=='PARTIAL'
    assert out['fills'][0]['qty']==10
    assert out['remaining_qty']==90

def test_market_requires_real_metrics():
    b=board(market={'rows':1000,'sources':2,'symbols':10},quotes=[])
    s=_states(b)
    assert s[181]=='PENDING_DATA' and s[183]=='PENDING_DATA' and s[184]=='PENDING_DATA'

def test_execution_reality_gate_cannot_pass_without_accounting():
    quotes=[{'bid':100,'ask':101,'volume':1000,'source':'x'} for _ in range(20)]
    market={'rows':1000,'sources':2,'symbols':10,'stale_rate':0,'gap_rate':0,'duplicate_rate':0,'broken_provider_paths':0,'http_404_count':0,'contemporaneous_multi_source':True}
    features={k:True for k in ('observed_spread','observed_volume','market_hours','partial_fills','rejects','slippage','commissions','liquidity_limits')}
    b=board(market=market,quotes=quotes,execution={'model_features':features},accounting={})
    s=_states(b)
    assert s[181]=='PASS' and s[184]=='PASS' and s[185]=='PASS'
    assert s[189]=='PENDING_PROOF' and s[190]=='BLOCKED'
