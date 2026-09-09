import radar_autonomy_e2e_v1 as e2e
from radar_simulation_research_v4 import chronological_walk_forward,expanded_stress_suite,anti_overfit_gate,research_protocol
from radar_champion_challenger_v2 import compete_v2
from radar_recovery_orchestrator_v2 import recovery_plan_v2


def _days(n=120):
    out=[]
    for i in range(n):
        base=100+i*.3
        out.append((f'2026-01-{(i%28)+1:02d}-x{i}',{'AAA':base,'BBB':100+i*.1,'CCC':100-i*.05 if i<100 else 95}))
    return out


def test_strict_walk_forward_has_no_lookahead_and_real_test_windows():
    cfg={'lookback_fast':10,'lookback_slow':30,'fast_weight':.65,'slow_weight':.35,'exit_momentum':-5,'cost_multiplier':1}
    r=chronological_walk_forward(cfg,_days(140),folds=3,min_train=60,validation_days=15,test_days=15)
    assert r['lookahead'] is False
    assert len(r['folds'])>=2
    for fold in r['folds']:
        assert fold['lookahead'] is False
        assert fold['train_days']>=60 and fold['validation_days']>0 and fold['test_days']>0
    assert r['real_trading'] is False


def test_expanded_stress_covers_cost_gap_volatility_sideways_missing_data_and_shock():
    cfg={'lookback_fast':10,'lookback_slow':30,'fast_weight':.65,'slow_weight':.35}
    r=expanded_stress_suite(cfg,_days(120))
    assert {'base','costs_2x','costs_4x','gap_-12','volatility','sideways','missing_data','shock_-20'} <= set(r['scenarios'])
    assert r['real_trading'] is False


def test_research_protocol_never_promotes_live():
    cfg={'lookback_fast':10,'lookback_slow':30,'fast_weight':.65,'slow_weight':.35}
    r=research_protocol(cfg,_days(140))
    assert r['automatic_live_promotion'] is False
    assert r['real_trading'] is False
    assert r['gate']['can_promote_to_paper'] is False


def test_anti_overfit_rejects_too_few_folds():
    gate=anti_overfit_gate({'folds':[]},{'survival_pass':True})
    assert gate['status']=='REJECT'
    assert 'TOO_FEW_WALK_FORWARD_FOLDS' in gate['blockers']


def test_challenger_can_recommend_replacement_but_not_apply_it():
    models=[
      {'model_version':'champ','forward_n':50,'forward_days':20,'forward_only':True,'matured_only':True,'backfilled':False,'cost_aware':True,'benchmark_aware':True,'mean_excess_return':.02},
      {'model_version':'chall','forward_n':55,'forward_days':22,'forward_only':True,'matured_only':True,'backfilled':False,'cost_aware':True,'benchmark_aware':True,'mean_excess_return':.05},
    ]
    r=compete_v2(models,current_champion_version='champ',margin=.01)
    assert r['replacement_recommended'] is True
    assert r['automatic_replacement'] is False
    assert r['promotion_scope']=='SHADOW_PAPER_ONLY'
    assert r['real_trading'] is False


def test_recovery_fails_closed_and_preserves_missing_as_missing():
    r=recovery_plan_v2(cloud_fresh=False,provider_ok=False,missing_data=True,retry_count=3)
    assert r['can_execute_new_paper'] is False
    assert 'FREEZE_NEW_PAPER_RISK' in r['actions']
    assert 'KEEP_MISSING_AS_MISSING' in r['actions']
    assert r['evidence_mutation_allowed'] is False
    assert r['real_trading'] is False


def test_e2e_chain_reports_observed_components_without_claiming_forward_maturity(monkeypatch):
    monkeypatch.setattr(e2e,'simulator_status',lambda:{'last_cycle_at':'2026-09-10T00:00:00+00:00','completed_experiments':6,'completed_cycles':2,'status':'ACTIVE','paper':{'enabled':True},'experiment_memory':{'count':6}})
    r=e2e.e2e_cycle_status()
    assert r['status']=='AUTONOMOUS_CHAIN_OBSERVED'
    assert r['forward_outcome_and_learning_require_mature_real_time_evidence'] is True
    assert r['real_trading'] is False
