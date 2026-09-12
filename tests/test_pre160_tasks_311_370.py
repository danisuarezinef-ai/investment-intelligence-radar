import math

import cloud_service_v9 as v9
from radar_forward_evidence_v2 import deduplicate,effective_sample_size_v2,horizon_maturity,asset_independence
from radar_brain_calibration_v2 import calibration_engine_v2,confidence_decomposition,abstention_decision_v3,alpha_summary
from radar_brain_competition_v3 import champion_challenger_v3,shadow_ensemble_v2,sequential_dynamic_routing
from radar_brain_readiness_v1 import build_tasks_311_370
from radar_pre160_production_proof_v1 import PROTECTED_PATHS


def row(i=1,*,model='m1',horizon='1d',decision='BUY',hit=True,excess=.01,cluster=None,matured=True,quality=1.0,day=1):
    raw=.02 if hit else -.02
    return {
      'prediction_id':f'p{i}','evidence_key':f'h{i}','prediction_hash':f'h{i}',
      'symbol':f'S{i%12}','horizon':horizon,'model_version':model,
      'created_at':f'2026-01-{day:02d}T10:00:00+00:00','evaluated_at':f'2026-01-{min(day+1,28):02d}T10:00:00+00:00',
      'matured':matured,'natural':True,'decision_state':decision,'action_hit':hit,
      'confidence':.7,'quality':quality,'quality_checks':{'pit_valid':True,'natural':True,'immutable_identity':True,'benchmark_complete':True,'cost_complete':True},
      'independence_cluster':cluster or f'c{i}','regime':'risk_on' if i%2 else 'risk_off','sector':'tech' if i%3 else 'health',
      'market':'US' if i%2 else 'EU','family':model,'raw_return':raw,'net_return':raw-.001,
      'excess_return':excess if hit else -abs(excess),'benchmark_return':.001,'cost':.001,
      'payload':{'score':10 if hit else -5,'features':{'source_quality':.8,'volatility':.4},'uncertainty':{'regime':'risk_on'}},
      'provenance':{'lookahead':False},'outcome':{'backfilled':False,'return':raw,'net_return':raw-.001,'excess_return':excess if hit else -abs(excess),'benchmark_return':.001,'benchmark_evidence':'PIT','cost':.001,'cost_model':'PAPER'},
    }


def test_dedup_prevents_double_count_and_detects_mutation():
    a=row(1);b=dict(a)
    out=deduplicate([a,b])
    assert out['input_n']==2 and out['unique_n']==1 and out['duplicates']==['h1']
    bad=dict(a);bad['symbol']='OTHER'
    out=deduplicate([a,bad])
    assert out['collisions']


def test_ess_penalizes_shared_cohorts():
    rows=[row(i,cluster='same') for i in range(1,41)]
    ess=effective_sample_size_v2(rows)
    assert ess['n']==40 and ess['cluster_ess']==1.0 and ess['conservative_ess']==1.0


def test_horizons_mature_independently():
    rows=[]
    for i in range(48):rows.append(row(i+1,horizon='1d',day=1+(i%4)))
    out=horizon_maturity(rows)
    assert out['1d']['status']=='PASS'
    assert out['1w']['status']=='PENDING_SAMPLE'
    assert out['1m']['status']=='PENDING_SAMPLE'
    assert out['3m']['status']=='PENDING_SAMPLE'


def test_asset_independence_requires_breadth():
    broad=[row(i) for i in range(1,49)]
    assert asset_independence(broad)['status']=='PASS'
    narrow=[]
    for i in range(30):
        x=row(i+1);x['symbol']='ONE';narrow.append(x)
    assert asset_independence(narrow)['status']=='PENDING_SAMPLE'


def test_calibration_v2_reports_brier_and_logloss_without_backfill():
    rows=[row(i+1,hit=(i%3!=0)) for i in range(60)]
    out=calibration_engine_v2(rows)
    assert out['status']=='PASS' and out['n']==60
    assert 0 <= out['brier'] <= 1 and out['log_loss']>0 and out['real_trading'] is False


def test_confidence_ceiling_is_fail_closed():
    x=row(1,quality=.4);x['confidence']=.99;x['regime']=None;x['payload']['features'].pop('source_quality',None)
    out=confidence_decomposition(x)
    assert out['adjusted_confidence']<=out['confidence_ceiling']<=.70
    assert out['empirically_calibrated_decomposition'] is False


def test_abstention_is_first_class_paper_only():
    x=row(1,quality=.2);x['confidence']=.55
    out=abstention_decision_v3(x)
    assert out['abstain'] is True and out['decision']=='NO_INVERTIR / ESPERAR'
    assert out['paper_only'] is True and out['real_trading'] is False


def test_alpha_requires_natural_forward_sample():
    rows=[row(i+1) for i in range(35)]
    out=alpha_summary(rows)
    assert out['status']=='PASS' and out['cost_complete'] and out['benchmark_complete']
    assert out['interval_excess']['low'] is not None


