from radar_block_d_validation_v1 import trial001_accounting_validation


def test_trial001_accounting_lifecycle_isolated_and_paper_only():
    out=trial001_accounting_validation()
    assert out['status']=='PASS', out
    assert out['trial_id']=='RADAR_FIRST_PAPER_TRIAL_001'
    assert out['initial_cash']==100000.0
    assert out['isolated_from_champion'] is True
    assert out['real_trading'] is False
    assert out['live_execution_allowed'] is False
    assert out['broker_connected'] is False
    assert out['accounting']['equation_error']==0.0
    assert out['accounting']['unaccounted_fills']==0
    assert out['checks']['full_buy_applied'] is True
    assert out['checks']['partial_buy_applied'] is True
    assert out['checks']['partial_sell_applied'] is True
    assert out['checks']['full_close_applied'] is True
    assert 'AAA' not in out['final_account']['positions']
