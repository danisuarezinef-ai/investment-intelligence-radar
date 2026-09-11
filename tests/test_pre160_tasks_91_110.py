from datetime import datetime, timezone, timedelta
from pathlib import Path

import radar_pre160_runtime_v3 as v3


def _decision(i, competitor='balanced', confidence=.8, pnl=1.0):
    day=(datetime(2026,9,1,tzinfo=timezone.utc)+timedelta(days=i)).isoformat()
    return {'competitor_key':competitor,'decision_fingerprint':f'f{i}','entry_ts':day,'exit_ts':day,'symbol':f'S{i%6}',
            'realized_pnl':pnl,'return_pct':1.0 if pnl>0 else -1.0,'costs':.01,'entry_capital':100.,
            'evidence_class':'PROSPECTIVE_PAPER_CLOSE','forward_eligible':True,'payload':{'confidence':confidence,'horizon':'1d'}}


def test_94_sample_gate_requires_time_size_and_diversity():
    rows=[_decision(i) for i in range(30)]
    out=v3.sample_gate(rows)
    assert out['status']=='MATURE'
    assert out['closes']==30 and out['days']>=14 and out['symbols']>=5
    small=v3.sample_gate(rows[:4])
    assert small['status']=='EVIDENCE_PENDING'
    assert 'MIN_PROSPECTIVE_CLOSES_NOT_MET' in small['blockers']


def test_95_calibration_bins_and_drift_fail_closed_then_mature():
    rows=[_decision(i,confidence=.9,pnl=1 if i%5 else -1) for i in range(45)]
    out=v3.calibration_bins_and_drift(rows)
    assert out['n']==45 and len(out['bins'])==5
    assert out['brier'] is not None and out['brier_drift'] is not None
    assert v3.calibration_bins_and_drift(rows[:5])['status']=='EVIDENCE_PENDING'


def test_96_multi_benchmark_needs_primary_coverage():
    good=[{'matured':True,'backfilled':False,'net_return':2.0,'benchmark_return':1.0} for _ in range(10)]
    out=v3.multi_benchmark_attribution(good)
    assert out['status']=='AVAILABLE'
    assert out['benchmarks']['primary']['mean_excess_return']==1.0
    bad=[{'matured':True,'backfilled':False,'net_return':2.0}]
    assert 'PRIMARY_BENCHMARK_COVERAGE_LOW' in v3.multi_benchmark_attribution(bad)['blockers']


def test_97_cost_ladder_monotonically_penalizes_returns():
    out=v3.cost_slippage_ladder([_decision(i) for i in range(3)])
    vals=[x['mean_return_pct'] for x in out['scenarios']]
    assert vals==sorted(vals,reverse=True)
    assert out['scenarios'][-1]['extra_cost_bps']==50


def test_98_capital_efficiency_uses_observed_closed_capital():
    out=v3.capital_efficiency([_decision(1,pnl=5),_decision(2,pnl=-2)])
    assert out['capital_deployed']==200
    assert out['realized_pnl']==3
    assert round(out['realized_return_on_deployed_pct'],3)==1.5


def test_99_100_missing_pit_regime_or_horizon_blocks_matrix():
    rows=[_decision(1)]
    out=v3.regime_horizon_matrix(rows,[])
    assert 'PIT_REGIME_CONTEXT_INCOMPLETE' in out['blockers']
    assert 'NO_MATURE_REGIME_HORIZON_CELL' in out['blockers']


def test_101_stress_never_invents_exposures():
    assert v3.stress_readiness([])['status']=='EVIDENCE_PENDING'
    out=v3.stress_readiness([{'stress_scenario':'high_vol'}])
    assert out['observed_exposures']==1 and out['synthetic_stress_claim'] is False


