from radar_experiment_brain_v1 import generate_experiments
from radar_experiment_memory_v2 import diversity_filter,stage_funnel
from radar_simulation_research_v3 import walk_forward,stress_suite,overfit_gate


def _days(n=120):
    out=[]
    for i in range(n):
        out.append((f'2026-01-{(i%28)+1:02d}',{'AAA':100+i*.3,'BBB':90+i*.1,'CCC':110-i*.05}))
    return out


def test_walk_forward_has_no_lookahead_and_never_real_trading():
    cfg=generate_experiments(1)[0]['configuration']
    r=walk_forward(cfg,_days())
    assert r['completed'] is True and r['lookahead'] is False and r['real_trading'] is False
    assert r['evidence_class']=='SIMULATED_WALK_FORWARD_ONLY'


def test_stress_and_overfit_gate_cannot_promote_to_paper():
    cfg=generate_experiments(1)[0]['configuration']
    w=walk_forward(cfg,_days());s=stress_suite(cfg,_days());g=overfit_gate(w,s)
    assert g['can_promote_to_paper'] is False and g['real_trading'] is False
    assert g['eligible_next_stage'] in ('SHADOW_REVIEW','GRAVEYARD')


def test_stage_funnel_is_gradual_and_never_live():
    a=stage_funnel(research_gate='PASS_RESEARCH',shadow_forward_n=0,shadow_days=0)
    b=stage_funnel(research_gate='PASS_RESEARCH',shadow_forward_n=25,shadow_days=8,paper_forward_n=0,paper_days=0)
    c=stage_funnel(research_gate='PASS_RESEARCH',shadow_forward_n=25,shadow_days=8,paper_forward_n=50,paper_days=20,degradation_clear=True)
    assert a['stage']=='SHADOW' and b['stage']=='PAPER_REVIEW' and c['stage']=='PAPER_MATURE'
    assert all(x['automatic_live_promotion'] is False and x['real_trading'] is False for x in (a,b,c))


def test_diversity_filter_limits_near_duplicates(monkeypatch):
    monkeypatch.setattr('radar_experiment_memory_v2.seen',lambda cfg:{'seen':False})
    xs=generate_experiments(2)
    ys=diversity_filter(xs,max_same_family=1)
    assert 0 < len(ys) <= len(xs)
    assert all(x['real_trading'] is False for x in ys)
