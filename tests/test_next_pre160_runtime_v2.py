from pathlib import Path
import math

import radar_pre160_runtime_v2 as rt
import radar_pre160_cloud_v2 as cloud


def _series(values):
    return [{'date':f'2026-09-{i+1:02d}','normalized_equity':v,'v_score':250+i,'v_confidence':.8,'v_components':{'evidence':85}} for i,v in enumerate(values)]


def test_competitor_benchmark_is_observed_vs_champion():
    challenger={'daily_equity_30d':_series([1000,1020,1040])}
    champion={'daily_equity_30d':_series([1000,1005,1010])}
    out=rt.competitor_vs_champion_benchmark(challenger,champion)
    assert out['status']=='AVAILABLE'
    assert out['observed_days']==3
    assert out['excess_return_pct']>2.9
    assert out['real_trading'] is False


def test_calibration_only_passes_with_mature_prospective_sample():
    rows=[{'realized_pnl':1,'payload':{'confidence':.9}} for _ in range(50)]
    out=rt.calibration_scorecard(rows,benchmark_coverage=1.0,cost_coverage=1.0)
    assert out['status']=='PASS'
    assert math.isclose(out['brier'],.01,rel_tol=1e-9)
    small=rt.calibration_scorecard(rows[:5],benchmark_coverage=1.0,cost_coverage=1.0)
    assert small['status']=='BLOCKED'
    assert 'INSUFFICIENT_MATURE_FORWARD' in small['blockers']


def test_enriched_promotion_fails_closed_without_stress_and_regimes():
    champion={'competitor_key':'champion','current_equity':1000,'v_score':240,'v_confidence':.8,'max_drawdown_pct':-2,
              'daily_equity_30d':_series([1000,1005,1010])}
    challenger={'competitor_key':'balanced','current_equity':1050,'v_score':300,'v_confidence':.85,'max_drawdown_pct':-3,
                'daily_equity_30d':_series([1000,1030,1050])}
    base=[{'competitor_key':'balanced','v_score':300,'v_confidence':.85,'v_components':{'evidence':90},
           'decision_metrics':{'anti_luck_score':90},'closed_decisions':[]}]
    forward=[{'matured':True,'backfilled':False,'return_pct':2,'net_return':1.8,'benchmark_return':1,'horizon':'1d'}]
    validation={'paper_gate_evidence':{'oos_pass':True,'benchmark_coverage':1.0,'cost_coverage':1.0},
                'market_telemetry':{'assets_observed':10,'assets_expected':10}}
    durable={'capture_started_at':'2026-09-11T00:00:00Z','decisions':[]}
    league={'champion_key':'champion','leaderboard':[champion,challenger],
            'best_promotion_watch':{'common_days':30,'persistence_score':90}}
    out=rt.enrich_scorecards(base,league,forward,validation,durable=durable)
    p=out['scorecards'][0]['promotion_v2']
    assert p['eligible'] is False
    assert 'CALIBRATION_NOT_MATURE' in p['evidence_blockers']
    assert 'STRESS_EXPOSURES_NOT_VERIFIED' in p['evidence_blockers']
    assert 'REGIME_GENERALIZATION_NOT_MATURE' in p['evidence_blockers']


def test_pre160_readiness_never_allows_setup_during_accumulation():
    runtime={'authority_status':'PRE160_EVALUATION_AUTHORITY','scorecards':[{'competitor_key':'champion'}],
             'evidence_maturity':{'capture_started_at':'2026-09-11T00:00:00+00:00','observed_runtime_days':0,'prospective_closed_decisions':0}}
    out=cloud.readiness_snapshot(runtime)
    assert out['setup_allowed'] is False
    assert out['candidate_version'] is None
    assert 'PROSPECTIVE_CLOSED_SAMPLE_SMALL' in out['blockers']
    assert out['real_trading'] is False


def test_edge_authority_preserves_payload_and_never_applies_archive_candidate():
    text=Path('supabase/functions/radar-pre160-evaluation/index.ts').read_text(encoding='utf-8')
    assert 'forward_eligible,payload' in text
    assert 'persist_archive_candidate' in text
    assert 'applied:false' in text
    migration=Path('supabase/migrations/20260911233000_pre160_archive_candidates.sql').read_text(encoding='utf-8')
    assert 'applied boolean not null default false check (applied = false)' in migration