def test_102_anti_overfit_does_not_use_test_or_live_for_selection():
    validation={'historical_lab':{'mean_gain':.01,'vault_gain':.009,'test_gain':.008}}
    forward=[{'matured':True,'backfilled':False,'excess_return':.007} for _ in range(10)]
    out=v3.anti_overfitting_v2(validation,forward)
    assert out['score'] is not None
    assert out['selection_uses_final_test'] is False
    assert out['selection_uses_live_forward'] is False


def test_103_transfer_never_auto_replaces_champion():
    cards=[{'competitor_key':'champion'},{'competitor_key':'balanced','competitor_benchmark':{'excess_return_pct':2},'promotion_v2':{'readiness':80}}]
    out=v3.champion_challenger_transfer(cards)
    assert out['comparisons'][0]['transfer_score'] is not None
    assert out['automatic_replacement'] is False


def test_104_degradation_is_watch_only_with_cooldown():
    rows=[{'competitor_key':'champion','day':f'2026-09-{d:02d}','v_score':100,'data_quality_score':50} for d in range(1,5)]
    out=v3.sequential_degradation_watch(rows)
    assert out['status']=='DEGRADED_WATCH' and out['cooldown_active'] is True
    assert out['automatic_demotion'] is False


def test_105_provenance_requires_every_required_field():
    good=v3.provenance_completeness([_decision(1)])
    assert good['status']=='COMPLETE' and good['score']==100
    bad=_decision(2);bad['return_pct']=None
    assert 'PROVENANCE_FIELDS_INCOMPLETE' in v3.provenance_completeness([bad])['blockers']


def test_107_freshness_blocks_stale_or_missing_daily_evaluation():
    now=datetime(2026,9,11,22,0,tzinfo=timezone.utc)
    out=v3.freshness_sla(capture_started_at=now.isoformat(),daily_rows=[],decisions=[],contexts=[],now=now)
    assert out['status']=='DEGRADED' and 'evaluation_daily' in out['blocking']


def test_108_readiness_16_never_allows_setup_automatically():
    pending={'status':'EVIDENCE_PENDING'}
    out=v3.readiness_16(sample_gates={},calibration=pending,benchmarks=pending,costs=pending,regime_matrix={'blockers':['x']},stress=pending,
                         anti_overfit={'score':None},provenance=pending,freshness={'status':'DEGRADED'},observed_runtime_days=0)
    assert out['status']=='BLOCKED_PRE160'
    assert out['setup_allowed'] is False and out['automatic_release'] is False and out['real_trading'] is False


def test_106_edge_chain_is_append_only_and_server_hashed():
    text=Path('supabase/functions/radar-pre160-evidence/index.ts').read_text(encoding='utf-8')
    assert 'appendProspectiveChain' in text
    assert '.insert({origin_node:node,decision_fingerprint:fp' in text
    assert 'prev_hash' in text and 'record_hash' in text
    assert 'chain_integrity:valid?"VERIFIED":"FAILED"' in text
    assert 'real_trading:false' in text


def test_93_109_durable_daily_and_pit_tables_are_private():
    sql=Path('supabase/migrations/20260911234500_pre160_evidence_v3.sql').read_text(encoding='utf-8')
    for table in ('radar_pre160_evidence_daily','radar_pre160_decision_contexts','radar_pre160_evidence_chain'):
        assert f'alter table public.{table} enable row level security' in sql
    assert 'revoke all on public.radar_pre160_evidence_daily from anon, authenticated' in sql
    assert 'check (real_trading = false)' in sql


def test_110_cloud_v4_exposes_audit_and_evidence_endpoints_without_setup():
    text=Path('cloud_service_v4.py').read_text(encoding='utf-8')
    for endpoint in ('/pre160-evidence-v1','/pre160-readiness-v2','/pre160-evidence-authority-v1','/pre160-audit-v1'):
        assert endpoint in text
    assert 'pre160_evidence_loop' in text
    assert 'REAL_TRADING=False' in text
    assert Path('version.json').read_text(encoding='utf-8').find('1.5.28')>=0
