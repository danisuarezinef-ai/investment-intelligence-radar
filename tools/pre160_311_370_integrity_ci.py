"""Static integrity gate for pre-1.6 tasks 311-370."""
from pathlib import Path
import json


def audit(root='.'):
    root=Path(root);findings=[]
    required=(
      'PRE160_TASKS_311_370.md','cloud_service_v9.py','radar_forward_evidence_v2.py',
      'radar_brain_calibration_v2.py','radar_brain_competition_v3.py','radar_brain_readiness_v1.py',
      'radar_brain_persistence_v1.py','tests/test_pre160_tasks_311_370.py',
      'supabase/functions/radar-brain-evidence/index.ts',
      'supabase/migrations/20260912110000_pre160_brain_evidence_snapshots_v1.sql',
      '.github/workflows/pre160-311-370-production-audit.yml')
    for p in required:
        if not (root/p).exists():findings.append('MISSING_311_370_COMPONENT:'+p)
    start=(root/'start.sh').read_text(encoding='utf-8-sig') if (root/'start.sh').exists() else ''
    v9=(root/'cloud_service_v9.py').read_text(encoding='utf-8-sig') if (root/'cloud_service_v9.py').exists() else ''
    if 'cloud_service_v9.py' not in start:findings.append('START_NOT_V9')
    if 'import cloud_service_v8 as base8' not in v9 or 'base8.start_runtime()' not in v9:findings.append('V9_CHAIN_INVALID')
    for endpoint in ('/pre160-brain-status-v1','/pre160-forward-evidence-v2','/pre160-calibration-v2',
                     '/pre160-brain-competition-v3','/pre160-brain-persistence-v1',
                     '/pre160-brain-readiness-v1','/pre160-audit-311-370-v1','/pre160-brain-gate-v1'):
        if endpoint not in v9:findings.append('MISSING_311_370_ENDPOINT:'+endpoint)
    checks={
      'radar_forward_evidence_v2.py':('prediction_hash','effective_sample_size_v2','HORIZONS','backfill_allowed','decision_envelope_status'),
      'radar_brain_calibration_v2.py':('calibration_engine_v2','log_loss','abstention_decision_v3','NO_INVERTIR / ESPERAR','signal_decay_by_family','failure_attribution'),
      'radar_brain_competition_v3.py':('champion_challenger_v3','automatic_replacement','shadow_ensemble_v2','sequential_dynamic_routing','uses_future_outcomes','historical_live_transfer_v2'),
      'radar_brain_readiness_v1.py':('range(311,371)','brain_readiness_gate','BLOCKED_TECHNICAL','NOT_READY','PENDING_SAMPLE','PENDING_TIME'),
      'radar_brain_persistence_v1.py':('content_addressed','SUPABASE','real_trading'),
      'supabase/functions/radar-brain-evidence/index.ts':('radar_brain_evidence_snapshots','content-address collision','real_trading must be false'),
    }
    for p,tokens in checks.items():
        text=(root/p).read_text(encoding='utf-8-sig') if (root/p).exists() else ''
        compact=text.replace(' ','')
        for token in tokens:
            if token.replace(' ','') not in compact:findings.append('INCOMPLETE_'+p+':'+token)
    for p in ('cloud_service_v9.py','radar_forward_evidence_v2.py','radar_brain_calibration_v2.py','radar_brain_competition_v3.py','radar_brain_readiness_v1.py'):
        text=(root/p).read_text(encoding='utf-8-sig') if (root/p).exists() else ''
        if 'REAL_TRADING=False' not in text.replace(' ',''):findings.append('REAL_TRADING_BOUNDARY_MISSING:'+p)
    version=json.loads((root/'version.json').read_text(encoding='utf-8-sig')).get('version')
    if version!='1.5.28':findings.append('UNEXPECTED_WINDOWS_VERSION_BUMP')
    proof=(root/'radar_pre160_production_proof_v1.py').read_text(encoding='utf-8-sig') if (root/'radar_pre160_production_proof_v1.py').exists() else ''
    for p in ('cloud_service_v9.py','radar_forward_evidence_v2.py','radar_brain_calibration_v2.py','radar_brain_competition_v3.py','radar_brain_readiness_v1.py','radar_brain_persistence_v1.py','supabase/functions/radar-brain-evidence/index.ts','supabase/migrations/20260912110000_pre160_brain_evidence_snapshots_v1.sql','tools/pre160_311_370_integrity_ci.py','PRE160_TASKS_311_370.md'):
        if p not in proof:findings.append('PROOF_SURFACE_NOT_PROTECTED:'+p)
    return {'status':'PASS' if not findings else 'FAIL','findings':findings,'version':version,
            'setup_built':False,'real_trading':False}

if __name__=='__main__':
    out=audit();print(json.dumps(out,indent=2));raise SystemExit(0 if out['status']=='PASS' else 1)