def test_champion_challenger_requires_two_incubated_models():
    one=[row(i+1,model='m1',day=1+(i%20)) for i in range(50)]
    assert champion_challenger_v3(one)['status']=='PENDING_SAMPLE'
    two=one+[row(100+i,model='m2',day=1+(i%20),excess=.02) for i in range(50)]
    out=champion_challenger_v3(two)
    assert out['status']=='READY_FOR_MANUAL_COMPARISON'
    assert out['automatic_replacement'] is False and out['promotion_scope']=='SHADOW_PAPER_ONLY'


def test_shadow_ensemble_never_applies_weights_automatically():
    rows=[]
    for i in range(50):
        rows.append(row(i+1,model='m1',day=1+(i%20),excess=.01))
        rows.append(row(100+i,model='m2',day=1+(i%20),excess=.01 if i%2 else -.01))
    out=shadow_ensemble_v2(rows)
    assert out['weights_applied_automatically'] is False and out['scope']=='SHADOW_ONLY'


def test_dynamic_routing_declares_no_future_outcomes():
    rows=[]
    for i in range(60):
        rows.append(row(i+1,model='m1',day=1+(i%20)))
        rows.append(row(100+i,model='m2',day=1+(i%20),excess=.02))
    out=sequential_dynamic_routing(rows,min_history=2)
    assert out['uses_future_outcomes'] is False and out['lookahead_violations']==[]


def test_brain_gate_remains_not_ready_without_natural_transaction_envelope():
    technical={
      'operational_health':{'investment_score_included':False,'affects_investment_ranking':False,'affects_model_promotion':False},
      'worker_utilization':{'not_instrumented_is_not_zero':True},
      'queue':{},'provider':{},'partition':{},'deep_151_200':{'deep_ready':True},'deep_201_270':{'deep_ready':True},
      'proof':{'verified':False},'protected_digest':{'digest':'a'*64,'missing':[],'files':80},
    }
    evidence={'decision_envelope':{'count':0,'natural_envelope':False,'provenance_complete':False,'entry_linked_without_reconstruction':False,'prospective_close':False,'task_150_eligible':False},
              'canonical_key':'prediction_hash','rows_total':1,'rows_matured_natural':0,
              'deduplication':{'input_n':1,'unique_n':1,'duplicates':[],'collisions':[]},
              'ess':{'clusters':0,'conservative_ess':0},'mean_evidence_quality':None,
              'horizons':{h:{'status':'PENDING_SAMPLE'} for h in ('1d','1w','1m','3m')},
              'regimes':{'status':'PENDING_SAMPLE'},'sectors':{'status':'PENDING_SAMPLE'},'markets':{'status':'PENDING_SAMPLE'},'assets':{'status':'PENDING_SAMPLE'}}
    analytics={'calibration':{'status':'PENDING_SAMPLE','n':0},'drift':{'status':'PENDING_SAMPLE'},'abstention_quality':{'status':'PENDING_SAMPLE'},
               'alpha':{'status':'PENDING_SAMPLE','interval_excess':{},'downside_excess':{}},'decay':{'status':'PENDING_SAMPLE'},
               'failure_attribution':{'status':'PENDING_SAMPLE'},'alpha_attribution':{'causal_attribution_verified':False},'ranking_369':{'status':'PENDING_SAMPLE'}}
    competition={'champion_challenger':{'status':'PENDING_SAMPLE','models':[]},'champion_degradation':{'status':'PENDING_SAMPLE'},
                 'shadow_ensemble':{'status':'PENDING_SAMPLE','correlations':{}},'diversity_reward':{'status':'PENDING_SAMPLE'},
                 'dynamic_routing':{'status':'PENDING_SAMPLE'},'meta_learning':{'status':'PENDING_SAMPLE'},'historical_live_transfer':{'status':'PENDING_SAMPLE'}}
    out=build_tasks_311_370(technical=technical,evidence=evidence,analytics=analytics,competition=competition,rows=[],persistence={},external={})
    assert set(out['tasks'])=={str(i) for i in range(311,371)}
    assert out['tasks']['330']['state']=='PENDING_SAMPLE'
    assert out['tasks']['370']['state']=='PASS' and out['brain_readiness_gate']['status']=='NOT_READY'
    assert out['real_trading'] is False and out['setup_allowed'] is False


def test_v9_cold_surface_fails_closed():
    out=v9._warming_tasks()
    assert out['source_ready'] is False and out['brain_readiness_gate']['status']=='NOT_READY'
    assert all(x['state']=='NOT_VERIFIED' for x in out['tasks'].values())
    assert out['real_trading'] is False


def test_v9_and_brain_files_are_protected():
    required={'cloud_service_v9.py','radar_forward_evidence_v2.py','radar_brain_calibration_v2.py','radar_brain_competition_v3.py','radar_brain_readiness_v1.py','radar_brain_persistence_v1.py','supabase/functions/radar-brain-evidence/index.ts'}
    assert required.issubset(set(PROTECTED_PATHS))
