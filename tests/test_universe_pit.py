from radar_universe_pit import survivorship_audit, REAL_TRADING


def test_unverified_membership_keeps_survivorship_risk_visible():
    result=survivorship_audit(['NONEXISTENT_TEST_SYMBOL'],'2001-01-01T00:00:00+00:00')
    assert result['survivorship_bias_risk'] is True
    assert 'NONEXISTENT_TEST_SYMBOL' in result['unknown']


def test_real_trading_off():
    assert REAL_TRADING is False
