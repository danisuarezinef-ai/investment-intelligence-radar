"""Refinement layer for tasks 121-130.
Legacy/non-prospective feature rows are excluded from Task 122 authority rather than treated as failures.
Any row claiming prospective capture but violating immutability, timing, or no-backfill fails closed.
"""
from __future__ import annotations
import radar_learning_governance_121_130_v1 as v1
REAL_TRADING=False
MIN_PROSPECTIVE_FEATURE_SNAPSHOTS=20

def feature_snapshot_authority(feature_snapshots):
    inspected=[];eligible=[];invalid_claims=[];legacy=0
    for s in feature_snapshots or []:
        if s.get('prospective_capture') is not True:
            legacy+=1;continue
        features=s.get('features') if isinstance(s.get('features'),dict) else {}
        captured=v1._dt(s.get('captured_at'));cutoff=v1._dt(s.get('data_cutoff'))
        temporal_ok=bool(captured and cutoff and cutoff<=captured)
        ok=bool(s.get('prediction_id') and captured and cutoff and s.get('feature_fingerprint') and features and
                s.get('immutable') is True and temporal_ok and s.get('lookahead') is not True and
                s.get('backfilled') is not True and s.get('retroactive_fill') is not True)
        item={'prediction_id':s.get('prediction_id'),'valid':ok,'feature_count':len(features),
              'temporal_ok':temporal_ok,'source':s.get('source')}
        inspected.append(item);eligible.append(s)
        if not ok:invalid_claims.append(item)
    valid=len(eligible)-len(invalid_claims)
    if invalid_claims:status='FAIL_CLOSED'
    elif valid>=MIN_PROSPECTIVE_FEATURE_SNAPSHOTS:status='PASS'
    elif valid:status='PENDING_SAMPLE'
    else:status='PENDING_DATA'
    return {'status':status,'n_input':len(feature_snapshots or []),'prospective_n':len(eligible),'valid_n':valid,
            'invalid_prospective_claims':invalid_claims[:30],'legacy_or_nonprospective_excluded_n':legacy,
            'minimum_prospective_n':MIN_PROSPECTIVE_FEATURE_SNAPSHOTS,'snapshots':inspected[:30],
            'full_feature_vector_required':True,'prospective_capture_required':True,'temporal_alignment_required':True,
            'legacy_rows_do_not_create_authority':True,'reconstruction_allowed':False,'backfill_allowed':False,'real_trading':False}

def causal_attribution_v2(rows,feature_snapshots):
    authority=feature_snapshot_authority(feature_snapshots)
    if authority['status']!='PASS':
        return {'status':'PENDING_DATA','reason':'FEATURE_SNAPSHOT_AUTHORITY_NOT_VERIFIED','feature_authority':authority,
                'causal_claim':False,'real_trading':False}
    eligible=[s for s in feature_snapshots or [] if s.get('prospective_capture') is True and s.get('immutable') is True and s.get('backfilled') is not True]
    return v1.causal_attribution_v2(rows,eligible)

def board(rows,feature_snapshots=None,candidates=None,risk=None,governor_inputs=None,task_states=None,critical_runtime=None,valid_forward_hours=None):
    vals=[v1.decision_journal_completeness(rows),feature_snapshot_authority(feature_snapshots),causal_attribution_v2(rows,feature_snapshots),
          v1.multi_horizon_outcome_evaluator(rows),v1.forward_tournament(rows),v1.automatic_demotion_safety(rows),v1.regime_specialist_evolution(rows),
          v1.portfolio_construction_v2(candidates or [],risk),v1.autonomous_learning_governor(governor_inputs),
          v1.master_paper_control_gate(task_states or {},critical_runtime,valid_forward_hours)]
    return {'status':'TASKS_121_130_EVALUATED','tasks':{str(121+i):{'state':x.get('status'),'evidence':x} for i,x in enumerate(vals)},
            'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,
            'live_execution_allowed':False,'real_trading':False}

master_paper_control_gate=v1.master_paper_control_gate
portfolio_construction_v2=v1.portfolio_construction_v2
autonomous_learning_governor=v1.autonomous_learning_governor
multi_horizon_outcome_evaluator=v1.multi_horizon_outcome_evaluator
automatic_demotion_safety=v1.automatic_demotion_safety
