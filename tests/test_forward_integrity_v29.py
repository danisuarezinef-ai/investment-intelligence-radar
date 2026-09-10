from radar_champion_challenger_v2 import compete_v2
from radar_evidence_scorecard_v1 import scorecard
from radar_experiment_memory_v2 import stage_funnel


def test_forward_governance_stays_closed_with_current_scale_sample():
    models=[{
        'model_version':'2.0.0','forward_n':13,'forward_days':2,
        'mean_excess_return':0.01,'forward_only':True,'matured_only':True,
        'backfilled':False,'cost_aware':True,'benchmark_aware':True,
    }]
    competition=compete_v2(models,current_champion_version='2.0.0')
    assert competition['status']=='INSUFFICIENT_EVIDENCE'
    assert competition['automatic_replacement'] is False
    assert competition['real_trading'] is False

    records=[{
        'matured':True,'backfilled':False,'created_at':'2026-09-08T17:00:00+00:00',
        'net_return':0.01,'excess_return':0.01,'benchmark_return':0.0,'cost':0.001,
    } for _ in range(13)]
    evidence=scorecard(records)
    assert evidence['status']=='INSUFFICIENT_EVIDENCE'
    assert evidence['performance_verified'] is False
    assert evidence['real_trading'] is False


def test_research_cannot_jump_directly_to_paper_or_live():
    stage=stage_funnel(
        research_gate='PASS_RESEARCH',shadow_forward_n=13,shadow_days=2,
        paper_forward_n=0,paper_days=0,degradation_clear=False,
    )
    assert stage['stage']=='SHADOW'
    assert stage['automatic_live_promotion'] is False
    assert stage['real_trading'] is False
