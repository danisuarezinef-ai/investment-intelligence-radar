from radar_autonomous_learning_16_40_v1 import (
    REAL_TRADING, build_priorities_16_40, entry_threshold_sweep, holding_duration,
    family_alpha_policy, balance_indicator,
)


def _row(i, *, confidence=.7, net=.01, excess=.005, family='trend', horizon='1d', regime='risk_on'):
    return {
        'prediction_id':i,'created_at':f'2026-09-{1+(i%4):02d}T10:00:00+00:00','evaluated_at':f'2026-09-{2+(i%4):02d}T10:00:00+00:00',
        'symbol':f'S{i%10}','horizon':horizon,'model_version':'m1','confidence':confidence,
        'uncertainty':{'score':.2,'regime':regime},'decision_state':'BUY','matured':True,'natural':True,
        'regime':regime,'sector':f'sector{i%4}','market':'US','family':family,'quality':1.0,
        'quality_checks':{'pit_valid':True,'natural':True},'net_return':net,'raw_return':net+.001,
        'excess_return':excess,'benchmark_return':net-excess,'cost':.001,'action_hit':net>0,
        'payload':{},'outcome':{'net_return':net,'return':net+.001,'excess_return':excess,'cost':.001},
    }


def _sim():
    return {
        'active':True,'status':'ACTIVE','generation':10,'completed_cycles':250,'completed_experiments':54,
        'queued_experiments':0,'automatic_live_promotion':False,
        'paper':{'enabled':True,'total':1010.0,'cash':650.0,'invested':360.0,'pnl_pct':.01},
        'recent_runs':[{'result':{'decision_class':'ABSTAIN_NO_CANDIDATE'}},{'result':{'decision_class':'PAPER_CYCLE_WITH_CANDIDATES'}}],
        'recent_experiments':[
            {'generation':9,'experiment_id':'a','configuration':{'method':'trend'},'stage':'SHADOW_REVIEW','gate_status':'PASS_RESEARCH','research_score':1,'created_at':'2026-09-10'},
            {'generation':9,'experiment_id':'b','configuration':{'method':'mean_reversion'},'stage':'SHADOW_REVIEW','gate_status':'PASS_RESEARCH','research_score':1,'created_at':'2026-09-10'},
        ],'real_trading':False,
    }


def test_priorities_16_40_remain_paper_only_and_time_gated():
    rows=[_row(i) for i in range(50)]
    snap=build_priorities_16_40(rows,{'alpha':{'status':'PASS','n':50,'mean_net_return':.01}},
                                {'correlations':{'status':'PENDING_SAMPLE'}},_sim(),persist=False)
    assert REAL_TRADING is False
    assert snap['real_trading'] is False and snap['live_execution_allowed'] is False
    assert snap['automatic_promotion'] is False
    assert snap['tasks']['16']['state']=='PASS'
    assert snap['tasks']['17']['state']=='PASS'
    assert snap['tasks']['18']['state']=='PASS'
    assert snap['tasks']['19']['state']=='PASS'
    assert snap['tasks']['20']['state']=='PASS'
    assert snap['tasks']['36']['state'] in ('PENDING_SAMPLE','PENDING_TIME')
    assert snap['tasks']['37']['state'] in ('PENDING_SAMPLE','PENDING_TIME')
    assert snap['tasks']['38']['state'] in ('PENDING_SAMPLE','PENDING_TIME')
    assert snap['tasks']['38']['evidence']['acceleration_allowed'] is False
    assert snap['tasks']['40']['evidence']['state']=='PROFIT'


def test_entry_threshold_is_advisory_not_strategy_mutation():
    rows=[_row(i,confidence=.8 if i<25 else .55,net=.02 if i<25 else -.02) for i in range(50)]
    out=entry_threshold_sweep(rows)
    assert out['status']=='PASS'
    assert out['best_observed']['threshold']>=.60
    assert out['automatically_change_strategy'] is False
    assert out['real_trading'] is False


def test_holding_duration_never_substitutes_maturation_window():
    out=holding_duration([_row(i) for i in range(30)])
    assert out['status']=='PENDING_SAMPLE'
    assert out['reason']=='NO_EXPLICIT_EXECUTION_HOLDING_DURATION'
    assert out['created_to_evaluated_not_substituted'] is True


def test_family_policy_has_sample_gates_and_paper_only_reduction():
    rows=[_row(i,net=-.01,family='bad') for i in range(25)] + [_row(100+i,net=.01,family='good') for i in range(25)]
    out=family_alpha_policy(rows)
    assert out['families']['bad']['paper_weight_multiplier']==.5
    assert out['families']['good']['paper_weight_multiplier']==1.0
    assert out['automatic_only_after_sample_gate'] is True
    assert out['applied_to_live'] is False and out['real_trading'] is False


def test_balance_indicator_is_machine_readable_simulation_only():
    out=balance_indicator(_sim())
    assert out['state']=='PROFIT' and out['glyph']=='↑'
    assert out['label']=='SIMULATION ONLY — NO REAL MONEY'
    assert 0 <= out['gauge_0_100'] <= 100
    assert out['real_trading'] is False
