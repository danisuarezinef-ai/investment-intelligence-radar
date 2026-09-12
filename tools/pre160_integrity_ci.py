"""Static backend integrity gate for pre-1.6 work. No Windows packaging required."""
from pathlib import Path
import json


def audit(root='.'):
    root=Path(root);findings=[]
    start=(root/'start.sh').read_text(encoding='utf-8-sig');v5=(root/'cloud_service_v5.py').read_text(encoding='utf-8-sig') if (root/'cloud_service_v5.py').exists() else '';v4=(root/'cloud_service_v4.py').read_text(encoding='utf-8-sig');v3=(root/'cloud_service_v3.py').read_text(encoding='utf-8-sig')
    if 'cloud_service_v5.py' not in start:findings.append('START_NOT_V5')
    if 'import cloud_service_v4 as base4' not in v5 or 'base4.start_v3_runtime()' not in v5:findings.append('V5_NOT_COMPOSED_OVER_V4')
    if 'import cloud_service_v3 as base3' not in v4:findings.append('V4_NOT_COMPOSED_OVER_V3')
    if 'import cloud_service as base' in v4:findings.append('V4_LEGACY_BASE_IMPORT')
    for endpoint in ('/supabase-health-v1','/pre160-readiness-board-v1','/decision-provenance-v1'):
        if endpoint not in v5:findings.append('MISSING_V5_ENDPOINT:'+endpoint)
    for endpoint in ('/pre160-runtime-v2','/pre160-readiness-v1','/mobile-summary-v2','/pre160-evidence-v1','/pre160-readiness-v2','/pre160-evidence-authority-v1','/pre160-audit-v1','/pre160-hardening-v1','/pre160-hardening-authority-v1','/pre160-audit-111-130-v1','/pre160-audit-131-150-v1'):
        if endpoint not in v4:findings.append('MISSING_V4_ENDPOINT:'+endpoint)
    for endpoint in ('/pre160-evaluation-v1','/simulator-league-v1','/persistent-authority-v1'):
        if endpoint not in v3:findings.append('MISSING_V3_ENDPOINT:'+endpoint)
    for path in ('radar_pre160_runtime_v3.py','radar_pre160_cloud_v3.py','radar_pre160_evidence_persistence_v1.py','PRE160_TASKS_91_110.md','supabase/functions/radar-pre160-evidence/index.ts'):
        if not (root/path).exists():findings.append('MISSING_91_110_COMPONENT:'+path)
    for path in ('radar_pre160_runtime_v4.py','radar_pre160_runtime_v4_linkage.py','radar_pre160_cloud_v4.py','radar_pre160_hardening_persistence_v1.py','PRE160_TASKS_111_130.md','supabase/functions/radar-pre160-hardening/index.ts','supabase/migrations/20260912003000_pre160_evidence_v4.sql'):
        if not (root/path).exists():findings.append('MISSING_111_130_COMPONENT:'+path)
    for path in ('radar_decision_provenance_v1.py','radar_pre160_runtime_v5.py','PRE160_TASKS_131_150.md','tests/test_decision_provenance_v1.py'):
        if not (root/path).exists():findings.append('MISSING_131_150_COMPONENT:'+path)
    for path in ('radar_supabase_sync.py','radar_learning_sync.py','cloud_service_v5.py','tests/test_supabase_sync_resilience.py','tests/test_learning_sync_resilience_v1.py','tests/test_post150_reliability_v1.py'):
        if not (root/path).exists():findings.append('MISSING_POST150_RELIABILITY_COMPONENT:'+path)
    edge=(root/'supabase/functions/radar-pre160-evidence/index.ts').read_text(encoding='utf-8-sig') if (root/'supabase/functions/radar-pre160-evidence/index.ts').exists() else ''
    if 'appendProspectiveChain' not in edge or 'PIT_REGIME_NOT_CAPTURED' not in edge:findings.append('EVIDENCE_AUTHORITY_INCOMPLETE')
    hard=(root/'supabase/functions/radar-pre160-hardening/index.ts').read_text(encoding='utf-8-sig') if (root/'supabase/functions/radar-pre160-hardening/index.ts').exists() else ''
    for token in ('appendCheckpoint','freezeEnvelopes','radar_pre160_evidence_checkpoints','radar_pre160_decision_envelopes','real_trading:false'):
        if token not in hard:findings.append('HARDENING_AUTHORITY_INCOMPLETE:'+token)
    paper_edge_path=root/'supabase/functions/radar-paper-engine-checkpoint/index.ts';paper_edge=paper_edge_path.read_text(encoding='utf-8-sig') if paper_edge_path.exists() else ''
    for token in ('[1,2].includes(schema)','paper_decision_envelopes_local','real_trading:false'):
        if token not in paper_edge:findings.append('PAPER_CHECKPOINT_V2_AUTHORITY_INCOMPLETE:'+token)
    sync_edge_path=root/'supabase/functions/radar-sync/index.ts';sync_edge=sync_edge_path.read_text(encoding='utf-8-sig') if sync_edge_path.exists() else ''
    for token in ('WRITE_CONCURRENCY=20','mapConcurrent','reconcilePortfolioMarks','portfolio_values immutable mismatch','portfolio_values origin collision','bulkInsert("portfolio_values",fresh)','edge_ms'):
        if token not in sync_edge:findings.append('SUPABASE_SYNC_RESILIENCE_INCOMPLETE:'+token)
    learning_edge_path=root/'supabase/functions/radar-learning-sync/index.ts';learning_edge=learning_edge_path.read_text(encoding='utf-8-sig') if learning_edge_path.exists() else ''
    for token in ('WRITE_CONCURRENCY=20','mapConcurrent','resolvePredictionOutcomes','applySingleAssignmentOutcomes','.is("outcome",null)','edge_ms'):
        if token not in learning_edge:findings.append('LEARNING_SYNC_EDGE_RESILIENCE_INCOMPLETE:'+token)
    sync_py=(root/'radar_supabase_sync.py').read_text(encoding='utf-8-sig') if (root/'radar_supabase_sync.py').exists() else ''
    for token in ('SupabaseCircuitOpen','CIRCUIT_FAILURE_THRESHOLD','sync_telemetry','timeout_means_missing_data'):
        if token not in sync_py:findings.append('SUPABASE_CLIENT_RESILIENCE_INCOMPLETE:'+token)
    learning_py=(root/'radar_learning_sync.py').read_text(encoding='utf-8-sig') if (root/'radar_learning_sync.py').exists() else ''
    for token in ('LearningSyncCircuitOpen','LEARNING_CIRCUIT_FAILURES','learning_sync_telemetry','timeout_means_missing_data','MAX_LEARNING_BATCH'):
        if token not in learning_py:findings.append('LEARNING_CLIENT_RESILIENCE_INCOMPLETE:'+token)
    if 'learning_sync_telemetry' not in v5 or 'all_configured_syncs_healthy' not in v5:findings.append('V5_DUAL_SYNC_HEALTH_MISSING')
    agents=(root/'radar_agents.py').read_text(encoding='utf-8-sig');champ=(root/'radar_champion_portfolio.py').read_text(encoding='utf-8-sig');persist=(root/'radar_paper_engine_persistence_v1.py').read_text(encoding='utf-8-sig');runtime5=(root/'radar_pre160_runtime_v5.py').read_text(encoding='utf-8-sig')
    if 'capture_trade_envelope' not in agents:findings.append('AGENT_TRANSACTIONAL_PROVENANCE_MISSING')
    if 'capture_trade_envelope' not in champ:findings.append('CHAMPION_TRANSACTIONAL_PROVENANCE_MISSING')
    if "SCHEMA_VERSION = 2" not in persist or 'paper_decision_envelopes_local' not in persist or 'LEGACY_SCHEMA_VERSION = 1' not in persist:findings.append('PAPER_CHECKPOINT_SCHEMA2_MISSING')
    if 'uses_exit_fields_for_entry_linkage' not in runtime5 or "'competitor_key'" not in runtime5 and 'competitor_key' not in runtime5:findings.append('ENTRY_ONLY_LINKAGE_AUDIT_MISSING')
    if 'pre160_evidence_loop' not in v4:findings.append('EVIDENCE_WORKER_MISSING')
    if 'pre160_hardening_loop' not in v4:findings.append('HARDENING_WORKER_MISSING')
    if 'tasks_131_150_audit' not in v4:findings.append('TASKS_131_150_AUDIT_NOT_WIRED')
    if 'REAL_TRADING=False' not in v4.replace(' ',''):findings.append('V4_TRADING_BOUNDARY_MISSING')
    if 'REAL_TRADING = False' not in v5 and 'REAL_TRADING=False' not in v5.replace(' ',''):findings.append('V5_TRADING_BOUNDARY_MISSING')
    version=json.loads((root/'version.json').read_text(encoding='utf-8-sig')).get('version')
    if version!='1.5.28':findings.append('UNEXPECTED_WINDOWS_VERSION_BUMP')
    return {'status':'PASS' if not findings else 'FAIL','version':version,'findings':findings,'setup_built':False,'real_trading':False}


if __name__=='__main__':
    result=audit();print(json.dumps(result,indent=2,ensure_ascii=False));raise SystemExit(0 if result['status']=='PASS' else 1)
