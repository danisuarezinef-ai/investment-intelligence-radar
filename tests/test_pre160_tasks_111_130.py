from datetime import datetime,timezone,timedelta

from radar_pre160_runtime_v4 import (
    checkpoint_continuity,horizon_maturity_queue,calibration_uncertainty,
    paired_champion_challenger,sequential_superiority,readiness_countdown,
    persistent_degradation_state,turnover_cost_budget,
)
from radar_pre160_runtime_v4_linkage import regime_coverage_balance_safe


def _prospective(key='champion',symbol='MSFT',entry='2026-09-12T00:00:00+00:00',exit='2026-09-13T00:00:00+00:00',ret=1.0,fp='x'):
    return {'competitor_key':key,'decision_fingerprint':fp,'entry_ts':entry,'exit_ts':exit,'symbol':symbol,
            'realized_pnl':ret,'return_pct':ret,'entry_capital':100.0,'costs':0.1,
            'evidence_class':'PROSPECTIVE_PAPER_CLOSE','forward_eligible':True,'payload':{'horizon':'1d'},'real_trading':False}


def test_checkpoint_continuity_needs_two_points_and_detects_gap():
    one=[{'id':1,'observed_at':'2026-09-12T00:00:00+00:00','prev_hash':None,'record_hash':'a'}]
    assert checkpoint_continuity(one)['status']=='EVIDENCE_PENDING'
    two=one+[{'id':2,'observed_at':'2026-09-12T00:05:00+00:00','prev_hash':'a','record_hash':'b'}]
    assert checkpoint_continuity(two)['status']=='VERIFIED'
    gap=one+[{'id':2,'observed_at':'2026-09-12T00:30:01+00:00','prev_hash':'a','record_hash':'b'}]
    assert 'CHECKPOINT_CADENCE_GAPS' in checkpoint_continuity(gap)['blockers']


def test_horizon_queue_never_invents_missing_metadata():
    now=datetime(2026,9,12,tzinfo=timezone.utc)
    out=horizon_maturity_queue([{'symbol':'MSFT','matured':False,'backfilled':False}],now=now)
    assert out['unknown']==1
    assert 'MATURITY_METADATA_INCOMPLETE' in out['blockers']


def test_horizon_queue_marks_due_record_overdue_only_from_timestamp_and_horizon():
    now=datetime(2026,9,12,tzinfo=timezone.utc)
    out=horizon_maturity_queue([{'symbol':'MSFT','created_at':'2026-09-10T00:00:00+00:00','horizon':'1d','matured':False,'backfilled':False}],now=now)
    assert out['overdue']==1
    assert 'OVERDUE_FORWARD_OUTCOMES' in out['blockers']


def test_calibration_uncertainty_small_sample_stays_pending():
    rows=[]
    for i in range(10):
        r=_prospective(fp=str(i),ret=1 if i%2 else -1);r['confidence']=0.7;rows.append(r)
    out=calibration_uncertainty(rows)
    assert out['status']=='EVIDENCE_PENDING'
    assert out['overall_hit_rate_ci95'] is not None
    assert 'CALIBRATION_EFFECTIVE_SAMPLE_SMALL' in out['blockers']


def test_regime_linkage_uses_entry_fields_not_future_exit_fields():
    entry='2026-09-12T00:00:00+00:00'
    d=_prospective(entry=entry,exit='2026-09-20T00:00:00+00:00')
    env={'competitor_key':'champion','symbol':'MSFT','trade_ts':entry,'side':'BUY','regime':'mixed'}
    out=regime_coverage_balance_safe([d],[env],min_per_regime=1)
    assert out['counts']=={'mixed':1}
    assert out['uses_exit_fields_for_entry_linkage'] is False


def test_paired_comparison_requires_matched_symbol_day_horizon():
    c=_prospective('champion','MSFT',ret=1.0,fp='c')
    a=_prospective('aggressive','MSFT',ret=2.0,fp='a')
    b=_prospective('balanced','NVDA',ret=5.0,fp='b')
    out=paired_champion_challenger([c,a,b],min_pairs=1)
    assert out['pairs']==1
    assert out['comparisons'][0]['challenger']=='aggressive'
    assert out['comparisons'][0]['mean_delta_pct']==1.0


def test_sequential_superiority_is_watch_only():
    paired={'comparisons':[{'challenger':'aggressive','pairs':6,'mean_delta_pct':1.2,'win_rate':.67}]}
    out=sequential_superiority(paired)
    assert out['status']=='WATCH_READY'
    assert out['automatic_promotion'] is False


def test_persistent_degradation_never_auto_demotes():
    out=persistent_degradation_state({'status':'DEGRADED_WATCH','consecutive_degraded_days':3,'cooldown_active':True},now=datetime(2026,9,12,tzinfo=timezone.utc))
    assert out['status']=='COOLDOWN'
    assert out['automatic_demotion'] is False
    assert out['cooldown_until']=='2026-09-19'


def test_readiness_countdown_does_not_promise_date_without_mature_sample():
    gates={'champion':{'status':'EVIDENCE_PENDING'}}
    out=readiness_countdown('2026-09-11T00:00:00+00:00',gates,{'status':'BLOCKED_PRE160'},now=datetime(2026,9,12,tzinfo=timezone.utc))
    assert out['earliest_possible_review_at'] is None
    assert out['setup_allowed'] is False


def test_turnover_cost_budget_uses_only_prospective_records_and_is_watch_only():
    good=_prospective();old=dict(good);old['evidence_class']='DERIVED_PREEXISTING';old['forward_eligible']=False;old['costs']=999
    out=turnover_cost_budget([good,old])
    assert out['closed_decisions']==1
    assert out['costs']==0.1
    assert out['automatic_action'] is False
