from radar_autonomous_learning_41_60_v1 import (
    REAL_TRADING,
    benchmark_robustness,
    build_priorities_41_60,
    cost_sensitivity,
    empirical_stress,
    manual_promotion_gate,
)


def _row(i, *, net=.01, excess=.004, cost=.001, confidence=.72, model='m1', matured=True):
    day=1+(i%20)
    return {
        'prediction_id':f'p{i}','created_at':f'2026-08-{day:02d}T10:00:00+00:00',
        'evaluated_at':f'2026-09-{1+(i%10):02d}T10:00:00+00:00',
        'symbol':f'S{i%10}','horizon':'1d','model_version':model,'family':'trend',
        'confidence':confidence,'decision_state':'BUY','matured':matured,'natural':True,
        'regime':'risk_on','sector':f'sector{i%4}','market':'US','quality':1.0,
        'quality_checks':{'pit_valid':True,'natural':True},'net_return':net,
        'raw_return':net+cost,'excess_return':excess,'benchmark_return':net-excess,
        'cost':cost,'action_hit':net>0,'payload':{'score':.3,'features':{'source_quality':1.0}},
        'provenance':{'lookahead':False},
        'outcome':{'net_return':net,'return':net+cost,'excess_return':excess,'cost':cost},
    }


def _competition():
    pending={'status':'PENDING_SAMPLE','real_trading':False}
    return {
        'champion_challenger':dict(pending),
        'champion_degradation':dict(pending),
        'shadow_ensemble':dict(pending),
        'diversity_reward':dict(pending),
        'dynamic_routing':dict(pending,lookahead_violations=[],uses_future_outcomes=False),
        'meta_learning':dict(pending),
        'historical_live_transfer':dict(pending,transfer_score=None),
        'real_trading':False,
    }


def _prior(*, alpha='PASS', w='PENDING_SAMPLE', m='PENDING_SAMPLE', q='PENDING_SAMPLE'):
    return {
        'tasks':{
            '20':{'state':alpha},'36':{'state':w},'37':{'state':m},'38':{'state':q},
        },
        'diversity':{'model_count':1},
        'real_trading':False,
    }


def test_priorities_41_60_exist_and_never_gain_execution_authority():
    rows=[_row(i,net=.01 if i%3 else -.005,excess=.004 if i%3 else -.003) for i in range(60)]
    snap=build_priorities_41_60(rows,{},_competition(),_prior(),persist=False)
    assert REAL_TRADING is False
    assert set(snap['tasks'])=={str(i) for i in range(41,61)}
    assert snap['real_trading'] is False
    assert snap['automatic_promotion'] is False
    assert snap['automatic_demotion'] is False
    assert snap['automatic_release'] is False
    assert snap['live_execution_allowed'] is False
    assert snap['setup_1_6_allowed'] is False
    assert snap['tasks']['59']['state']=='BLOCKED_EVIDENCE'
    assert snap['tasks']['60']['state']=='PASS'
    assert snap['tasks']['60']['evidence']['banner']=='SIMULATION ONLY — NO REAL MONEY'


def test_cost_sensitivity_is_monotonic_and_does_not_add_trades():
    rows=[_row(i,net=.01,cost=.001) for i in range(40)]
    out=cost_sensitivity(rows)
    means=[x['mean_net_return'] for x in out['scenarios']]
    assert out['status']=='PASS'
    assert means==sorted(means,reverse=True)
    assert out['synthetic_trades_added'] is False
    assert out['automatic_cost_model_change'] is False
    assert out['real_trading'] is False


def test_single_recorded_benchmark_is_not_misrepresented_as_multi_benchmark_robustness():
    rows=[_row(i) for i in range(40)]
    out=benchmark_robustness(rows)
    assert out['status']=='PASS'
    assert out['multi_benchmark_robustness_verified'] is False
    assert out['single_benchmark_cannot_prove_multi_benchmark_robustness'] is True
    assert out['automatic_benchmark_selection'] is False


def test_empirical_stress_does_not_claim_synthetic_or_crash_replay_evidence():
    rows=[_row(i,net=(-.03 if i==0 else .005)) for i in range(40)]
    costs=cost_sensitivity(rows)
    out=empirical_stress(rows,costs)
    assert out['status']=='PASS'
    assert out['historical_crash_replay_claimed'] is False
    assert out['synthetic_market_path_claimed'] is False
    assert out['can_change_live_risk'] is False


def test_manual_promotion_gate_stays_blocked_until_natural_long_horizons_and_advanced_evidence_pass():
    tasks={str(i):{'state':'PASS'} for i in range(41,59)}
    tasks['50']['state']='READY_FOR_MANUAL_COMPARISON'
    gate=manual_promotion_gate(tasks,_prior(alpha='PASS'))
    assert gate['status']=='BLOCKED_EVIDENCE'
    assert any('prior_task_36' in x for x in gate['blockers'])
    assert gate['manual_review_only'] is True
    assert gate['automatic_promotion'] is False
    assert gate['automatic_demotion'] is False
    assert gate['automatic_release'] is False
    assert gate['setup_1_6_allowed'] is False
    assert gate['live_execution_allowed'] is False


def test_manual_gate_can_only_become_manual_review_eligible_never_auto_promote():
    tasks={str(i):{'state':'PASS'} for i in range(41,59)}
    tasks['50']['state']='READY_FOR_MANUAL_COMPARISON'
    prior=_prior(alpha='PASS',w='PASS',m='PASS',q='PASS')
    gate=manual_promotion_gate(tasks,prior)
    assert gate['status']=='MANUAL_REVIEW_ELIGIBLE'
    assert gate['manual_review_only'] is True
    assert gate['automatic_promotion'] is False
    assert gate['live_execution_allowed'] is False
