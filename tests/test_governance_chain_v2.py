from radar_attribution_v2 import attribute_record, attribution_summary
from radar_learning_loop_v2 import learn_signal_value
from radar_degradation_engine_v2 import degradation_assessment
from radar_global_opportunity_rank_v1 import rank_global_opportunities
from radar_shadow_to_paper_gate_v1 import shadow_to_paper_gate


def test_attribution_requires_benchmark_and_costs():
    assert attribute_record({'return_pct':5})['attributable'] is False
    r=attribute_record({'return_pct':5,'benchmark_return_pct':2,'costs_pct':1})
    assert r['attributable'] is True and r['net_return_pct']==4 and r['selection_excess_pct']==2
    s=attribution_summary([{'return_pct':5,'benchmark_return_pct':2,'costs_pct':1}])
    assert s['performance_verified'] is False and s['real_trading'] is False


def test_learning_uses_only_matured_immutable_non_backfilled():
    rows=[{'immutable':True,'matured':True,'backfilled':False,'return_pct':10,'signals':{'mom':1},'regime':'R','horizon':'1m'} for _ in range(20)]
    rows.append({'immutable':True,'matured':False,'backfilled':False,'return_pct':99,'signals':{'mom':1}})
    out=learn_signal_value(rows,min_samples=20)
    assert out['rejected_records']==1 and out['groups'][0]['status']=='EVIDENCE_AVAILABLE'
    assert out['automatic_application'] is False


def test_degradation_fail_closed_on_insufficient_evidence_and_detects_drop():
    a=degradation_assessment({'samples':10},{'samples':10})
    assert a['status']=='INSUFFICIENT_EVIDENCE' and a['recommended_multiplier']==0.5
    b=degradation_assessment({'samples':40,'hit_rate':.65,'excess_return_pct':5,'brier':.15},{'samples':40,'hit_rate':.50,'excess_return_pct':0,'brier':.25})
    assert b['degraded'] is True and len(b['reasons'])==3


def test_global_rank_rejects_incomplete_risk_metadata():
    cards=[{'symbol':'A','horizon':'1m','action':'BUY','evidence_complete':True,'expected_return_pct':15,'downside_pct':-2,'confidence':.8,'valuation_risk':1},
           {'symbol':'B','horizon':'1m','action':'BUY','evidence_complete':True,'expected_return_pct':10,'downside_pct':-1,'confidence':.7,'valuation_risk':1}]
    meta={'A':{'sector':'tech','geography':'US','fx':'USD','liquidity_score':1}}
    out=rank_global_opportunities(cards,meta)
    assert out['ranked'][0]['symbol']=='A' and out['ranked'][0]['global_rank']==1
    assert out['rejected'][0]['symbol']=='B' and out['can_trade'] is False


def test_shadow_to_paper_gate_never_auto_promotes():
    evidence={'forward_days':100,'decisions':50,'marks':120,'max_drawdown_pct':-5,'benchmark_coverage':1,'cost_coverage':1,'positive_months':4,'oos_pass':True,'degradation_clear':True}
    out=shadow_to_paper_gate(evidence)
    assert out['ready_for_paper_review'] is True and out['auto_promote'] is False and out['paper_trading_enabled'] is False and out['real_trading'] is False
    bad=shadow_to_paper_gate({})
    assert bad['ready_for_paper_review'] is False
