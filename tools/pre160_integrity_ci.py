"""Static backend integrity gate for the complete pre-1.6 runtime chain.

The gate intentionally overlaps version-specific integrity audits.  It verifies that
adding a new cloud layer does not bypass older evidence, provenance or safety controls.
"""
from pathlib import Path
import json


def _text(root,path):
    p=root/path
    return p.read_text(encoding='utf-8-sig') if p.exists() else ''


def _tokens(findings,root,path,tokens,prefix):
    text=_text(root,path)
    if not text:findings.append('MISSING:'+path);return
    for token in tokens:
        if token not in text:findings.append(prefix+':'+path+':'+token)


def audit(root='.'):
    root=Path(root);findings=[]
    start=_text(root,'start.sh')
    layers={n:_text(root,f'cloud_service_v{n}.py') for n in range(3,10)}
    if 'cloud_service_v9.py' not in start:findings.append('START_NOT_V9')
    chain=((9,'import cloud_service_v8 as base8','base8.start_runtime()'),
           (8,'import cloud_service_v7 as base7','base7.start_runtime()'),
           (7,'import cloud_service_v6 as base6','base6.start_runtime()'),
           (6,'import cloud_service_v5 as base5','base5.start_runtime()'),
           (5,'import cloud_service_v4 as base4','base4.start_v3_runtime()'),
           (4,'import cloud_service_v3 as base3',None))
    for n,imp,start_token in chain:
        text=layers[n]
        if not text:findings.append(f'MISSING_CLOUD_V{n}');continue
        if imp not in text:findings.append(f'V{n}_CHAIN_IMPORT_INVALID')
        if start_token and start_token not in text:findings.append(f'V{n}_CHAIN_START_INVALID')
    if 'import cloud_service as base' in layers[4]:findings.append('V4_LEGACY_BASE_IMPORT')

    required=(
      'radar_pre160_runtime_v3.py','radar_pre160_cloud_v3.py','radar_pre160_evidence_persistence_v1.py','PRE160_TASKS_91_110.md','supabase/functions/radar-pre160-evidence/index.ts',
      'radar_pre160_runtime_v4.py','radar_pre160_runtime_v4_linkage.py','radar_pre160_cloud_v4.py','radar_pre160_hardening_persistence_v1.py','PRE160_TASKS_111_130.md','supabase/functions/radar-pre160-hardening/index.ts','supabase/migrations/20260912003000_pre160_evidence_v4.sql',
      'radar_decision_provenance_v1.py','radar_pre160_runtime_v5.py','PRE160_TASKS_131_150.md','tests/test_decision_provenance_v1.py',
      'radar_supabase_sync.py','radar_learning_sync.py','tests/test_supabase_sync_resilience.py','tests/test_learning_sync_resilience_v1.py','tests/test_post150_reliability_v1.py',
      'PRE160_TASKS_151_200.md','radar_pre160_controls_v6.py','radar_pre160_recovery_v2.py','radar_pre160_release_authority_v2.py','tests/test_pre160_tasks_151_200.py','tests/test_pre160_recovery_release_v2.py',
      'cloud_service_v7.py','cloud_service_v8.py','radar_supabase_sync_partitioned_v2.py','tests/test_pre160_runtime_closure_v8.py',
      'cloud_service_v9.py','radar_forward_evidence_v2.py','radar_brain_calibration_v2.py','radar_brain_competition_v3.py','radar_brain_readiness_v1.py','radar_brain_persistence_v1.py','PRE160_TASKS_311_370.md')
    for path in required:
        if not (root/path).exists():findings.append('MISSING_COMPONENT:'+path)

    endpoint_sets={
      9:('/pre160-forward-evidence-v2','/pre160-calibration-v2','/pre160-brain-competition-v3','/pre160-brain-readiness-v1','/pre160-audit-311-370-v1'),
      8:('/pre160-audit-151-200-v1','/supabase-health-v1','/pre160-sync-partitions-v2','/pre160-operational-health-v2','/pre160-audit-271-310-v1'),
      7:('/pre160-audit-201-270-v1','/pre160-statistical-validity-v7','/pre160-autonomy-v7','/pre160-deployment-v7'),
      6:('/pre160-audit-151-200-v1','/pre160-recovery-v2','/pre160-release-authority-v2'),
      5:('/supabase-health-v1','/pre160-readiness-board-v1','/decision-provenance-v1'),
      4:('/pre160-evidence-v1','/pre160-hardening-v1','/pre160-audit-131-150-v1'),
      3:('/pre160-evaluation-v1','/simulator-league-v1','/persistent-authority-v1'),
    }
    for n,endpoints in endpoint_sets.items():
        for endpoint in endpoints:
            # An endpoint inherited by a later layer is allowed to live in an earlier
            # layer. Search the composed chain up to that version.
            if not any(endpoint in layers[k] for k in range(3,n+1)):findings.append(f'MISSING_ENDPOINT_V{n}:'+endpoint)

    _tokens(findings,root,'supabase/functions/radar-pre160-evidence/index.ts',('appendProspectiveChain','PIT_REGIME_NOT_CAPTURED'),'EVIDENCE_AUTHORITY_INCOMPLETE')
    _tokens(findings,root,'supabase/functions/radar-pre160-hardening/index.ts',('appendCheckpoint','freezeEnvelopes','radar_pre160_evidence_checkpoints','radar_pre160_decision_envelopes','real_trading:false'),'HARDENING_AUTHORITY_INCOMPLETE')
    _tokens(findings,root,'supabase/functions/radar-paper-engine-checkpoint/index.ts',('[1,2].includes(schema)','paper_decision_envelopes_local','real_trading:false'),'PAPER_CHECKPOINT_INCOMPLETE')
    _tokens(findings,root,'supabase/functions/radar-sync/index.ts',('WRITE_CONCURRENCY=20','mapConcurrent','reconcilePortfolioMarks','portfolio_values immutable mismatch','edge_ms'),'SYNC_EDGE_INCOMPLETE')
    _tokens(findings,root,'supabase/functions/radar-learning-sync/index.ts',('WRITE_CONCURRENCY=20','mapConcurrent','resolvePredictionOutcomes','.is("outcome",null)','edge_ms'),'LEARNING_EDGE_INCOMPLETE')
    _tokens(findings,root,'radar_supabase_sync.py',('SupabaseCircuitOpen','CIRCUIT_FAILURE_THRESHOLD','sync_telemetry','timeout_means_missing_data','MAX_SYNC_BATCH','random.uniform'),'SYNC_CLIENT_INCOMPLETE')
    _tokens(findings,root,'radar_learning_sync.py',('LearningSyncCircuitOpen','LEARNING_CIRCUIT_FAILURES','learning_sync_telemetry','timeout_means_missing_data','MAX_LEARNING_BATCH','random.uniform'),'LEARNING_CLIENT_INCOMPLETE')
    _tokens(findings,root,'radar_supabase_sync_partitioned_v2.py',('PER_FAMILY_AFTER_ALL_CHUNKS_REMOTE_SUCCESS','_send_family','partitioned_transport','SUPABASE_RETRY_QUEUE','drain_backpressure'),'PARTITIONED_SYNC_INCOMPLETE')
    _tokens(findings,root,'radar_pre160_controls_v6.py',('provider_divergence_guard','PENDING_SAMPLE','PENDING_TIME','lookahead_flags','uses_exit_fields_for_entry_linkage','automatic_promotion','automatic_demotion'),'TASK_151_200_INCOMPLETE')
    _tokens(findings,root,'radar_pre160_recovery_v2.py',('build_recovery_manifest','compare_recovery_manifests','SHA-256','reconstruction_allowed','backfill_allowed'),'RECOVERY_INCOMPLETE')
    _tokens(findings,root,'radar_pre160_release_authority_v2.py',('READY_FOR_MANUAL_1_6_REVIEW','manual_review_only','automatic_release','setup_allowed','live_execution_allowed'),'RELEASE_AUTHORITY_INCOMPLETE')
    _tokens(findings,root,'radar_causal_scoring_v2.py',('MAX_SCORE_ADJUSTMENT=1.5','one contribution per independent event','promotion_authorized',"'real_trading':False"),'CAUSAL_GOVERNANCE_INCOMPLETE')
    _tokens(findings,root,'radar_promotion_governance_v2.py',("'auto_promote':False","'live_review_allowed':False","'live_execution_allowed':False","'can_trade':False","'real_trading':False"),'PROMOTION_GOVERNANCE_INCOMPLETE')
    _tokens(findings,root,'radar_forward_evidence_v2.py',('synthetic_evidence_can_mature','backfill_allowed','decision_envelope_status','prediction_hash'),'BRAIN_EVIDENCE_INCOMPLETE')
    _tokens(findings,root,'radar_brain_competition_v3.py',('automatic_replacement','SHADOW_PAPER_ONLY','uses_future_outcomes'),'BRAIN_COMPETITION_INCOMPLETE')

    agents=_text(root,'radar_agents.py');champ=_text(root,'radar_champion_portfolio.py');persist=_text(root,'radar_paper_engine_persistence_v1.py');runtime5=_text(root,'radar_pre160_runtime_v5.py')
    if 'capture_trade_envelope' not in agents:findings.append('AGENT_TRANSACTIONAL_PROVENANCE_MISSING')
    if 'capture_trade_envelope' not in champ:findings.append('CHAMPION_TRANSACTIONAL_PROVENANCE_MISSING')
    if 'SCHEMA_VERSION = 2' not in persist or 'paper_decision_envelopes_local' not in persist or 'LEGACY_SCHEMA_VERSION = 1' not in persist:findings.append('PAPER_CHECKPOINT_SCHEMA2_MISSING')
    if 'uses_exit_fields_for_entry_linkage' not in runtime5 or 'competitor_key' not in runtime5:findings.append('ENTRY_ONLY_LINKAGE_AUDIT_MISSING')

    for n in range(4,10):
        text=layers[n]
        if 'REAL_TRADING=False' not in text.replace(' ','') and 'REAL_TRADING = False' not in text:findings.append(f'V{n}_TRADING_BOUNDARY_MISSING')
    version=json.loads(_text(root,'version.json')).get('version')
    if version!='1.5.28':findings.append('UNEXPECTED_WINDOWS_VERSION_BUMP')
    return {'status':'PASS' if not findings else 'FAIL','version':version,'findings':findings,
            'setup_built':False,'real_trading':False}

if __name__=='__main__':
    result=audit();print(json.dumps(result,indent=2,ensure_ascii=False));raise SystemExit(0 if result['status']=='PASS' else 1)
