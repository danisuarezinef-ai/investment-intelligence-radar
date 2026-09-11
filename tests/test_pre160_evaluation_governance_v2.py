import radar_pre160_evaluation_v1 as e
import radar_league_governance_v2 as g


def test_horizon_quality_never_uses_backfilled_records():
    records=[
        {'horizon':'1d','immutable':True,'backfilled':False,'outcome':{'net_return_pct':2,'hit':True}},
        {'horizon':'1d','immutable':True,'backfilled':True,'outcome':{'net_return_pct':100,'hit':True}},
    ]
    out=e.horizon_quality(records)
    assert out['horizons']['1d']['n']==1
    assert out['horizons']['1d']['mean_return_pct']==2


def test_regime_generalization_requires_real_breadth():
    insufficient=e.regime_generalization([{'regime':'RISK_ON','return_pct':1}]*5)
    assert insufficient['generalization_score'] is None
    records=[]
    for regime,rets in [('RISK_ON',[2,1,3]),('RISK_OFF',[1,.5,1.5]),('NEUTRAL',[1,1,1])]:
        records += [{'regime':regime,'return_pct':x} for x in rets]
    good=e.regime_generalization(records)
    assert good['regimes_evaluated']==3
    assert good['generalization_score']>60


def test_diversity_flags_clone_like_strategies():
    out=e.diversity_score({'a':[1,2,3,4],'b':[1,2,3,4]}, {'a':['X','Y'],'b':['X','Y']})
    assert out['clone_risk']=='HIGH'
    assert out['score']<20


def test_transfer_and_anti_overfit_penalize_collapse():
    historical={'hit_rate':.7,'excess_return_pct':8,'decision_quality':80,'max_drawdown_pct':-4}
    live={'hit_rate':.4,'excess_return_pct':-4,'decision_quality':40,'max_drawdown_pct':-15}
    tr=e.historical_live_transfer(historical,live)
    ao=e.anti_overfitting_score(historical,live,live,live)
    assert tr['score']<50
    assert ao['score']<50


def test_data_quality_missing_fields_do_not_become_success():
    out=e.data_quality_score(freshness=1,benchmark_coverage=None,cost_coverage=.5,pit_verified=True,
                             provider_consensus=None,forward_integrity=True)
    assert out['checks']['benchmark_coverage']=='UNKNOWN'
    assert out['score']<90


def test_quality_gate_is_fail_closed():
    out=e.quality_gate(decision_metrics={'mature_decisions':20})
    assert out['passed'] is False
    assert 'data_quality' in out['failed']


def test_quality_promotion_penalizes_luck_and_instability():
    champion={'v_score':270,'current_equity':1100,'v_confidence':.8,'max_drawdown_pct':-4,'v_components':{'evidence':80}}
    challenger={'v_score':300,'current_equity':1200,'v_confidence':.8,'max_drawdown_pct':-5,'v_components':{'evidence':80}}
    robust=g.quality_readiness(challenger,champion,common_days=30,persistence_score=90,
                               benchmark_score=80,calibration_score=80,stability_score=85,anti_luck_score=90)
    lucky=g.quality_readiness(challenger,champion,common_days=30,persistence_score=90,
                              benchmark_score=80,calibration_score=80,stability_score=20,anti_luck_score=10)
    assert robust['readiness']>lucky['readiness']
    assert robust['eligible'] is True
    assert lucky['eligible'] is False


def test_champion_degradation_never_auto_demotes_or_trades():
    out=g.champion_degradation({'v_score':300,'max_drawdown_pct':-2,'v_confidence':.9,'period_change_pct':10},
                               {'v_score':240,'max_drawdown_pct':-15,'v_confidence':.5,'period_change_pct':-5},
                               challenger_readiness=95)
    assert out['degraded'] is True
    assert out['automatic_demotion'] is False
    assert out['can_trade'] is False
    assert out['real_trading'] is False
