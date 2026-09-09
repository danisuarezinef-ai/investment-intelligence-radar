from radar_evidence_scheduler_v2 import schedule_due
from radar_paper_risk_budget_v2 import assess_risk
from radar_decision_explainability_v2 import explain_decision
from radar_alert_prioritization_v2 import prioritise
from radar_recovery_orchestrator_v1 import recovery_plan


def test_scheduler_prioritises_short_horizons_and_rejects_backfill():
    rows=[
      {'horizon':'1w','target_at':'2026-09-01T00:00:00+00:00','outcome_status':'PENDING'},
      {'horizon':'1d','target_at':'2026-09-02T00:00:00+00:00','outcome_status':'PENDING'},
      {'horizon':'1d','target_at':'2026-09-01T00:00:00+00:00','outcome_status':'PENDING','backfilled':True},
    ]
    out=schedule_due(rows,now='2026-09-09T00:00:00+00:00')
    assert out['due_count']==2
    assert out['due'][0]['horizon']=='1d'
    assert any(x['scheduler_state']=='REJECTED_BACKFILL' for x in out['waiting'])
    assert out['real_trading'] is False


def test_paper_risk_budget_blocks_concentration():
    out=assess_risk(equity=1000,cash=700,positions=[{'market_value':300}],drawdown_pct=-0.02)
    assert out['status']=='BLOCKED'
    assert out['checks']['single_position'] is False
    assert out['real_trading'] is False


def test_explainability_requires_model_and_provenance():
    incomplete=explain_decision({'symbol':'MSFT','action':'HOLD'})
    assert incomplete['status']=='INCOMPLETE_EXPLANATION'
    complete=explain_decision({'symbol':'MSFT','action':'BUY','model_version':'v1','evidence':[{'source':'market','signal':'quality','confidence':0.8}]})
    assert complete['status']=='EXPLAINED'
    assert complete['evidence_count']==1


def test_alerts_deduplicate_and_critical_causes_hold():
    out=prioritise([
      {'key':'market','severity':'LOW','message':'stale'},
      {'key':'market','severity':'CRITICAL','message':'stale'},
    ])
    assert out['total_unique']==1
    assert out['critical']==1
    assert out['operational_hold'] is True


def test_recovery_orchestrator_fails_closed():
    bad=recovery_plan(cloud_fresh=False,duplicate_risk=True)
    assert bad['state']=='DEGRADED_HOLD'
    assert bad['can_execute_new_paper'] is False
    assert bad['real_trading'] is False
    good=recovery_plan()
    assert good['state']=='READY'
    assert good['can_execute_new_paper'] is True
    assert good['real_trading'] is False
