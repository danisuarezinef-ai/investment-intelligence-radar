from datetime import datetime, timedelta, timezone

from radar_evidence_scorecard_v1 import scorecard
from radar_champion_challenger_v1 import derive_forward_model_metrics, compete
from radar_priority_runtime_v1 import priority_snapshot


def _records(model, n, excess):
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    out=[]
    for i in range(n):
        created=start+timedelta(days=i%14)
        out.append({'model_version':model,'created_at':created.isoformat(),'matured':True,'backfilled':False,
                    'net_return':0.01,'excess_return':excess,'benchmark_return':0.002,'cost':0.001})
    return out


def test_scorecard_requires_sample_days_benchmark_and_cost():
    sc=scorecard(_records('m1',30,0.004))
    assert sc['status']=='VERIFIED_FORWARD_SAMPLE'
    assert sc['forward_days']>=14
    assert sc['benchmark_coverage']==1.0
    assert sc['cost_coverage']==1.0
    assert sc['backfill_used'] is False
    assert sc['real_trading'] is False


def test_champion_challenger_is_derived_only_from_mature_forward_evidence():
    records=_records('champ',40,0.02)+_records('chall',40,0.005)
    models=derive_forward_model_metrics(records)
    result=compete(models)
    assert result['status']=='READY'
    assert result['champion']['model_version']=='champ'
    assert result['automatic_replacement'] is False
    assert result['promotion_scope']=='SHADOW_PAPER_ONLY'
    assert result['real_trading'] is False


def test_priority_runtime_integrates_6_to_10_and_never_enables_live_execution():
    records=_records('champ',40,0.02)+_records('chall',40,0.005)
    payload=priority_snapshot(account={'equity':1000,'cash':500,'invested':500},decision=None,opportunities=[],
        forward_records=records,models=[],endpoint_status={},freshness={},promotion_metrics={
            'max_drawdown':-0.02,'positive_months':4,'degradation_clear':True})
    assert payload['scorecard']['performance_verified'] is True
    assert payload['model_competition']['status']=='READY'
    assert payload['ui']['model_competition']['champion']['model_version']=='champ'
    assert payload['promotion']['review_only'] is True
    assert payload['promotion']['live_execution_allowed'] is False
    assert payload['promotion']['auto_promote'] is False
    assert payload['can_trade'] is False
    assert payload['real_trading'] is False
