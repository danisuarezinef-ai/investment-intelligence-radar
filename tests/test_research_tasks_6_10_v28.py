import radar_simulation_research_v5 as r
from radar_experiment_memory_v2 import stage_funnel


def _days(n=220):
    out=[]
    for i in range(n):
        out.append((f'2026-01-{i+1:03d}',{'AAA':100+i*.4,'BBB':120+i*.15,'CCC':80+i*.25}))
    return out


def _cfg():
    return {'lookback_fast':10,'lookback_slow':30,'fast_weight':.7,'slow_weight':.3,'exit_momentum':-5,'cost_multiplier':1,'max_positions':2,'per_position':.12}


def test_task6_walk_forward_is_oos_and_chronological():
    w=r.chronological_walk_forward(_cfg(),_days(),folds=3,min_train=90,validation_days=20,test_days=20)
    assert w['completed'] is True and w['lookahead'] is False
    assert len(w['folds'])>=2
    for f in w['folds']:
        assert f['validation']['evidence_class']=='SIMULATED_OOS_ONLY'
        assert f['test']['evidence_class']=='SIMULATED_OOS_ONLY'
        assert f['train_end'] < f['validation_end'] < f['test_end']


def test_task7_stress_has_required_failure_modes():
    s=r.expanded_stress_suite(_cfg(),_days())
    names=set(s['scenarios'])
    assert {'costs_4x','gap_-20','volatility_20','sideways','missing_data','shock_-30'} <= names
    assert s['real_trading'] is False


def test_task8_ranking_includes_sortino_and_tail_risk():
    p=r.research_protocol(_cfg(),_days())
    assert {'SHARPE','SORTINO','TAIL_RISK','MAX_DRAWDOWN'} <= set(p['ranking_dimensions'])
    assert isinstance(p['research_score'],float)


def test_task9_overfit_gate_rejects_bad_oos_and_stress():
    walk={'folds':[{'validation':{'completed':True,'return_pct':10},'test':{'completed':True,'return_pct':-20}}, {'validation':{'completed':True,'return_pct':12},'test':{'completed':True,'return_pct':25}}]}
    g=r.anti_overfit_gate(walk,{'survival_pass':False})
    assert g['status']=='REJECT'
    assert 'STRESS_SURVIVAL_FAILED' in g['blockers']
    assert g['can_promote_to_paper'] is False and g['real_trading'] is False


def test_task10_funnel_requires_forward_evidence_for_paper():
    research=stage_funnel(research_gate='PASS_RESEARCH',shadow_forward_n=0,shadow_days=0,paper_forward_n=0,paper_days=0,degradation_clear=False)
    assert research['stage']=='SHADOW'
    mature=stage_funnel(research_gate='PASS_RESEARCH',shadow_forward_n=25,shadow_days=8,paper_forward_n=45,paper_days=15,degradation_clear=True)
    assert mature['stage']=='PAPER_MATURE'
    assert mature['automatic_live_promotion'] is False and mature['real_trading'] is False
