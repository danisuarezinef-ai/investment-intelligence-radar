"""Static integrity gate for pre-1.6 tasks 271-310."""
from pathlib import Path
import json


def audit(root='.'):
    root=Path(root);findings=[]
    required=(
        'radar_pre160_readiness_v4.py','radar_sync_queue_v3.py','radar_provider_resilience_v2.py',
        'radar_pre160_production_proof_v3.py','radar_pre160_controls_v8.py','tests/test_pre160_tasks_271_310.py',
        'supabase/functions/radar-retry-queue/index.ts','supabase/migrations/20260912093000_pre160_remote_retry_queue_v3.sql',
        'cloud_service_v7.py')
    for p in required:
        if not (root/p).exists():findings.append('MISSING_271_310_COMPONENT:'+p)
    v7=(root/'cloud_service_v7.py').read_text(encoding='utf-8-sig') if (root/'cloud_service_v7.py').exists() else ''
    for endpoint in ('/pre160-readiness-v4','/pre160-queue-v3','/pre160-provider-resilience-v2','/pre160-proof-v3','/pre160-audit-271-310-v1','/pre160-master-gate-v4'):
        if endpoint not in v7:findings.append('MISSING_271_310_ENDPOINT:'+endpoint)
    checks={
      'radar_pre160_readiness_v4.py':('TieredReadiness','DeepWorkScheduler','StageProfiler','ONE_DEEP_JOB_AT_A_TIME','DEEP_READY'),
      'radar_sync_queue_v3.py':('durability_probe','cross_redeploy_verified','SUPABASE','ack_after_remote_success','dead_letter_remote'),
      'radar_provider_resilience_v2.py':('ProviderTransportGuard','CLOSED_OPEN_HALF_OPEN','AdaptiveRateGovernor','bulkhead_isolation'),
      'radar_pre160_production_proof_v3.py':('derived_not_asserted','requires_exact_sha','runtime_can_approve_proof'),
      'radar_pre160_controls_v8.py':('range(271,311)','master_gate_v4','PENDING_TIME','PENDING_SAMPLE'),
      'supabase/functions/radar-retry-queue/index.ts':('radar_sync_retry_queue','radar_sync_dead_letter','payload_hash','unknown_action'),
    }
    for p,tokens in checks.items():
        text=(root/p).read_text(encoding='utf-8-sig') if (root/p).exists() else ''
        compact=text.replace(' ','')
        for token in tokens:
            if token.replace(' ','') not in compact:findings.append('INCOMPLETE_'+p+':'+token)
    if 'REAL_TRADING = False' not in v7 and 'REAL_TRADING=False' not in v7.replace(' ',''):
        findings.append('V7_REAL_TRADING_BOUNDARY_MISSING')
    if '1.5.28' not in v7:findings.append('V7_WINDOWS_FREEZE_MISSING')
    version=json.loads((root/'version.json').read_text(encoding='utf-8-sig')).get('version')
    if version!='1.5.28':findings.append('UNEXPECTED_WINDOWS_VERSION_BUMP')
    proof=(root/'radar_pre160_production_proof_v1.py').read_text(encoding='utf-8-sig') if (root/'radar_pre160_production_proof_v1.py').exists() else ''
    for p in ('radar_pre160_readiness_v4.py','radar_sync_queue_v3.py','radar_provider_resilience_v2.py','radar_pre160_production_proof_v3.py','radar_pre160_controls_v8.py','supabase/functions/radar-retry-queue/index.ts','tools/pre160_271_310_integrity_ci.py'):
        if p not in proof:findings.append('PROOF_SURFACE_NOT_PROTECTED:'+p)
    return {'status':'PASS' if not findings else 'FAIL','findings':findings,'version':version,'setup_built':False,'real_trading':False}


if __name__=='__main__':
    out=audit();print(json.dumps(out,indent=2));raise SystemExit(0 if out['status']=='PASS' else 1)
