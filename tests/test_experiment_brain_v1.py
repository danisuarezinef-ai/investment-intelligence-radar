from radar_experiment_brain_v1 import generate_experiments,rank_experiments,REAL_TRADING
from radar_simulation_scheduler_v1 import simulation_cycle


def test_generates_distinct_safe_experiments():
    xs=generate_experiments(3)
    assert len(xs)>=8 and len({x['experiment_id'] for x in xs})==len(xs)
    assert all(x['evidence_class']=='SIMULATED_HISTORICAL_ONLY' for x in xs)
    assert all(x['eligible_for_forward_promotion'] is False and x['real_trading'] is False for x in xs)
    assert REAL_TRADING is False


def test_rank_is_survival_aware_and_review_only():
    xs=rank_experiments([{'experiment_id':'a','completed':True,'return_pct':10,'alpha_pct':5,'max_drawdown_pct':-40,'costs':1,'stability_score':1},{'experiment_id':'b','completed':True,'return_pct':7,'alpha_pct':4,'max_drawdown_pct':-5,'costs':1,'stability_score':1}])
    assert xs[0]['experiment_id']=='b'
    assert all(x['promotion']=='SHADOW_CANDIDATE_REVIEW_ONLY' and x['real_trading'] is False for x in xs)


def test_scheduler_requires_deep_history_and_health():
    assert simulation_cycle(history_days=10,cloud_fresh=True,persistence_ok=True)['action']=='HOLD'
    r=simulation_cycle(history_days=120,cloud_fresh=True,persistence_ok=True,generation=2)
    assert r['action']=='RUN_EXPERIMENT_BATCH' and r['experiments']
    assert r['can_promote_directly'] is False and r['real_trading'] is False


def test_scheduler_fails_closed_on_stale_cloud():
    r=simulation_cycle(history_days=120,cloud_fresh=False,persistence_ok=True)
    assert r['action']=='HOLD' and 'STALE_CLOUD' in r['blockers']
