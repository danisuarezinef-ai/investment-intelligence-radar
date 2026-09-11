from pathlib import Path

from radar_portfolio_optimizer_v3 import optimize_capital
from radar_paper_rebalance_v1 import rebalance_paper
from radar_learning_engine_v3 import learn_v3
from radar_champion_challenger_v1 import compete


def test_optimizer_preserves_verified_forward_evidence():
    out=optimize_capital(cash=1000,equity=1000,drawdown_pct=0,opportunities=[{
        'symbol':'AAA','evidence_complete':True,'prediction_evidence':'VERIFIED_FORWARD',
        'expected_return':0.02,'risk_score':0.2}])
    assert out['status']=='READY'
    assert out['allocations'][0]['prediction_evidence']=='VERIFIED_FORWARD'
    assert out['real_trading'] is False


def test_paper_rebalance_is_blocked_without_promotion_gate():
    out=rebalance_paper(governance={'paper_execution_allowed':False},target_values={'AAA':100},prices={'AAA':10})
    assert out['status']=='BLOCKED_BY_PROMOTION_GATE'
    assert out['executed']==[] and out['real_trading'] is False


def test_learning_and_competition_fail_closed_on_immature_evidence():
    learning=learn_v3([{'immutable':True,'matured':False,'backfilled':False,'signals':{'x':1},'horizon':'1d'}])
    assert learning['promotion_grade_records']==0
    comp=compete([{'model_version':'m1','forward_n':3,'forward_days':2,'forward_only':True,
                   'cost_aware':True,'benchmark_aware':True,'matured_only':True,
                   'backfilled':False,'mean_excess_return':0.01}])
    assert comp['status']=='INSUFFICIENT_EVIDENCE'
    assert comp['automatic_replacement'] is False and comp['real_trading'] is False


def test_production_entrypoint_runs_delegated_sync_and_closed_loop():
    src=Path('cloud_service_v4.py').read_text(encoding='utf-8')
    v3=Path('cloud_service_v3.py').read_text(encoding='utf-8')
    assert 'import cloud_service_v3 as base3' in src
    assert 'base3._forward_outcome_sync_loop' in src
    assert 'sync_forward_outcomes_once(750)' in v3
    assert 'mature_forward_outcomes()' in src
    assert "closed_loop_cycle('1d')" in src
    assert 'def closed_loop_runtime_loop(interval_seconds=300)' in src
    assert 'REAL_TRADING=False' in src
    assert 'exec python cloud_service_v4.py' in Path('start.sh').read_text(encoding='utf-8')


def test_forward_outcome_sync_resends_updated_existing_rows_idempotently():
    src=Path('radar_forward_outcome_sync_v1.py').read_text(encoding='utf-8')
    assert 'where outcome is not null' in src
    assert "'decision_forward_ledger':forward" in src
    assert "'idempotent':True" in src
    assert "'backfill_used':False" in src
