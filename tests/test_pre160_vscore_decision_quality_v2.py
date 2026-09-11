import radar_simulator_vscore_v1 as v


def _status():
    return {'initial':200,'total':220,'invested':140,'max_drawdown_pct':-3,'sharpe':1.2,'marks':100}


def test_mature_closed_decisions_replace_daily_proxy_gradually():
    daily=[{'date':f'2026-01-{i:02d}','equity':200+i} for i in range(1,16)]
    good={'mature_decisions':15,'hit_rate':.67,'mean_return_pct':3.0,'profit_factor':2.2,
          'capital_efficiency_pct':8,'anti_luck_score':85,'error_cost_ratio':.25}
    poor={'mature_decisions':15,'hit_rate':.33,'mean_return_pct':-2.0,'profit_factor':.55,
          'capital_efficiency_pct':-5,'anti_luck_score':40,'error_cost_ratio':.72}
    a=v.compute_v_score(_status(),daily,trade_count=30,distinct_symbols=6,decision_metrics=good)
    b=v.compute_v_score(_status(),daily,trade_count=30,distinct_symbols=6,decision_metrics=poor)
    assert a['v_components']['decision_quality']>b['v_components']['decision_quality']
    assert a['v_score']>b['v_score']
    assert 'REALIZED_CLOSED' in a['score_semantics']


def test_tiny_closed_sample_cannot_override_fallback():
    daily=[{'date':'2026-01-01','equity':200},{'date':'2026-01-02','equity':201}]
    tiny={'mature_decisions':1,'hit_rate':1.0,'mean_return_pct':100,'profit_factor':99,
          'capital_efficiency_pct':100,'anti_luck_score':0,'error_cost_ratio':0}
    out=v.compute_v_score(_status(),daily,trade_count=1,distinct_symbols=1,decision_metrics=tiny)
    assert out['score_semantics']=='OBSERVED_PAPER_DECISION_QUALITY_PROXY'
    assert out['v_confidence']<.7


def test_regime_linkage_replaces_generalization_proxy_only_with_evidence():
    daily=[{'date':f'2026-01-{i:02d}','equity':200+i} for i in range(1,10)]
    proxy=v.compute_v_score(_status(),daily,trade_count=10,distinct_symbols=4)
    actual=v.compute_v_score(_status(),daily,trade_count=10,distinct_symbols=4,
                             regime_metrics={'regimes_evaluated':3,'generalization_score':91})
    assert proxy['generalization_status']=='PROXY_UNTIL_REGIME_LINKAGE'
    assert actual['generalization_status']=='OBSERVED_REGIME_LINKAGE'
    assert actual['v_components']['generalization']==91


def test_blocked_turnover_cannot_improve_consistency():
    daily=[{'date':f'2026-01-{i:02d}','equity':200+i} for i in range(1,10)]
    base=v.compute_v_score(_status(),daily,trade_count=10,distinct_symbols=4)
    blocked=v.compute_v_score(_status(),daily,trade_count=10,distinct_symbols=4,
                              turnover_metrics={'status':'BLOCKED'})
    assert blocked['v_components']['consistency']<base['v_components']['consistency']


def test_vscore_never_grants_trading_authority():
    out=v.compute_v_score(_status(),[])
    assert out['real_trading'] is False
    assert out['can_trade'] is False
    assert out['automatic_model_promotion'] is False
